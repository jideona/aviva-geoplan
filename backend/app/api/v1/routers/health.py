from pathlib import Path

from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import DbSession

router = APIRouter(tags=["health"])

# Migrations run at container start, not on code reload. Adding a migration
# during a session therefore leaves a running container on an older schema,
# and every query against the changed table fails with a column error that
# surfaces as an unexplained 500. This check names the problem.
# health.py lives at app/api/v1/routers/, so the app package is three levels
# up and the migrations sit inside it.
_VERSIONS = Path(__file__).resolve().parents[3] / "migrations" / "versions"


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
def ready(db: DbSession) -> dict:
    db.execute(text("SELECT 1"))
    postgis = db.execute(text("SELECT PostGIS_Version()")).scalar()

    applied = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    on_disk = sorted(p.name.split("_")[0] for p in _VERSIONS.glob("[0-9]*.py"))
    latest = on_disk[-1] if on_disk else None
    pending = [v for v in on_disk if applied is None or v > applied]

    return {
        "status": "ready" if not pending else "migration_pending",
        "postgis": str(postgis),
        "schema_applied": applied,
        "schema_latest": latest,
        "pending_migrations": pending,
        "action": ("Run `make migrate`. The container applies migrations only "
                   "at start, so a migration added since then is not in the "
                   "database and queries against changed tables will fail.")
        if pending else None,
    }
