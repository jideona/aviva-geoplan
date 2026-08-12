from app.domain.verification import (VerificationState, is_authoritative,
                                     is_protected, rank)


def test_ordering_is_monotonic():
    assert rank(VerificationState.IMPORTED) < rank(VerificationState.FIELD_OBSERVED)
    assert rank(VerificationState.FIELD_OBSERVED) < rank(VerificationState.ENGINEER_APPROVED)


def test_imported_and_ai_are_not_protected():
    assert not is_protected(VerificationState.IMPORTED)
    assert not is_protected(VerificationState.AI_DETECTED)
    assert not is_protected(VerificationState.DESK_VERIFIED)


def test_field_observed_and_above_are_protected():
    assert is_protected(VerificationState.FIELD_OBSERVED)
    assert is_protected(VerificationState.CUSTOMER_CONFIRMED)
    assert is_protected(VerificationState.AS_BUILT_CONFIRMED)


def test_only_engineer_approved_and_above_is_authoritative():
    assert not is_authoritative(VerificationState.FIELD_MEASURED)
    assert is_authoritative(VerificationState.ENGINEER_APPROVED)
    assert is_authoritative(VerificationState.AS_BUILT_CONFIRMED)
