"""Seed a development organisation, administrator and Wuye project.

Everything created here is sample data and is labelled as such. It must never
be presented as verified field data (SRD NFR-MNT-007).
"""
import sys

from sqlalchemy import select

from app.core.config import get_settings
from app.core.permissions import Role
from app.core.security import hash_password
from app.db.models.organisation import Organisation
from app.db.models.project import Project
from app.db.models.provenance import DataSource
from app.db.models.user import User
from app.db.session import SessionLocal
from app.domain.identifiers import district_prefix

SOURCES = [
    ("Overture Maps", "overture", "ODbL / CDLA-Permissive (mixed)", "share_alike",
     "Primary ingestion layer. Harmonised reference, not independent ground truth."),
    ("Google Open Buildings v3", "open_buildings", "CC BY 4.0", "attribution",
     "Alternative footprints with confidence. No addresses, use type or units."),
    ("Google Open Buildings 2.5D Temporal", "open_buildings", "CC BY 4.0", "attribution",
     "Area-level height stratification only. Modelled raster ~4 m effective "
     "resolution, ends 2023. Not a surveyed attribute."),
    ("Microsoft Global ML Building Footprints", "microsoft_gbf", "ODbL", "share_alike",
     "Footprint comparison and gap filling."),
    ("OpenStreetMap", "osm", "ODbL", "share_alike",
     "Street names, topology, access detail, points of interest."),
    ("GRID3 Nigeria", "grid3", "CC BY 4.0", "attribution",
     "Area-level population baselining. Not for per-premises derivation."),
    ("Aviva field survey", "field_survey", "Proprietary — Aviva Networx", "owned",
     "Authoritative source for units, use, access and demand."),
]


def main() -> int:
    settings = get_settings()
    if not settings.seed_admin_password:
        print("SEED_ADMIN_PASSWORD is not set. Refusing to create an account "
              "without a password.", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        org = db.scalar(select(Organisation).where(Organisation.name == "Aviva Networx Ltd."))
        if org is None:
            org = Organisation(name="Aviva Networx Ltd.", country="NG")
            db.add(org)
            db.flush()
            print(f"created organisation {org.name}")

        email = settings.seed_admin_email.lower()
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(
                organisation_id=org.id, email=email, full_name="Platform Administrator",
                password_hash=hash_password(settings.seed_admin_password),
                roles=[Role.PLATFORM_ADMIN.value], is_active=True,
            )
            db.add(user)
            db.flush()
            print(f"created administrator {email}")
        else:
            # Always reset the existing dev admin to the known SEED_ADMIN_PASSWORD
            # with a fresh argon2 hash. This heals a legacy/corrupt hash (a
            # bcrypt value from before the argon2 switch makes every login 500)
            # and guarantees the credential in infra/.env actually works.
            from app.core.security import is_valid_hash
            was_valid = is_valid_hash(user.password_hash)
            user.password_hash = hash_password(settings.seed_admin_password)
            user.is_active = True
            db.flush()
            print(f"administrator {email} — password reset to SEED_ADMIN_PASSWORD "
                  f"(previous hash valid: {was_valid})")

        for name, stype, licence, lclass, role in SOURCES:
            if db.scalar(select(DataSource).where(DataSource.name == name)) is None:
                db.add(DataSource(name=name, source_type=stype, licence=licence,
                                  licence_class=lclass, admitted_role=role))
                print(f"registered source {name}")

        project = db.scalar(select(Project).where(Project.name == "Wuye District (sample)"))
        if project is None:
            db.add(Project(
                organisation_id=org.id, owner_user_id=user.id,
                name="Wuye District (sample)", client="Aviva Networx Ltd.",
                country="NG", state="FCT", city="Abuja", district="Wuye",
                code_prefix=district_prefix("Wuye"),
                metric_crs_epsg=32632, project_type="ftth",
                network_technology="xgs_pon", status="draft",
                notes="SAMPLE PROJECT — contains no verified field data.",
            ))
            print("created sample Wuye project")

        db.commit()
        print("seed complete")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
