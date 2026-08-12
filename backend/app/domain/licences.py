"""Licence classification and propagation (SAD 5.5).

Obligations are computed from the set of contributing sources, not annotated by
hand. A register derived from a share-alike source may itself be subject to
share-alike terms, so the classification has to survive every derivation.
"""
from enum import Enum


class LicenceClass(str, Enum):
    SHARE_ALIKE = "share_alike"
    ATTRIBUTION = "attribution"
    PROPRIETARY_RESTRICTED = "proprietary_restricted"
    OWNED = "owned"
    LICENSED_AUTHORITY = "licensed_authority"
    TILE_SERVICE = "tile_service"
    # Read from a proprietary consumer mapping product. Usable for internal
    # pilot work; must be re-sourced before commercial delivery.
    DESK_REFERENCE_RESTRICTED = "desk_reference_restricted"


# Overture records the upstream licence string. Google Open Buildings arrives
# with a null licence because Overture treats it as CDLA-Permissive; the
# upstream grant is CC BY 4.0, so it is attribution, not unrestricted.
_BY_LICENCE_STRING = {
    "odbl-1.0": LicenceClass.SHARE_ALIKE,
    "odbl": LicenceClass.SHARE_ALIKE,
    "cc-by-sa-4.0": LicenceClass.SHARE_ALIKE,
    "cc-by-4.0": LicenceClass.ATTRIBUTION,
    "cc0-1.0": LicenceClass.ATTRIBUTION,
    "cdla-permissive-2.0": LicenceClass.ATTRIBUTION,
}

_BY_DATASET = {
    "openstreetmap": LicenceClass.SHARE_ALIKE,
    "microsoft ml buildings": LicenceClass.SHARE_ALIKE,
    "google open buildings": LicenceClass.ATTRIBUTION,
    "esri community maps": LicenceClass.ATTRIBUTION,
}


def classify(licence: str | None, dataset: str | None) -> LicenceClass:
    """Conservative: an unrecognised source is restricted, not permissive."""
    if licence:
        hit = _BY_LICENCE_STRING.get(licence.strip().lower())
        if hit:
            return hit
    if dataset:
        hit = _BY_DATASET.get(dataset.strip().lower())
        if hit:
            return hit
    return LicenceClass.PROPRIETARY_RESTRICTED


# Classes that must not reach a commercially delivered dataset.
COMMERCIAL_BLOCKERS = {
    LicenceClass.SHARE_ALIKE,
    LicenceClass.DESK_REFERENCE_RESTRICTED,
    LicenceClass.TILE_SERVICE,
    # An unrecognised or contractually restricted source is blocked by
    # default. Permitting delivery requires a positive classification, not
    # merely the absence of a known problem.
    LicenceClass.PROPRIETARY_RESTRICTED,
}

# Human labels. The enum values are identifiers, not prose.
LABELS = {
    LicenceClass.SHARE_ALIKE: "share-alike",
    LicenceClass.ATTRIBUTION: "attribution-only",
    LicenceClass.PROPRIETARY_RESTRICTED: "proprietary or unclassified",
    LicenceClass.OWNED: "Aviva-owned",
    LicenceClass.LICENSED_AUTHORITY: "licensed from an authority",
    LicenceClass.TILE_SERVICE: "tile-service display-only",
    LicenceClass.DESK_REFERENCE_RESTRICTED: "desk reference restricted",
}


def label(cls: LicenceClass) -> str:
    return LABELS.get(cls, cls.value.replace("_", " "))


def blocks_commercial_delivery(classes: set[LicenceClass]) -> bool:
    """Share-alike obligations propagate into a delivered derivative database;
    proprietary consumer-map derivations may not be redistributed at all."""
    return bool(classes & COMMERCIAL_BLOCKERS)


def clearance_note(classes: set[LicenceClass]) -> str:
    blockers = classes & COMMERCIAL_BLOCKERS
    if not blockers:
        return "Clear for commercial delivery."
    parts = []
    if LicenceClass.SHARE_ALIKE in blockers:
        parts.append("share-alike obligations may attach to the whole derivative")
    if LicenceClass.PROPRIETARY_RESTRICTED in blockers:
        parts.append("proprietary or unclassified sources are not cleared")
    if LicenceClass.DESK_REFERENCE_RESTRICTED in blockers:
        parts.append("proprietary consumer-map derivations must be re-sourced")
    if LicenceClass.TILE_SERVICE in blockers:
        parts.append("tile-service content is display-only")
    return "Not clear for commercial delivery: " + "; ".join(parts) + "."


def attribution_required(classes: set[LicenceClass]) -> bool:
    return bool(classes & {LicenceClass.SHARE_ALIKE, LicenceClass.ATTRIBUTION,
                           LicenceClass.LICENSED_AUTHORITY})
