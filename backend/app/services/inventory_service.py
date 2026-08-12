"""Warehouse stock ingestion and lookup — the data side of "design against
available inventory" (extends SRD FR-NET-004 beyond splitters/connectorised
cable, which already had hardcoded stock constants — see
domain/pilot.py:SPLITTER_STOCK and services/connectorised_service.py:
DEFAULT_STOCK, both flagged in their own comments as belonging here once an
inventory model existed).

An upload REPLACES the organisation's current stock snapshot wholesale — this
is a point-in-time picture for comparison, not a transactional ledger. It does
not reserve/deduct stock as projects consume it, so two concurrent projects
being told "buildable from stock" against the same units is a known
limitation (flag to Jide if this becomes a real problem — the fix is a
reservation/allocation layer, a bigger build than this).
"""
import csv
import io
import re
import uuid
from dataclasses import dataclass, field

import openpyxl
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models.inventory import StockItem

MAX_BYTES = 25 * 1024 * 1024


class InventoryError(ValueError):
    """Message is safe to show the user."""


@dataclass
class StockUploadResult:
    replaced: int = 0
    inserted: int = 0
    categories: dict[str, int] = field(default_factory=dict)
    unmatched_headers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"replaced": self.replaced, "inserted": self.inserted,
                "categories": self.categories,
                "unmatched_headers": self.unmatched_headers,
                "warnings": self.warnings}


# Header aliases so a real-world sheet (which won't always match the Aviva
# Asset Register template exactly) still parses. Matched case-insensitively
# after stripping whitespace.
_HEADER_ALIASES = {
    "stock_code": ("stock code", "stock_code", "code", "sku", "asset class id",
                   "item code", "part no", "part number"),
    "category": ("asset category", "category", "class"),
    "subcategory": ("subcategory", "sub-category", "sub category", "type"),
    "manufacturer": ("manufacturer", "make", "brand"),
    "product_name": ("product / asset name", "product name", "item",
                      "description", "asset name", "name"),
    "model": ("model", "model no", "model number"),
    "quantity": ("quantity held", "quantity", "qty", "qty held", "stock qty",
                 "quantity on hand", "on hand"),
    "uom": ("uom", "unit", "unit of measure"),
    "unit_cost": ("unit cost (£)", "unit cost", "cost", "unit price"),
    "condition": ("condition",),
    "warehouse": ("warehouse / site", "warehouse", "site", "location"),
    "remarks": ("remarks", "notes", "comment", "comments"),
}


def _normalise_headers(headers: list[str]) -> dict[int, str]:
    """Map column index -> our canonical field name, best-effort."""
    mapping: dict[int, str] = {}
    for i, h in enumerate(headers):
        if not h:
            continue
        key = str(h).strip().lower()
        for field_name, aliases in _HEADER_ALIASES.items():
            if key in aliases:
                mapping[i] = field_name
                break
    return mapping


_RATIO_RE = re.compile(r"1\s*[:x]\s*(\d{1,3})")
_CABLE_LEN_RE = re.compile(r"(\d{2,4})\s*m\b")
_CABLE_WAY_RE = re.compile(r"(\d{1,2})\s*[- ]?way\b", re.I)
_FIBRE_COUNT_RE = re.compile(r"(\d{1,3})\s*[-\s]?f(?:ibre|iber)?\b", re.I)
FIBRE_COUNTS = (2, 4, 12, 24, 48, 96, 144)
# Microduct sizes are usually quoted as nominal outer/inner mm, e.g. "12/10mm"
# or just "12mm" — the leading number is the one that matters for matching.
_MICRODUCT_MM_RE = re.compile(r"(\d{1,2})(?:/\d{1,2})?\s*mm", re.I)

_LENGTH_UOM = {"m", "metre", "metres", "meter", "meters"}
_DRUM_UOM = {"drum", "drums", "reel", "reels", "roll", "rolls"}


