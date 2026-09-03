"""Create field-surveyor accounts (SRD Section 11: Role.FIELD_SURVEYOR).

Companion to app/seed.py, which must be run first (it creates the
"Aviva Networx Ltd." organisation this script attaches new users to).

Field surveyors are organisation-scoped, not project/district-scoped, so a
single account here can pick up work on any district.

Usage (from the repo root, matching the `make seed` pattern):

    docker compose exec api python -m app.seed_field_surveyors

Idempotent: an email that already exists is left untouched (no password
reset) and reported as skipped, so this is safe to re-run when adding a new
batch of surveyors — just extend NEW_SURVEYORS below.

Each newly created account gets a fresh, random password printed once to
stdout. Nothing is written to disk. Capture that output somewhere your
password manager can pick it up, then relay each password to its surveyor
over a channel separate from wherever the email addresses live (e.g. WhatsApp
the password, email the username) — and treat these as one-time credentials
the surveyor should change on first login once the app supports that.
"""
import secrets
import string
import sys

from sqlalchemy import select

from app.core.permissions import Role
from app.core.security import hash_password
from app.db.models.organisation import Organisation
from app.db.models.user import User
from app.db.session import SessionLocal

ORG_NAME = "Aviva Networx Ltd."

# Extend this list to onboard more surveyors; re-running only creates the new
# ones. (name, email) — email is lower-cased/stripped to match auth_service's
# lookup in app/services/auth_service.py.
NEW_SURVEYORS: list[tuple[str, str]] = [
    ("Raphael Nwanna", "ralph.nwanna@hakonix.com"),
    ("John Agbor", "john.agbor@hakonix.com"),
    ("Henry Imiruaye", "henry.imiruaye@hakonix.com"),
]


def _generate_password(length: int = 12) -> str:
    alphabet = string.ascii_uppercase + string.ascii_lowercase + string.digits
    symbols = "!@#%^&*-_+="
    chars = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice(symbols),
    ]
    chars += [secrets.choice(alphabet) for _ in range(length - len(chars))]
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def main() -> int:
    db = SessionLocal()
    try:
        org = db.scalar(select(Organisation).where(Organisation.name == ORG_NAME))
        if org is None:
            print(f'Organisation "{ORG_NAME}" not found — run `make seed` first.',
                  file=sys.stderr)
            return 1

        created: list[tuple[str, str, str]] = []
        skipped: list[str] = []

        for full_name, raw_email in NEW_SURVEYORS:
            email = raw_email.lower().strip()
            existing = db.scalar(select(User).where(User.email == email))
            if existing is not None:
                skipped.append(email)
                continue

            password = _generate_password()
            user = User(
                organisation_id=org.id, email=email, full_name=full_name,
                password_hash=hash_password(password),
                roles=[Role.FIELD_SURVEYOR.value], is_active=True,
            )
            db.add(user)
            db.flush()
            created.append((full_name, email, password))

        db.commit()

        if created:
            print("Created field surveyor accounts (save these passwords now — "
                  "they are not stored or shown again):")
            for full_name, email, password in created:
                print(f"  {full_name:<20} {email:<32} {password}")
        if skipped:
            print("Skipped (already exist, password unchanged):")
            for email in skipped:
                print(f"  {email}")
        if not created and not skipped:
            print("Nothing to do — NEW_SURVEYORS is empty.")

        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
