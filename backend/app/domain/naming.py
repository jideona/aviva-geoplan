"""Street name sourcing (SRD FR-STA-009, SAD 5.5).

A street name is a claim about the world, and where the claim came from
determines whether it may be redistributed. Recording that at entry costs
nothing; reconstructing it later is impossible without re-surveying.
"""
from dataclasses import dataclass
from enum import Enum

from app.domain.licences import LicenceClass
from app.domain.verification import VerificationState


class NameSource(str, Enum):
    FIELD_OBSERVED = "field_observed"          # surveyor read the sign
    FIELD_PHOTO = "field_photo"                # sign photographed as evidence
    AUTHORITY = "authority"                    # AGIS / FCDA register
    OPERATOR_KNOWLEDGE = "operator_knowledge"  # staff local knowledge
    OPEN_DATA = "open_data"                    # OSM and similar
    PROPRIETARY_MAP = "proprietary_map"        # consumer mapping product


@dataclass(frozen=True)
class SourceRules:
    licence_class: LicenceClass
    verification: VerificationState
    commercial_ready: bool
    note: str


RULES: dict[NameSource, SourceRules] = {
    NameSource.FIELD_OBSERVED: SourceRules(
        LicenceClass.OWNED, VerificationState.FIELD_OBSERVED, True,
        "Observed in the field by an Aviva surveyor."),
    NameSource.FIELD_PHOTO: SourceRules(
        LicenceClass.OWNED, VerificationState.FIELD_MEASURED, True,
        "Street sign photographed as evidence."),
    NameSource.AUTHORITY: SourceRules(
        LicenceClass.LICENSED_AUTHORITY, VerificationState.AUTHORITY_VERIFIED, True,
        "From the naming authority register, subject to agreement terms."),
    NameSource.OPERATOR_KNOWLEDGE: SourceRules(
        LicenceClass.OWNED, VerificationState.DESK_VERIFIED, True,
        "Local knowledge. Confirm in the field before it is relied upon."),
    NameSource.OPEN_DATA: SourceRules(
        LicenceClass.SHARE_ALIKE, VerificationState.IMPORTED, False,
        "Open data under share-alike terms."),
    NameSource.PROPRIETARY_MAP: SourceRules(
        LicenceClass.DESK_REFERENCE_RESTRICTED, VerificationState.DESK_VERIFIED, False,
        "Read from a proprietary consumer map. Usable for internal pilot work. "
        "Must be replaced by a field or authority source before this register "
        "is delivered or sold."),
}


def rules_for(source: NameSource | str) -> SourceRules:
    return RULES[NameSource(source)]


def re_source_required(sources: list[str]) -> list[str]:
    """Which name sources present would block commercial delivery."""
    out = []
    for s in set(sources):
        try:
            if not RULES[NameSource(s)].commercial_ready:
                out.append(s)
        except ValueError:
            out.append(s)
    return sorted(out)