def _derive_match_key(category: str, subcategory: str, product_name: str,
                       model: str, uom: str = "") -> tuple[str | None, dict]:
    """Best-effort classification into categories the design engine already
    understands structurally (splitters, connectorised FAT cable, bulk fibre
    cable drums). Everything else gets no match_key and falls back to
    free-text matching — deliberately conservative, since a wrong auto-match
    (e.g. treating a generic splice closure as a splitter) would silently
    corrupt the design engine's own stock figures, not just a display list.
    """
    blob = " ".join(x for x in (category, subcategory, product_name, model) if x).lower()

    if "splitter" in blob or "plc splitter" in blob:
        m = _RATIO_RE.search(blob)
        if m:
            ratio = int(m.group(1))
            if ratio in (2, 4, 8, 16, 32, 64, 128):
                return f"splitter:{ratio}", {"ratio": ratio}

    if ("connectoris" in blob or "connectoriz" in blob
            or "pre-terminated" in blob or "preterminated" in blob):
        length_m = _CABLE_LEN_RE.search(blob)
        way = _CABLE_WAY_RE.search(blob)
        if length_m and way:
            ports = int(way.group(1))
            kind = f"{ports}way"
            return (f"connectorised_cable:{kind}:{length_m.group(1)}",
                    {"kind": kind, "ports": ports, "length_m": int(length_m.group(1))})

    # Bulk (cuttable) fibre optic cable drums/reels — feeder and distribution
    # cable in the SOM are generic lengths by fibre count, not fixed
    # pre-terminated assemblies, so these match by fibre_count alone.
    if (("fibre" in blob or "fiber" in blob) and "splitter" not in blob
            and "pigtail" not in blob and "adapter" not in blob
            and ("cable" in blob or "drum" in blob or "reel" in blob)):
        m = _FIBRE_COUNT_RE.search(blob)
        if m:
            count = int(m.group(1))
            if count in FIBRE_COUNTS:
                return f"cable_drum:{count}", {"fibre_count": count}

    # Microduct — cuttable to length like cable drums, matched by nominal mm
    # size. Compared against the SOM's HDPE duct/trench-length line, which
    # today assumes 1x duct per metre of trench (same assumption the SOM
    # itself already makes for HDPE duct — see design_pack_service.py).
    if "microduct" in blob or "micro-duct" in blob or "micro duct" in blob \
            or "subduct" in blob or "sub-duct" in blob:
        m = _MICRODUCT_MM_RE.search(blob)
        if m:
            mm = int(m.group(1))
            return f"microduct:{mm}mm", {"diameter_mm": mm}
        return "microduct:unspecified", {}

    return None, {}


def parse_stock_rows(filename: str, data: bytes) -> tuple[list[dict], list[str]]:
    """Parse a CSV or XLSX stock sheet into normalised row dicts.

    Returns (rows, unmatched_header_names) — unmatched headers are reported
    back so a real upload's quirks are visible, not silently dropped.
    """
    name = (filename or "").lower()
    if name.endswith(".csv"):
        text = data.decode("utf-8-sig", errors="replace")
        reader = csv.reader(io.StringIO(text))
        rows_raw = list(reader)
    elif name.endswith((".xlsx", ".xlsm")):
        try:
            wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
        except Exception as exc:                          # noqa: BLE001
            raise InventoryError(f"Could not read the workbook: {exc}") from exc
        # Prefer a sheet literally named for the register; else the first
        # sheet with a recognisable header row.
        ws = None
        for candidate in wb.sheetnames:
            if "asset register" in candidate.lower() or "stock" in candidate.lower():
                ws = wb[candidate]
                break
        ws = ws or wb[wb.sheetnames[0]]
        rows_raw = [list(r) for r in ws.iter_rows(values_only=True)]
    else:
        raise InventoryError("Unsupported file type — upload a .csv or .xlsx.")

    # Header row = first row containing at least 2 recognised column names.
    header_idx, mapping = None, {}
    for i, row in enumerate(rows_raw[:15]):
        m = _normalise_headers([str(c) if c is not None else "" for c in row])
        if len(m) >= 2:
            header_idx, mapping = i, m
            break
    if header_idx is None:
        raise InventoryError(
            "Could not find a header row (need at least a category/item name "
            "and a quantity column) in the first 15 rows.")

    headers = [str(c) if c is not None else "" for c in rows_raw[header_idx]]
    unmatched = [h for i, h in enumerate(headers) if h and i not in mapping]

    rows: list[dict] = []
    for raw in rows_raw[header_idx + 1:]:
        if raw is None or all(c in (None, "") for c in raw):
            continue
        rec: dict = {}
        for i, field_name in mapping.items():
            if i < len(raw):
                rec[field_name] = raw[i]
        product_name = str(rec.get("product_name") or "").strip()
        if not product_name:
            continue                                      # skip title/blank/note rows
        qty_raw = rec.get("quantity")
        try:
            quantity = float(qty_raw) if qty_raw not in (None, "") else 0.0
        except (TypeError, ValueError):
            quantity = 0.0
        rows.append({
            "stock_code": (str(rec["stock_code"]).strip() if rec.get("stock_code") else None),
            "category": (str(rec.get("category") or "Uncategorised").strip()),
            "subcategory": (str(rec["subcategory"]).strip() if rec.get("subcategory") else None),
            "manufacturer": (str(rec["manufacturer"]).strip() if rec.get("manufacturer") else None),
            "product_name": product_name,
            "model": (str(rec["model"]).strip() if rec.get("model") else None),
            "quantity": quantity,
            "uom": (str(rec["uom"]).strip() if rec.get("uom") else "pcs"),
            "unit_cost": (_to_float(rec.get("unit_cost"))),
            "condition": (str(rec["condition"]).strip() if rec.get("condition") else None),
            "warehouse": (str(rec["warehouse"]).strip() if rec.get("warehouse") else None),
            "remarks": (str(rec["remarks"]).strip() if rec.get("remarks") else None),
        })
    if not rows:
        raise InventoryError("No stock lines found under the header row.")
    return rows, unmatched


