"""One-off import: the "Existing Network Survey Map" monday.com board (35
street-segment rows, 106 chamber/pole photos) into GeoPlan.

What this does NOT do: guess which real Street each row is. Two rows in the
source sheet share the exact text "OLUSEGUN OBASANJO WAY" and two share
"Untamed Road" — real labelling collisions, not a bug to paper over — so this
creates one RecordedStreet per monday row (keyed by monday's own item id, not
by name) and drops it into the *existing* recorded-street matching queue
(the same one any other field-recorded street name goes through). A human
confirms each match on the Street Matching screen, where the photos now show
up as a thumbnail strip to help make that call — see frontend StreetMatching.tsx.

Each photo becomes a MediaAsset attached to entity_type="recorded_street" (not
to a Street directly, since we haven't matched anything yet). MediaAsset is
already polymorphic — this needed zero schema changes.

EXIF note: the source photos carry a GPSInfo IFD but every value in it is NaN
(the phone's camera app wrote the tag structure without a location fix) — so
there is no photo-level geolocation to use here, only the recorded DateTime
(real and used below for captured_at / survey_date).

This is a batch operational tool, not part of the live API: it opens its own
DB session and talks to MinIO directly. Same convention as
app/bulk_import_overture.py — run it where the stack already runs, not in a
sandboxed/offline environment.

Usage (inside the api container):
    python -m app.import_existing_network_survey --district Wuye
    python -m app.import_existing_network_survey --district Wuye --commit

Default is a DRY RUN — it prints what it would create and touches nothing.
Pass --commit to actually write RecordedStreet rows and upload photos.

Data expected at (relative to the repo root, mounted into the container the
same way source-data/ already is):
    source-data/existing_network_survey/manifest.csv
    source-data/existing_network_survey/photos/*.jpg
    source-data/existing_network_survey/Existing_Network_Survey_Map_export.xlsx
"""
import argparse
import csv
import io
from datetime import datetime
from pathlib import Path

from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models.media import MediaAsset
from app.db.models.organisation import Organisation
from app.db.models.project import Project
from app.db.models.survey_data import RecordedStreet
from app.db.models.user import User
from app.db.session import SessionLocal

DEFAULT_DATA_DIR = Path("/app/source-data/existing_network_survey")
SOURCE_FILE = "Existing_Network_Survey_Map_export.xlsx"
THUMBS_UP = "\U0001F44D"
_EXT = "jpg"


def _get_actor(db: Session) -> tuple[Organisation, User]:
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


def _get_project(db: Session, org: Organisation, district: str | None,
                 project_id: str | None) -> Project:
    if project_id:
        project = db.scalar(select(Project).where(
            Project.organisation_id == org.id, Project.id == project_id))
        if project is None:
            raise SystemExit(f"No project with id={project_id!r} in this organisation.")
        return project

    # district alone is NOT a unique key — e.g. "Wuye District" (real survey
    # data) and "Wuye District (sample)" (seed data) can both have
    # district="Wuye". Refuse to guess; make the caller disambiguate with
    # --project-id instead of silently picking whichever row Postgres returns
    # first (that's how photos ended up in the sample project the first
    # time this ran).
    matches = list(db.scalars(select(Project).where(
        Project.organisation_id == org.id, Project.district == district)))
    if not matches:
        others = db.scalars(select(Project.district).where(
            Project.organisation_id == org.id)).all()
        raise SystemExit(
            f"No project with district={district!r}. Projects on file: "
            f"{sorted(set(others))}")
    if len(matches) > 1:
        listing = "\n".join(f"  {p.id}  {p.name!r}  (status={p.status})" for p in matches)
        raise SystemExit(
            f"{len(matches)} projects have district={district!r} — ambiguous. "
            f"Re-run with --project-id for the one you mean:\n{listing}")
    return matches[0]


def _exif_datetime(path: Path) -> datetime | None:
    try:
        img = Image.open(path)
        exif = img.getexif()
        raw = exif.get(306)  # DateTime, e.g. "2026:03:03 10:20:57"
        if not raw:
            return None
        return datetime.strptime(raw, "%Y:%m:%d %H:%M:%S")
    except Exception:                                     # noqa: BLE001
        return None


def _load_manifest(data_dir: Path) -> dict[str, list[dict]]:
    """item_id -> list of {name, flag, column, filename} rows, in sheet order."""
    by_item: dict[str, list[dict]] = {}
    with open(data_dir / "manifest.csv", newline="") as f:
        for row in csv.DictReader(f):
            by_item.setdefault(row["item_id"], []).append(row)
    return by_item


