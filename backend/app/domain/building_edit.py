"""Manual building capture — drawing rooftops that imported data missed.

How a building was captured determines whether it may be redistributed, exactly
as with street-name sources: a rooftop traced over display-only Esri imagery is
a derivative of that imagery and cannot be sold; one traced over Aviva's own
drone orthomosaic, or walked in the field, is clean.
"""
from enum import Enum

from app.domain.licences import LicenceClass
from app.domain.verification import VerificationState


class CaptureSource(str, Enum):
    FIELD_SURVEYED = "field_surveyed"        # walked and measured
    TRACED_OWNED = "traced_owned"            # over Aviva drone orthomosaic
    TRACED_REFERENCE = "traced_reference"    # over Esri/consumer imagery
    MANUAL = "manual"                        # placed without a clear source


_RULES = {
    CaptureSource.FIELD_SURVEYED: (LicenceClass.OWNED,
                                   VerificationState.FIELD_OBSERVED, True),
    CaptureSource.TRACED_OWNED: (LicenceClass.OWNED,
                                 VerificationState.DESK_VERIFIED, True),
    # Traced over display-only imagery: usable for the pilot, must be re-sourced
    # (re-traced over owned imagery or field-confirmed) before commercial use.
    CaptureSource.TRACED_REFERENCE: (LicenceClass.DESK_REFERENCE_RESTRICTED,
                                     VerificationState.DESK_VERIFIED, False),
    CaptureSource.MANUAL: (LicenceClass.PROPRIETARY_RESTRICTED,
                           VerificationState.DESK_VERIFIED, False),
}


def rules_for(source: CaptureSource | str):
    lc, vs, commercial = _RULES[CaptureSource(source)]
    return {"licence_class": lc.value, "verification_state": vs.value,
            "commercial_ready": commercial}
