import uuid

from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import MultiPolygon, mapping
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models.boundary import ProjectBoundary
from app.db.models.project import Project
from app.db.models.user import User
from app.domain.boundary import BoundaryParseError, parse_boundary
from app.domain.crs import area_sqm
from app.services import audit_service

MAX_UPLOAD_BYTES = 32 * 1024 * 1024


class BoundaryError(ValueError):
    """Message is safe to return to the caller."""


def set_boundary(db: Session, user: User, project: Project, filename: str,
                 data: bytes) -> ProjectBoundary:
    if not data:
        raise BoundaryError("The uploaded file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise BoundaryError(
            f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit for "
            "boundary uploads."
        )

    try:
        geom = parse_boundary(filename, data)
    except BoundaryParseError as exc:
        raise BoundaryError(str(exc)) from exc

    # Measure in the project metric CRS. Area in degrees is meaningless.
    area_km2 = area_sqm(geom, project.metric_crs_epsg) / 1_000_000
    limit = get_settings().max_boundary_area_sqkm
    if area_km2 > limit:
        raise BoundaryError(
            f"Boundary covers {area_km2:,.1f} km², above the {limit:,.0f} km² "
            "limit. Check the file is the district boundary and not a larger extent."
        )
    if area_km2 <= 0:
        raise BoundaryError("Boundary has no area.")

    if geom.geom_type == "Polygon":
        geom = MultiPolygon([geom])

    # Supersede rather than overwrite, so designs stay traceable to their extent.
    db.execute(
        update(ProjectBoundary)
        .where(ProjectBoundary.project_id == project.id,
               ProjectBoundary.is_current.is_(True))
        .values(is_current=False)
    )

    boundary = ProjectBoundary(
        project_id=project.id,
        geom=from_shape(geom, srid=4326),
        area_sqkm=round(area_km2, 4),
        source_filename=filename,
        verification_state="imported",
    )
    db.add(boundary)
    db.flush()
    audit_service.record(
        db, actor=user, entity_type="project_boundary", entity_id=boundary.id,
        action="create", project_id=project.id,
        changes={"source_filename": {"before": None, "after": filename},
                 "area_sqkm": {"before": None, "after": round(area_km2, 4)}},
    )
    db.commit()
    db.refresh(boundary)
    return boundary


def get_current(db: Session, project_id: uuid.UUID) -> ProjectBoundary | None:
    return db.scalar(
        select(ProjectBoundary).where(
            ProjectBoundary.project_id == project_id,
            ProjectBoundary.is_current.is_(True),
        )
    )


def as_geojson(boundary: ProjectBoundary) -> dict:
    return mapping(to_shape(boundary.geom))
