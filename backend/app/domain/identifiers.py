"""Human-readable identifier generation (SRD FR-PRM-002).

Format:  WUY-ST-001-C001-B001-P001
Codes are immutable once issued and are never recycled.
"""
import re

_DISTRICT_RE = re.compile(r"[^A-Z]")


def district_prefix(district_name: str) -> str:
    """Derive a three-letter prefix, e.g. 'Wuye District' -> 'WUY'."""
    cleaned = _DISTRICT_RE.sub("", district_name.upper())
    if len(cleaned) < 3:
        raise ValueError(f"cannot derive a 3-letter prefix from {district_name!r}")
    return cleaned[:3]


def street_code(prefix: str, seq: int) -> str:
    return f"{prefix}-ST-{seq:03d}"


def compound_code(street: str, seq: int) -> str:
    return f"{street}-C{seq:03d}"


def building_code(parent: str, seq: int) -> str:
    return f"{parent}-B{seq:03d}"


def premises_code(building: str, seq: int) -> str:
    return f"{building}-P{seq:03d}"