def _to_float(v) -> float | None:
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def replace_stock(db: Session, organisation_id: uuid.UUID, filename: str,
                   data: bytes) -> StockUploadResult:
    """Wholesale-replace this organisation's stock snapshot with the upload."""
    if len(data) > MAX_BYTES:
        raise InventoryError("File exceeds the 25 MB limit.")
    rows, unmatched = parse_stock_rows(filename, data)

    replaced = db.execute(
        delete(StockItem).where(StockItem.organisation_id == organisation_id))
    replaced_count = replaced.rowcount or 0

    categories: dict[str, int] = {}
    drum_count_uom_seen = False
    for r in rows:
        match_key, attributes = _derive_match_key(
            r["category"], r["subcategory"] or "", r["product_name"], r["model"] or "",
            r["uom"] or "")
        if match_key and match_key.startswith("cable_drum:") \
                and r["uom"].strip().lower() in _DRUM_UOM:
            drum_count_uom_seen = True
        item = StockItem(
            organisation_id=organisation_id,
            stock_code=r["stock_code"], category=r["category"],
            subcategory=r["subcategory"], manufacturer=r["manufacturer"],
            product_name=r["product_name"], model=r["model"],
            quantity=r["quantity"], uom=r["uom"], attributes=attributes,
            match_key=match_key, unit_cost=r["unit_cost"],
            condition=r["condition"], warehouse=r["warehouse"],
            source_filename=filename, remarks=r["remarks"],
        )
        db.add(item)
        categories[r["category"]] = categories.get(r["category"], 0) + 1

    warnings = []
    if unmatched:
        warnings.append(
            "Columns not recognised (ignored): " + ", ".join(unmatched))
    n_splitters = sum(1 for r in rows if (
        _derive_match_key(r["category"], r["subcategory"] or "", r["product_name"],
                          r["model"] or "", r["uom"] or "")[0] or "").startswith("splitter:"))
    if n_splitters == 0:
        warnings.append(
            "No rows were recognised as PON splitter stock — the splitter "
            "shortfall/surplus figures in the SOM will show 0 in stock unless "
            "your sheet labels split ratios explicitly (e.g. '1:32').")
    if drum_count_uom_seen:
        warnings.append(
            "Some fibre cable drums are stocked in drum/reel counts, not "
            "metres — the cable comparison needs total metres in stock, so "
            "those rows won't be counted until their quantity is given in "
            "metres (e.g. '2000' with UoM 'm', not '1 drum').")

    db.commit()
    return StockUploadResult(replaced=replaced_count, inserted=len(rows),
                             categories=categories, unmatched_headers=unmatched,
                             warnings=warnings)


