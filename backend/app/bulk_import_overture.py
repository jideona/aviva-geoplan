"""One-off bulk import: for every district in ABUJA_DISTRICTS, get-or-create
a project (which auto-attaches a GRID3 ward or OSM district boundary — see
app/services/reference_data_service.py), download that boundary's Overture
Maps building footprints, and run them through the same import pipeline a
manual per-project upload would use (app/services/import_service.py). The
goal is base building-footprint data in every district so field surveys have
something to work from, not a finished register — imported buildings land
with verification_state="imported" and are expected to be corrected in the
field, same as the Wuye pilot.

This is a batch operational tool, not part of the live API: it opens its own
DB session and shells out to the `overturemaps` CLI, which needs real
outbound internet access to Overture's public release (S3/Azure). Run it
where the stack already runs, not in a sandboxed/offline environment.

Requires, on the machine running this (not part of the API image's
requirements.txt, same convention as tools/detect_buildings.py):
    pip install overturemaps
Verify `overturemaps download --help` still matches the --bbox/--type/-f/-o
flags used below for whatever version you install — this was written
against Overture's documented CLI form, not tested live from here.

Usage (inside the api container):
    python -m app.bulk_import_overture
    python -m app.bulk_import_overture --district Wuse --district Garki

Via Makefile (from the repo root, stack already up):
    make bulk-import-buildings
"""
import argparse
import subprocess
import tempfile
from pathlib import Path

from geoalchemy2.shape import to_shape
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models.organisation import Organisation
from app.db.models.project import Project
from app.db.models.user import User
from app.db.session import SessionLocal
from app.schemas.project import ProjectCreate
from app.services import import_service, project_service
from app.services.import_service import ImportError_
from app.services.project_service import ProjectError

# Starting point compiled from the FCT master-plan phases and known
# satellite/Area-Council towns — NOT GIS-verified against an authoritative
# AGIS district register. Review and edit before a production run.
#
# A name that doesn't resolve to a GRID3 ward or OSM admin_level=7 relation
# is skipped and logged, not treated as an error — same "a miss is a normal
# outcome" design as reference_data_service.ensure_boundary_for_district.
ABUJA_DISTRICTS: list[str] = [
    # Phase 1 (AMAC core)
    "Asokoro", "Wuse", "Garki", "Maitama", "Central Area",
    # Phase 2
    "Wuse II", "Garki II", "Utako", "Jabi", "Mabushi", "Kado", "Gwarinpa",
    "Wuye", "Katampe", "Guzape", "Jahi",
    # Phase 3
    "Dawaki", "Dutse", "Life Camp", "Katampe Extension", "Wumba",
    "Galadimawa", "Lokogoma", "Apo", "Durumi", "Gudu", "Gwarinpa II",
    # Phase 4 / industrial
    "Idu", "Kabusa", "Dei-Dei", "Gwagwa",
    # Satellite towns
    "Kubwa", "Nyanya", "Lugbe", "Karu", "Dakwo", "Pyakasa",
    # Outer Area Council HQ towns
    "Gwagwalada", "Kuje", "Kwali", "Abaji", "Bwari",
]


def _get_actor(db: Session) -> tuple[Organisation, User]:
    """Reuses the seeded organisation/admin as the actor of record for
    everything this script creates. Run `make seed` first if this fails.
    """
    settings = get_settings()
    org = db.scalar(select(Organisation).order_by(Organisation.created_at).limit(1))
    if org is None:
        raise SystemExit("No organisation exists yet. Run `make seed` first.")
    user = db.scalar(
        select(User).where(User.email == settings.seed_admin_email.lower()))
    if user is None:
        raise SystemExit(
            f"Seed admin {settings.seed_admin_email!r} not found. Run `make seed` first.")
    return org, user


def _get_or_create_project(
    db: Session, org: Organisation, user: User, district: str,
) -> Project:
    existing = db.scalar(
        select(Project).where(
            Project.organisation_id == org.id, Project.district == district,
        )
    )
    if existing is not None:
        return existing

    payload = ProjectCreate(
        name=f"{district} (bulk import)", district=district,
        country="NG", state="FCT", city="Abuja",
        metric_crs_epsg=32632, project_type="ftth", network_technology="xgs_pon",
        notes="Created by bulk_import_overture — base data for survey planning.",
    )
    return project_service.create_project(db, user, payload)


def _download_overture_buildings(bbox: tuple[float, float, float, float]) -> bytes:
    """Shells out to the `overturemaps` CLI for a bbox download. The import
    pipeline clips to the true boundary polygon by centroid afterwards, so a
    bbox (a superset of the district) is exactly what's needed here — no
    need to pre-clip.
    """
    minx, miny, maxx, maxy = bbox
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "buildings.geojson"
        cmd = [
            "overturemaps", "download", f"--bbox={minx},{miny},{maxx},{maxy}",
            "--type=building", "-f", "geojson", "-o", str(out_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            raise RuntimeError(
                f"overturemaps download failed (exit {result.returncode}): "
                f"{result.stderr.strip()}")
        return out_path.read_bytes()


def run(districts: list[str]) -> int:
    db = SessionLocal()
    had_error = False
    try:
        org, user = _get_actor(db)
        for district in districts:
            print(f"\n=== {district} ===")
            try:
                project = _get_or_create_project(db, org, user, district)
            except ProjectError as exc:
                print(f"  project error: {exc}")
                had_error = True
                continue

            boundary = project_service.current_boundary(db, project.id)
            if boundary is None:
                print("  no boundary (no GRID3 ward or OSM district match) — "
                      "skipped, nothing to clip buildings against.")
                continue

            bbox = to_shape(boundary.geom).bounds
            try:
                data = _download_overture_buildings(bbox)
            except (RuntimeError, subprocess.TimeoutExpired) as exc:
                print(f"  Overture download failed: {exc}")
                had_error = True
                continue

            try:
                result = import_service.import_overture_buildings(
                    db, user, project, f"{district}_overture_buildings.geojson", data)
            except ImportError_ as exc:
                print(f"  import error: {exc}")
                had_error = True
                continue

            print(f"  created={result.created} updated={result.updated} "
                  f"unchanged={result.unchanged} "
                  f"outside_boundary={result.skipped_outside_boundary} "
                  f"too_small={result.skipped_too_small} "
                  f"protected={result.skipped_protected}")
            share_alike = result.licence_classes.get("share_alike", 0)
            if share_alike:
                print(f"  NOTE: {share_alike} share-alike features present — "
                      "check licence_summary() before commercial delivery.")
    finally:
        db.close()
    return 1 if had_error else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--district", action="append", dest="districts",
        help="Limit to this district (repeatable). Default: all of ABUJA_DISTRICTS.")
    args = parser.parse_args()
    return run(args.districts or ABUJA_DISTRICTS)


if __name__ == "__main__":
    raise SystemExit(main())
