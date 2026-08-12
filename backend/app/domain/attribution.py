"""Attribution manifest and export clearance (SRD FR-IMP-032, FR-IMP-033).

Every export carries a statement of what it is built from. Where the export
purpose is incompatible with the obligations of its sources, the export is
blocked rather than silently produced.
"""
from dataclasses import dataclass
from datetime import date
from enum import Enum

from app.domain.licences import COMMERCIAL_BLOCKERS, LicenceClass, label


class ExportPurpose(str, Enum):
    INTERNAL = "internal"          # Aviva use, including pilot design work
    CLIENT_REVIEW = "client_review"  # shared with a named client under NDA
    COMMERCIAL = "commercial"      # delivered or sold; strictest gate


@dataclass
class SourceEntry:
    name: str
    licence: str | None
    licence_class: str
    feature_count: int
    source_date: date | None = None


@dataclass
class Manifest:
    project: str
    generated: str
    purpose: ExportPurpose
    sources: list[SourceEntry]
    blocked: bool
    reason: str | None

    def attribution_lines(self) -> list[str]:
        out = []
        for s in self.sources:
            licence = s.licence or s.licence_class.replace("_", " ")
            out.append(f"{s.name} — {licence} ({s.feature_count:,} features)")
        return out

    def as_text(self) -> str:
        lines = [
            "AVIVA GEOPLAN — DATA ATTRIBUTION",
            f"Project: {self.project}",
            f"Generated: {self.generated}",
            f"Export purpose: {self.purpose.value}",
            "",
            "Contributing sources:",
            *(f"  - {line}" for line in self.attribution_lines()),
        ]
        if self.blocked:
            lines += ["", "EXPORT BLOCKED", self.reason or ""]
        return "\n".join(lines)


def build(project_name: str, generated: str, purpose: ExportPurpose,
          sources: list[SourceEntry]) -> Manifest:
    classes: set[LicenceClass] = set()
    for s in sources:
        try:
            classes.add(LicenceClass(s.licence_class))
        except ValueError:
            classes.add(LicenceClass.PROPRIETARY_RESTRICTED)

    blockers = classes & COMMERCIAL_BLOCKERS
    blocked = purpose is ExportPurpose.COMMERCIAL and bool(blockers)
    reason = None
    if blocked:
        names = ", ".join(sorted(label(c) for c in blockers))
        reason = (
            f"This export contains {names} data, which may not be commercially "
            "delivered. Re-source the affected records, or export for internal "
            "or client-review purposes instead."
        )
    return Manifest(project_name, generated, purpose, sources, blocked, reason)
