"""Network Design Report — the full design pack as a single Word document.

Same underlying data as the xlsx pack (design_pack_service.assemble) and the
same methodology text (design_pack_service.methodology_sections), laid out as
a client/management-facing narrative report: summary, aerial view of the
design, methodology, diagrams, then every schedule from the Excel pack
reproduced as Word tables.

The aerial screenshot is supplied by the caller (captured client-side from
the live MapLibre canvas — see ReportsPanel.tsx) because a faithful render of
the interactive map, at whatever zoom/layers the user was looking at, is not
something this service can reconstruct headlessly. Topology and schematic
diagrams are generated the normal way (schematic_service) and rasterised with
the same svglib/reportlab path the PNG diagram endpoints already use.
"""
import io

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor

from app.services.design_pack_service import methodology_sections

NAVY = RGBColor(0x0D, 0x1B, 0x4B)
BRAND = RGBColor(0x1A, 0x6F, 0xA8)
STEEL = RGBColor(0x5A, 0x73, 0x9A)
AMBER = RGBColor(0xB4, 0x53, 0x09)
TEAL = RGBColor(0x00, 0xC9, 0xA7)
INK = RGBColor(0x2A, 0x34, 0x46)


class WordReportError(ValueError):
    """Message is safe to show the user."""


def svg_to_png_bytes(svg: str, dpi: int = 144) -> bytes:
    """Same conversion path as the topology.png / schematic.png endpoints —
    pure Python, no system cairo needed."""
    from reportlab.graphics import renderPM
    from svglib.svglib import svg2rlg
    drawing = svg2rlg(io.StringIO(svg))
    if drawing is None:
        raise WordReportError("Diagram conversion failed.")
    return renderPM.drawToString(drawing, fmt="PNG", dpi=dpi)


# --------------------------------------------------------------------------- #
#  Formatting helpers
# --------------------------------------------------------------------------- #
def _shade(cell, hex_color: str):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), hex_color)
    tcPr.append(shd)


def _cell_text(cell, text, *, bold=False, color=None, size=9, italic=False):
    cell.text = ""
    p = cell.paragraphs[0]
    run = p.add_run("" if text is None else str(text))
    run.font.size = Pt(size)
    run.bold = bold
    run.italic = italic
    if color is not None:
        run.font.color.rgb = color


def _title_block(doc, project: str, ran: str, eng: str):
    h = doc.add_paragraph()
    run = h.add_run("AVIVA NETWORX")
    run.font.size = Pt(22); run.font.bold = True; run.font.color.rgb = NAVY
    sub = doc.add_paragraph()
    run = sub.add_run(f"{project} — Network Design Report")
    run.font.size = Pt(14); run.font.color.rgb = BRAND
    meta = doc.add_paragraph()
    run = meta.add_run(f"Design engine v{eng} · {ran[:19].replace('T', ' ')}")
    run.font.size = Pt(9); run.font.color.rgb = STEEL; run.italic = True