def list_stock(db: Session, organisation_id: uuid.UUID) -> list[StockItem]:
    return list(db.scalars(
        select(StockItem).where(StockItem.organisation_id == organisation_id)
        .order_by(StockItem.category, StockItem.product_name)))


def stock_map_for_splitters(db: Session, organisation_id: uuid.UUID) -> dict[int, int]:
    """{ratio: quantity} for domain/pilot.py's build_pilot(), replacing the
    hardcoded SPLITTER_STOCK constant."""
    out: dict[int, int] = {}
    for item in db.scalars(
            select(StockItem).where(
                StockItem.organisation_id == organisation_id,
                StockItem.match_key.like("splitter:%"))):
        ratio = item.attributes.get("ratio")
        if ratio:
            out[ratio] = out.get(ratio, 0) + int(item.quantity)
    return out


def stock_lines_for_connectorised(db: Session, organisation_id: uuid.UUID
                                   ) -> list[tuple[str, int, int, int]]:
    """(kind, ports, length_m, quantity) tuples for
    domain/connectorised.py:stock_from_lines(), replacing DEFAULT_STOCK."""
    out: list[tuple[str, int, int, int]] = []
    for item in db.scalars(
            select(StockItem).where(
                StockItem.organisation_id == organisation_id,
                StockItem.match_key.like("connectorised_cable:%"))):
        a = item.attributes
        if {"kind", "ports", "length_m"} <= a.keys():
            out.append((a["kind"], a["ports"], a["length_m"], int(item.quantity)))
    return out


def stock_metres_by_fibre_count(db: Session, organisation_id: uuid.UUID
                                 ) -> dict[int, float]:
    """{fibre_count: metres_in_stock} for bulk cable drums (144F, 96F, 48F,
    24F, 12F, 4F, 2F), matched against the SOM's feeder/distribution cable
    lines which are already broken down by fibre count. Only rows stocked in
    metres count — drum/reel-count rows can't be compared to a metres
    requirement without a per-drum length, and are excluded rather than
    guessed at (see the upload warning that flags this)."""
    out: dict[int, float] = {}
    for item in db.scalars(
            select(StockItem).where(
                StockItem.organisation_id == organisation_id,
                StockItem.match_key.like("cable_drum:%"))):
        if (item.uom or "").strip().lower() not in _LENGTH_UOM:
            continue
        count = item.attributes.get("fibre_count")
        if count:
            out[count] = out.get(count, 0.0) + float(item.quantity)
    return out


def stock_metres_by_microduct_size(db: Session, organisation_id: uuid.UUID
                                    ) -> dict[str, float]:
    """{"12mm": metres, ...} — mirrors stock_metres_by_fibre_count. The SOM's
    HDPE duct line doesn't currently size-differentiate, so callers typically
    sum this across sizes for a total-vs-trench-length comparison, but the
    per-size split is kept for display since a 12mm and 40mm duct aren't
    interchangeable in practice even though the SOM doesn't know that yet."""
    out: dict[str, float] = {}
    for item in db.scalars(
            select(StockItem).where(
                StockItem.organisation_id == organisation_id,
                StockItem.match_key.like("microduct:%"))):
        if (item.uom or "").strip().lower() not in _LENGTH_UOM:
            continue
        label = item.match_key.split(":", 1)[1]
        out[label] = out.get(label, 0.0) + float(item.quantity)
    return out


