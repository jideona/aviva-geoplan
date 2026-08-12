"""Error classification — who a failure is for, and what to do about it.

Two audiences:
  - user   : a workflow or input mistake the person can fix (wrong file,
             missing prerequisite, invalid value). Shown to them with a remedy.
  - admin  : a system fault (schema behind, DB down, misconfiguration,
             unhandled bug). Shown as an operational alert and logged in full.

Classification is by HTTP status so existing `HTTPException(detail=...)` raises
keep working unchanged; the message they already carry is the user-facing text.
"""

USER_STATUSES = {400, 401, 403, 404, 409, 413, 422, 451}
ADMIN_STATUSES = {500, 502, 503, 504}


def classify(status_code: int) -> str:
    if status_code in ADMIN_STATUSES:
        return "admin"
    return "user"


def audience_hint(status_code: int) -> str:
    """A short standing instruction appended for the relevant audience."""
    if status_code in ADMIN_STATUSES:
        return ("This is a system fault. If it persists, check the API logs "
                "and that the database schema is current (`make migrate`).")
    if status_code == 403:
        return "Your role does not permit this action; ask an administrator."
    if status_code == 401:
        return "Your session has expired — sign in again."
    if status_code == 413:
        return "The upload is too large; split it or reduce the area."
    return "Check the step and try again."


def envelope(status_code: int, message: str, remedy: str | None = None) -> dict:
    return {
        "detail": message,
        "kind": classify(status_code),
        "remedy": remedy or audience_hint(status_code),
    }