def _h1(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(18)
    p.paragraph_format.space_after = Pt(6)
    run = p.add_run(text)
    run.font.size = Pt(15); run.font.bold = True; run.font.color.rgb = NAVY
    return p


def _h2(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(4)
    run = p.add_run(text)
    run.font.size = Pt(11.5); run.font.bold = True; run.font.color.rgb = BRAND
    return p


def _prose(doc, text, *, italic=False, color=INK, size=9.5):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(6)
    run = p.add_run(text)
    run.font.size = Pt(size); run.italic = italic; run.font.color.rgb = color
    return p


def _bullets(doc, items):
    for item in items:
        p = doc.add_paragraph(style="List Bullet")
        run = p.add_run(str(item))
        run.font.size = Pt(9); run.font.color.rgb = STEEL; run.italic = True


def _kv_table(doc, rows: list[tuple[str, str]]):
    """Two-column label/value block, used for summary-style sections."""
    t = doc.add_table(rows=0, cols=2)
    t.autofit = True
    for label, value in rows:
        row = t.add_row()
        if label == "" and value == "":
            continue
        head = label.isupper()
        _cell_text(row.cells[0], label, bold=head,
                  color=NAVY if head else STEEL, size=10 if head else 9.5)
        _cell_text(row.cells[1], value, color=NAVY, size=9.5)
    return t


def _data_table(doc, headers: list[str], rows, *, header_fill="0D1B4B"):
    t = doc.add_table(rows=1, cols=len(headers))
    t.alignment = WD_TABLE_ALIGNMENT.LEFT
    hdr = t.rows[0].cells
    for i, h in enumerate(headers):
        _cell_text(hdr[i], h, bold=True, color=RGBColor(0xFF, 0xFF, 0xFF), size=9)
        _shade(hdr[i], header_fill)
    for values in rows:
        cells = t.add_row().cells
        for i, v in enumerate(values):
            _cell_text(cells[i], v, size=9)
    return t


def _picture(doc, png_bytes: bytes | None, caption: str, missing_note: str,
             *, width_in=6.5):
    if png_bytes:
        try:
            doc.add_picture(io.BytesIO(png_bytes), width=Inches(width_in))
        except Exception:                                          # noqa: BLE001
            # A bad/corrupt upload (e.g. the aerial screenshot) should degrade
            # to a note, not fail the whole export.
            _prose(doc, missing_note, italic=True, color=STEEL)
            return
        last = doc.paragraphs[-1]
        last.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cap = doc.add_paragraph()
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = cap.add_run(caption)
        run.font.size = Pt(8.5); run.italic = True; run.font.color.rgb = STEEL
    else:
        _prose(doc, missing_note, italic=True, color=STEEL)


# --------------------------------------------------------------------------- #
#  Document assembly
# --------------------------------------------------------------------------- #
def build_docx(pack: dict, *, aerial_png: bytes | None = None,
              topology_png: bytes | None = None,
              schematic_png: bytes | None = None) -> bytes:
    doc = Document()
    section = doc.sections[0]
    section.left_margin = section.right_margin = Cm(2.0)
    style = doc.styles["Normal"]
    style.font.name = "Calibri"; style.font.size = Pt(9.5)

    t = pack["totals"]; proj = pack["project"]
    ran = pack["design"].get("ran_at", ""); eng = pack["design"].get("engine_version", "")
    rules = pack["design"].get("rules") or {}
    ring = pack.get("ring")

    _title_block(doc, proj, ran, eng)

    # ---- Aerial view of the network design ----
    _h1(doc, "Aerial View — Network Design")
    _picture(doc, aerial_png, f"{proj} — aerial view of the current network design.",
             "No aerial screenshot was supplied for this export. Capture one from "
             "the map (position, zoom and layers as needed — e.g. toggle "
             "satellite imagery on) and re-export to include it here.")

    # ---- Network summary ----
    _h1(doc, "Network Summary")
    _kv_table(doc, [
        ("FDH cabinets", str(t["fdh_count"])),
        ("FAT terminals (serving zones)", str(t["fat_count"])),
        ("Premises served", str(t["served_premises"])),
        ("Buildings served", str(t["served_buildings"])),
        ("OLT PON ports used", f'{t["olt_ports_used"]} / 16'),
        ("", ""),
        ("PHASING", ""),
        ("Phase 1 — connectorised core (premises)", str(t["phase1_premises"])),
        ("Phase 2 — conventional extension (premises)", str(t["phase2_premises"])),
        ("", ""),
        ("MEASURED PLANT (routed)", ""),
        ("Quantities scope", pack.get("scope_note", "")),
        ("Total trench", f'{t["total_trench_m"]:,.0f} m'),
        ("Feeder cable (with allowances)", f'{t["feeder_cable_m"]:,.0f} m'),
        ("Distribution cable (with allowances)", f'{t["distribution_cable_m"]:,.0f} m'),
        ("Drop cable (estimate)", f'{t["drop_cable_m"]:,.0f} m'),
    ])

    if pack.get("optical"):
        _h2(doc, "Optical Loss Budget")
        for ph, o in sorted(pack["optical"].items()):
            wc = o.get("worst_case_path") or {}
            _prose(doc,
                f"Phase {ph} — {o['architecture']}: verdict "
                f"{o['verdict'].upper()} · budget {o['system_budget_db']} dB · "
                f"worst case {wc.get('total_loss_db', '?')} dB", color=NAVY)

    _h2(doc, "Assumptions & Notes")
    notes = [
        "Drop cable and HDPE duct are ESTIMATES (drop = buildings x avg drop x 1.1; duct approx = trench).",
        "Detected/traced geometry is pilot-only until re-sourced; premises are counts, not surveyed units.",
        "Measurements are metric-CRS accurate but bounded by source geometry — planning grade, not survey grade.",
    ] + list(pack.get("missing_phases") or []) + list(pack.get("warnings") or [])
    _bullets(doc, notes)

    # ---- Methodology (shared with the xlsx pack) ----
    _h1(doc, "Design Methodology")
    for heading, paragraphs in methodology_sections(rules, ring):
        _h2(doc, heading)
        for p in paragraphs:
            _prose(doc, p)

    # ---- Diagrams ----
    _h1(doc, "Network Topology Diagram")
    _picture(doc, topology_png, f"{proj} — logical topology (NOC to FDH lanes to FAT boxes).",
             "Not available — the connectorised pilot/port model could not be "
             "assembled for this design (see Stock Comparison for possible "
             "causes, e.g. no connectorised cable stock uploaded).")

    _h1(doc, "Line Schematic (SLD)")
    _picture(doc, schematic_png, f"{proj} — straight-line diagram.",
             "Not available — the connectorised pilot/port model could not be "
             "assembled for this design.")

    # ---- FDH schedule ----
    _h1(doc, "FDH Schedule")
    _data_table(doc,
        ["FDH", "Premises", "FATs", "Splitters", "Capacity", "Utilisation %", "Reach m"],
        [[f["code"], f["premises"], f["fats"], f["splitters"], f["capacity"],
          f["utilisation_pct"], round(f["reach_m"], 1)]
         for f in pack["design"]["fdhs"]])

    # ---- FAT schedule ----
    _h1(doc, "FAT / Serving-Zone Schedule")
    _data_table(doc,
        ["FAT / zone", "Premises", "Buildings", "Spare ports", "Max drop m",
         "Avg drop m", "Assumed?"],
        [[z["zone_code"], z["premises_count"], z["building_count"],
          z["spare_ports"], z["max_drop_m"], z["avg_drop_m"],
          "yes" if z.get("premises_assumed") else "no"]
         for z in pack["design"]["zones"]])

    # ---- Schedule of Materials ----
    _h1(doc, "Schedule of Materials (SOM)")
    for cat, items in pack["som"]:
        _h2(doc, cat)
        _data_table(doc, ["Item", "Unit", "Qty", "Note"],
                    [[item, unit, qty, note] for item, unit, qty, note in items],
                    header_fill="1A2E72")

    # ---- Stock comparison ----
    _h1(doc, "Stock Comparison")
    _prose(doc,
        "Upload your warehouse stock via the Reports panel to populate this "
        "section with real figures. Rows with no stock data are not zero — "
        "the uploaded sheet just doesn't carry that item.", italic=True)
    rows = []
    for line in pack.get("stock_comparison") or []:
        no_data = line.get("in_stock") is None
        note = line.get("note") or ""
        matched = line.get("matched_products")
        if matched:
            note = (note + " " if note else "") + "Matched: " + ", ".join(matched[:4])
        rows.append([
            line["section"], line["item"], line["uom"], line["required"],
            "—" if no_data else line.get("in_stock"),
            "—" if no_data else line.get("shortfall"),
            "—" if no_data else line.get("surplus"), note])
    _data_table(doc, ["Section", "Item", "Unit", "Required", "In stock",
                      "Shortfall (buy)", "Surplus", "Note"], rows,
                header_fill="1A2E72")

    # ---- Bill of Quantities ----
    _h1(doc, "Bill of Quantities (BOQ)")
    _prose(doc,
        "Rates are left blank for the estimator to fill by hand — this "
        "document does not compute amounts live the way the xlsx pack's "
        "formulas do. Quantities marked ESTIMATE (drop cable, duct) should "
        "be confirmed on site.", italic=True)
    for sec, items in pack["boq"]:
        _h2(doc, sec)
        _data_table(doc, ["Ref", "Description", "Unit", "Qty", "Rate (NGN)", "Amount (NGN)"],
                    [[ref, desc, unit, qty, "", ""] for ref, desc, unit, qty in items],
                    header_fill="1A2E72")

    # ---- Connectivity-dependent detail sheets ----
    conn = pack.get("connectivity")
    if conn:
        _h1(doc, "FAT Port Assignment Schedule")
        _prose(doc,
            "Ports are assigned in building-code order. Drop lengths are "
            "straight-line estimates; measured drops are in the drops layer.",
            italic=True)
        rows = []
        for z in conn["fats"]:
            flags = "; ".join(z["warnings"]) or (
                "premises assumed" if z["premises_assumed"] else "")
            for port in z["ports"]:
                rows.append([
                    z["code"], z["fdh"], port["port"], port["building"],
                    port.get("premises"), port["drop_est_m"],
                    round(z["utilisation_pct"], 1),
                    flags if port["port"] == 1 else ""])
        _data_table(doc, ["FAT", "FDH", "Port", "Building / status", "Premises",
                          "Drop est. m", "Zone util %", "Flags"], rows)

        _h1(doc, "Building Connection Schedule")
        _prose(doc,
            "One row per connected building, in code order. Premises source: "
            "surveyed (field), modelled (typology), assumed (rule default — "
            "treat as a lower bound). Drop lengths are straight-line "
            "estimates.", italic=True)
        rows = []
        for z in conn["fats"]:
            flags = "; ".join(z["warnings"]) or (
                "premises assumed" if z["premises_assumed"] else "")
            for port in z["ports"]:
                if port["building"] == "SPARE":
                    continue
                rows.append((port["building"], port.get("address", ""),
                            z["code"], port["port"], z["fdh"],
                            port.get("premises"), port.get("premises_source", ""),
                            port["drop_est_m"], port.get("deployment") or "unset", flags))
        rows.sort(key=lambda x: x[0])
        _data_table(doc, ["Building code", "Address", "FAT", "FAT port", "FDH",
                          "Premises", "Count source", "Drop est. m", "Drop type",
                          "Zone flags"], rows)
        _prose(doc,
            f"{len(rows):,} connected buildings · "
            f"{sum(v[5] or 0 for v in rows):,} premises", color=NAVY)

        _h1(doc, "FDH Splitter Tray Map")
        _prose(doc,
            "Sx:Py = splitter number : output port. Outputs are consumed "
            "sequentially across the FDH's FATs in code order.", italic=True)
        rows = []
        for f in conn["fdhs"]:
            for i, tr in enumerate(f["tray"]):
                rows.append([f["code"], tr["fat"], tr["premises"],
                            f'{tr["from"]} → {tr["to"]}', f'{tr["dist_fibres"]}F',
                            tr["dist_est_m"],
                            f'{f["feeder_cable_fibres"]}F' if i == 0 else ""])
        _data_table(doc, ["FDH", "FAT", "Premises", "Splitter ports (from → to)",
                          "Distribution cable", "Length est. m", "Feeder cable"], rows)

    # ---- Cable Core Schedule (segment-by-segment fibre core count) ----
    core_schedule = pack.get("core_schedule")
    if core_schedule:
        _h1(doc, "Cable Core Schedule")
        _prose(doc, core_schedule.get("note", ""), italic=True)
        _data_table(doc, ["Tier", "From", "To", "Cores", "Length m", "With allowances m"],
                    [[seg["tier"], seg["from"], seg["to"], seg["cores"],
                      seg["length_m"], seg["with_allowances_m"]]
                     for seg in core_schedule["segments"]],
                    header_fill="1A2E72")
        for tier, agg in core_schedule["summary"].items():
            _prose(doc,
                f"{tier.upper()} total — {agg['segments']} segments · "
                f"{agg['length_m']:,.0f} m measured · "
                f"{agg['with_allowances_m']:,.0f} m with allowances · "
                f"{agg['cores_total']} cores total", color=NAVY)
        if core_schedule.get("unreachable"):
            _prose(doc,
                "Unreachable on street graph: " + "; ".join(core_schedule["unreachable"]),
                color=AMBER)

    # ---- Ring option ----
    if ring:
        _h1(doc, "Feeder Ring — Resilience Option")
        _prose(doc,
            "Closed feeder loop NOC to every FDH and back to NOC. Any single "
            "feeder cut leaves all FDHs reachable from the other direction. "
            "Quantities are INCREMENTAL to the base design and are NOT "
            "included in the BOQ totals.", italic=True)
        eqp = pack["pilot"]["equipment"] if pack.get("pilot") else {}
        splq32 = 0
        for l in (eqp.get("splitters") or []):
            if l["item"] == "1:32 splitter":
                splq32 = l["with_spares"]
        rows = [
            ("FDHs on ring", "no.", ring["fdhs_on_ring"],
             " → ".join(ring["order"][:8]) + (" …" if len(ring["order"]) > 9 else "")),
            ("Ring route length (trench basis)", "m", ring["ring_trench_m"],
             "street-routed closed loop"),
            ("As-designed feeder tree (compare)", "m", ring["tree_feeder_m"],
             "sum of NOC→FDH shortest paths"),
            ("Incremental trench (upper bound)", "m", ring["incremental_trench_m"],
             "less where ring shares duct with tree routes"),
            ("Ring feeder cable (with allowances)", "m", ring["ring_cable_m"],
             "slack + jointing + wastage + contingency"),
            ("2:N protection splitters (Type B, option)", "no.", splq32,
             "replaces 1:32 units at FDHs for <50 ms switchover"),
            ("OLT protection PON ports (option)", "no.",
             pack["totals"].get("olt_ports_used", 0),
             "one protection port per working port"),
        ]
        _data_table(doc, ["Item", "Unit", "Qty", "Note"], rows, header_fill="1A2E72")
        if ring.get("unreachable_fdhs"):
            _prose(doc, "Unreachable on street graph: " + ", ".join(ring["unreachable_fdhs"]),
                  color=AMBER)
        if ring.get("note"):
            _prose(doc, ring["note"], italic=True, color=STEEL)

    buf = io.BytesIO(); doc.save(buf)
    return buf.getvalue()