def run(district: str | None, project_id: str | None, data_dir: Path, commit: bool) -> int:
    db = SessionLocal()
    minio_client = None
    bucket = None
    if commit:
        from minio import Minio
        s = get_settings()
        minio_client = Minio(s.minio_endpoint, access_key=s.minio_access_key,
                             secret_key=s.minio_secret_key, secure=s.minio_secure)
        bucket = s.minio_bucket
        if not minio_client.bucket_exists(bucket):
            minio_client.make_bucket(bucket)

    created_streets = 0
    skipped_streets = 0
    uploaded_photos = 0
    try:
        org, user = _get_actor(db)
        project = _get_project(db, org, district, project_id)
        by_item = _load_manifest(data_dir)
        print(f"Project: {project.name} ({project.id}) — {len(by_item)} survey rows "
              f"in manifest, {sum(len(v) for v in by_item.values())} photo refs.")
        print("DRY RUN — nothing will be written. Pass --commit to apply.\n"
              if not commit else "")

        for item_id, rows in by_item.items():
            name = rows[0]["name"]
            flag = rows[0]["flag"]

            existing = db.scalar(select(RecordedStreet).where(
                RecordedStreet.project_id == project.id,
                RecordedStreet.source_file == SOURCE_FILE,
                RecordedStreet.note.like(f"%item {item_id}%"),
            ))
            if existing is not None:
                print(f"  [{item_id}] {name!r} — already imported (recorded_street "
                      f"{existing.id}), skipping.")
                skipped_streets += 1
                continue

            photo_paths = []
            earliest_dt: datetime | None = None
            for r in rows:
                p = data_dir / "photos" / r["local_file"]
                if not p.exists():
                    print(f"  [{item_id}] WARNING: missing file {p}")
                    continue
                dt = _exif_datetime(p)
                if dt and (earliest_dt is None or dt < earliest_dt):
                    earliest_dt = dt
                photo_paths.append((r, p, dt))

            flagged = flag.strip() != THUMBS_UP
            note = (f'Imported from monday.com "Existing Network Survey Map" '
                   f"board (item {item_id}). Review flag on the board: {flag}"
                   + (" — needs a second look, not thumbed-up on the board."
                      if flagged else "."))

            print(f"  [{item_id}] {name!r} — {len(photo_paths)} photo(s), "
                  f"survey_date={earliest_dt.date() if earliest_dt else None}"
                  f"{' — FLAGGED' if flagged else ''}")

            if not commit:
                created_streets += 1
                continue

            rec = RecordedStreet(
                project_id=project.id, name=name,
                survey_date=earliest_dt.date() if earliest_dt else None,
                surveyor=None, source_file=SOURCE_FILE, note=note,
            )
            db.add(rec)
            db.flush()  # need rec.id for the MediaAsset rows below

            for r, p, dt in photo_paths:
                key = f"{project.id}/recorded_street/{rec.id}/{p.stem}_{r['column']}.{_EXT}"
                data = p.read_bytes()
                minio_client.put_object(
                    bucket, key, data=io.BytesIO(data),
                    length=len(data), content_type="image/jpeg")
                db.add(MediaAsset(
                    project_id=project.id, entity_type="recorded_street",
                    entity_id=rec.id, kind="photo", object_key=key,
                    content_type="image/jpeg", size_bytes=len(data),
                    caption=f"{r['column']} — {name} (monday item {item_id})",
                    captured_at=dt, captured_by="import:monday.com",
                    uploaded=True,
                ))
                uploaded_photos += 1

            db.commit()
            created_streets += 1

        print(f"\n{'Would create' if not commit else 'Created'}: {created_streets} "
              f"recorded streets, {skipped_streets} already present"
              + (f", {uploaded_photos} photos uploaded." if commit else "."))
        if not commit:
            print("Re-run with --commit to write this for real.")
    finally:
        db.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--district", default="Wuye",
                        help="Project district to import into (default: Wuye). "
                             "Ignored if --project-id is given.")
    parser.add_argument("--project-id",
                        help="Exact project id to import into — required when "
                             "--district matches more than one project.")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR),
                        help="Folder containing manifest.csv and photos/ "
                             f"(default: {DEFAULT_DATA_DIR}).")
    parser.add_argument("--commit", action="store_true",
                        help="Actually write to the DB and upload to MinIO. "
                             "Without this, it's a dry run.")
    args = parser.parse_args()
    return run(args.district, args.project_id, Path(args.data_dir), args.commit)


if __name__ == "__main__":
    raise SystemExit(main())
