"""Verification state model (SRD FR-VER-001).

State ordering matters: a protected write refuses to overwrite anything at
FIELD_OBSERVED or above without an explicit approving actor.
"""
from enum import Enum


class VerificationState(str, Enum):
    IMPORTED = "imported"
    AI_DETECTED = "ai_detected"
    DESK_VERIFIED = "desk_verified"
    FIELD_OBSERVED = "field_observed"
    FIELD_MEASURED = "field_measured"
    CUSTOMER_CONFIRMED = "customer_confirmed"
    AUTHORITY_VERIFIED = "authority_verified"
    ENGINEER_APPROVED = "engineer_approved"
    AS_BUILT_CONFIRMED = "as_built_confirmed"


_ORDER = list(VerificationState)
PROTECTED_FROM = VerificationState.FIELD_OBSERVED


def rank(state: VerificationState | str) -> int:
    return _ORDER.index(VerificationState(state))


def is_protected(state: VerificationState | str) -> bool:
    """True where an automated process may not overwrite the record."""
    return rank(state) >= rank(PROTECTED_FROM)


def is_authoritative(state: VerificationState | str) -> bool:
    """True where the record may be relied on by an issued design."""
    return rank(state) >= rank(VerificationState.ENGINEER_APPROVED)