# --------------------------------------------------------------------------- #
#  Generic SOM-vs-stock comparison for everything without a structured match
#  key (CPE/ONTs, cabinets, closures, terminals, chambers, mounting hardware,
#  connectors). Curated keyword buckets rather than free-text fuzzy matching —
#  deliberately: a wrong auto-match here (e.g. counting a mounting bracket as
#  a splice closure) would misreport a real shortfall as covered, which is
#  worse than reporting "no stock data" honestly. Extend this table as real
#  registers reveal item names it doesn't catch yet.
# --------------------------------------------------------------------------- #
GENERIC_BUCKETS: dict[str, list[str]] = {
    "olt": ["olt", "optical line terminal"],
    "fdh cabinet": ["fdh cabinet", "fibre distribution hub", "distribution cabinet",
                    "fdh enclosure"],
    "fat terminal": ["fat terminal", "fibre access terminal", "fibre distribution point",
                     "fdp", "distribution box", "access terminal", "distribution terminal"],
    # No bare "closure" — it false-matches "enclosure" (mounting hardware is
    # routinely described as an "enclosure mounting plate/base/bracket" in
    # real stock sheets, confirmed against the actual Aviva register).
    "splice closure": ["splice closure", "dome closure", "fibre closure", "joint closure"],
    "drop termination": ["customer outlet", "drop termination", "wall outlet",
                         "cable entry", "cof kit", "entry kit"],
    "hdpe duct": ["hdpe duct", "duct pipe"],
    "handhole": ["handhole", "hand hole"],
    "manhole": ["manhole", "man hole"],
    "mounting hardware": ["mounting bracket", "wall mount", "pole mount",
                          "mounting plate", "back box", "mounting base",
                          "pole adapter", "pole fixing", "pole bracket"],
    "aerial drop fitting": ["tension clamp", "suspension clamp", "aerial fitting",
                            "drop fitting"],
    "pigtail": ["pigtail"],
    "adapter": ["sc/apc adapter", "lc/upc adapter", "fibre adapter", "coupler"],
    "patch cord": ["patch cord", "patch lead", "patch cable"],
    "ont": ["ont", "gpon ont", "cpe", "gpon router", "gpon wi-fi"],
    "connector": ["connector assembly", "fibre connector", "optical connector"],
    "microduct": ["microduct", "micro-duct", "micro duct", "subduct", "sub-duct"],
}


def _bucket_for_som_item(item_name: str) -> str | None:
    low = item_name.lower()
    for bucket, keywords in GENERIC_BUCKETS.items():
        if any(kw in low for kw in keywords):
            return bucket
    return None


def _stock_blob(item: StockItem) -> str:
    return " ".join(x for x in (
        item.category, item.subcategory, item.product_name, item.model) if x).lower()


@dataclass
class ComparisonLine:
    section: str
    item: str
    uom: str
    required: float
    in_stock: float | None       # None = no stock data matched — not the same as 0
    matched_products: list[str] = field(default_factory=list)

    @property
    def shortfall(self) -> float | None:
        if self.in_stock is None:
            return None
        return max(0.0, round(self.required - self.in_stock, 2))

    @property
    def surplus(self) -> float | None:
        if self.in_stock is None:
            return None
        return max(0.0, round(self.in_stock - self.required, 2))

    def as_dict(self) -> dict:
        return {"section": self.section, "item": self.item, "uom": self.uom,
                "required": self.required, "in_stock": self.in_stock,
                "shortfall": self.shortfall, "surplus": self.surplus,
                "matched_products": self.matched_products}


def compare_som_generic(db: Session, organisation_id: uuid.UUID,
                        som: list[tuple[str, list[tuple]]]) -> list[ComparisonLine]:
    """Flatten the SOM (list of (section, [(item, uom, qty, note), ...])) and
    compare each line against stock via the curated keyword buckets above.
    Structured categories (splitters, connectorised cable, cable drums,
    microduct) already have their own precise comparisons elsewhere — this
    covers what's left."""
    stock = list_stock(db, organisation_id)
    by_bucket: dict[str, list[StockItem]] = {}
    for s in stock:
        if s.match_key:                     # already handled by a structured lookup
            continue
        blob = _stock_blob(s)
        for bucket, keywords in GENERIC_BUCKETS.items():
            if any(kw in blob for kw in keywords):
                by_bucket.setdefault(bucket, []).append(s)

    lines: list[ComparisonLine] = []
    for section, items in som:
        for entry in items:
            item_name, uom, qty, *_ = entry
            if not isinstance(qty, (int, float)) or qty == 0:
                continue
            bucket = _bucket_for_som_item(item_name)
            if bucket is None or bucket not in by_bucket:
                lines.append(ComparisonLine(section=section, item=item_name,
                                            uom=uom, required=qty, in_stock=None))
                continue
            matched = by_bucket[bucket]
            in_stock = sum(float(m.quantity) for m in matched)
            lines.append(ComparisonLine(
                section=section, item=item_name, uom=uom, required=qty,
                in_stock=in_stock,
                matched_products=[m.product_name for m in matched]))
    return lines
