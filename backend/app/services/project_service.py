import logging
import uuid

from geoalchemy2.shape import from_shape, to_shape
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.boundary import ProjectBoundary
from app.db.models.project import Project
from app.db.models.user import User
from app.domain.crs import is_metric
from app.domain.identifiers import district_prefix
from app.schemas.project import ProjectCreate, ProjectUpdate
from app.services import audit_service, reference_data_service

logger = logging.getLogger(__name__)


class ProjectError(ValueError):
    """Message is safe to return to the caller."""


def list_projects(db: Session, user: User) -> list[Project]:
    return list(db.scalars(
        select(Project)
        .where(Project.organisation_id == user.organisation_id)
        .order_by(Project.created_at.desc())
    ))


def get_project(db: Session, user: User, project_id: uuid.UUID) -> Project:
    project = db.scalar(
        select(Project).where(
            Project.id == project_id,
            Project.organisation_id == user.organisation_id,
        )
    )
    if project is None:
        raise ProjectError("Project not found.")
    return project


def current_boundary(db: Session, project_id: uuid.UUID) -> ProjectBoundary | None:
    return db.scalar(
        select(ProjectBoundary)
        .where(ProjectBoundary.project_id == project_id,
               ProjectBoundary.is_current.is_(True))
        .order_by(ProjectBoundary.created_at.desc())
    )


def create_project(db: Session, user: User, payload: ProjectCreate) -> Project:
    errors = payload.validate_enums()
    if errors:
        raise ProjectError("; ".join(errors))

    if not is_metric(payload.metric_crs_epsg):
        raise ProjectError(
            f"EPSG:{payload.metric_crs_epsg} is not a metric CRS. Measurement "
            "requires a projected CRS in metres — EPSG:32632 for the FCT."
        )

    try:
        prefix = district_prefix(payload.district)
    except ValueError as exc:
        raise ProjectError(str(exc)) from exc

    existing = db.scalar(select(func.count()).select_from(Project).where(
        Project.organisation_id == user.organisation_id,
        func.lower(Project.name) == payload.name.lower(),
    ))
    if existing:
        raise ProjectError(f"A project named {payload.name!r} already exists.")

    project = Project(
        organisation_id=user.organisation_id,
        owner_user_id=user.id,
        code_prefix=prefix,
        **payload.model_dump(exclude={"notes"}),
        notes=payload.notes,
    )
    db.add(project)
    db.flush()
    audit_service.record(
        db, actor=user, entity_type="project", entity_id=project.id,
        action="create", project_id=project.id,
        changes={"name": {"before": None, "after": project.name}},
    )

    _auto_attach_boundary(db, user, project)

    db.commit()
    db.refresh(project)
    return project


def _auto_attach_boundary(db: Session, user: User, project: Project) -> None:
    """Best-effort: attach a GRID3 ward or OSM district boundary matching
    the project's district if one is cached or can be fetched. Never blocks
    project creation on a miss — reference_data_service already treats "no
    match" and "upstream unreachable" as normal, logged outcomes rather than
    errors, so a project with an unrecognised or not-yet-mapped district
    name still gets created, just without an auto-attached boundary (same
    as before this feature existed).
    """
    ref = reference_data_service.ensure_boundary_for_district(db, project.district)
    if ref is None:
        return

    boundary = ProjectBoundary(
        project_id=project.id,
        geom=from_shape(to_shape(ref.geom), srid=4326),
        area_sqkm=ref.area_sqkm,
        source_filename=f"auto:{ref.source}:{ref.source_ref}",
        verification_state="imported",
    )
    db.add(boundary)
    db.flush()
    audit_service.record(
        db, actor=user, entity_type="project_boundary", entity_id=boundary.id,
        action="create", project_id=project.id,
        changes={
            "source_filename": {"before": None, "after": boundary.source_filename},
            "area_sqkm": {"before": None, "after": float(ref.area_sqkm)},
        },
    )
    logger.info(
        "Auto-attached %s boundary (%s) to new project %s (district=%r)",
        ref.kind, ref.source, project.id, project.district)


_UPDATABLE = ("name", "client", "state", "city", "design_capacity",
              "expected_takeup_rate", "design_horizon", "status", "notes")


def update_project(db: Session, user: User, project_id: uuid.UUID,
                   payload: ProjectUpdate) -> Project:
    errors = payload.validate_enums()
    if errors:
        raise ProjectError("; ".join(errors))

    project = get_project(db, user, project_id)
    if project.status == "archived":
        raise ProjectError("Archived projects are read-only.")

    before = {f: getattr(project, f) for f in _UPDATABLE}
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    after = {f: getattr(project, f) for f in _UPDATABLE}

    changes = audit_service.diff(before, after)
    if changes:
        audit_service.record(
            db, actor=user, entity_type="project", entity_id=project.id,
            action="update", project_id=project.id, changes=changes,
        )
    db.commit()
    db.refresh(project)
    return project
