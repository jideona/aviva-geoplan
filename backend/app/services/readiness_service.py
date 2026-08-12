"""Project workflow readiness — what is done, what is next, what is blocked.

Turns the pipeline (boundary -> roads -> buildings -> assignment -> naming ->
design -> routing -> pilot) into an explicit checklist so a user always knows
the next step, and a step that cannot run explains its prerequisite rather than
failing opaquely.
"""
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.boundary import ProjectBoundary
from app.db.models.building import Building
from app.db.models.design import DesignRun
from app.db.models.project import Project
from app.db.models.street import Street


def _count(db, model, project_id, **filt):
    stmt = select(func.count()).select_from(model).where(
        model.project_id == project_id)
    for k, v in filt.items():
        stmt = stmt.where(getattr(model, k) == v)
    return db.scalar(stmt) or 0


def readiness(db: Session, project: Project) -> dict:
    pid = project.id

    boundary = db.scalar(select(ProjectBoundary).where(
        ProjectBoundary.project_id == pid,
        ProjectBoundary.is_current.is_(True)))
    n_roads = _count(db, Street, pid)
    n_named = db.scalar(select(func.count()).select_from(Street).where(
        Street.project_id == pid, Street.name.isnot(None))) or 0
    n_buildings = db.scalar(select(func.count()).select_from(Building).where(
        Building.project_id == pid, Building.excluded.is_(False))) or 0
    n_assigned = db.scalar(select(func.count()).select_from(Building).where(
        Building.project_id == pid, Building.excluded.is_(False),
        Building.street_id.isnot(None))) or 0
    design = db.scalar(select(DesignRun).where(
        DesignRun.project_id == pid, DesignRun.is_current.is_(True)))

    steps = []

    def step(key, label, done, detail, action=None, blocked_by=None):
        steps.append({"key": key, "label": label,
                      "status": ("done" if done else
                                 "blocked" if blocked_by else "pending"),
                      "detail": detail, "action": action,
                      "blocked_by": blocked_by})

    step("boundary", "Project boundary",
         boundary is not None,
         f"{float(boundary.area_sqkm):.2f} km²" if boundary else "Not uploaded",
         action=None if boundary else "Upload a KML, KMZ or GeoJSON boundary.")

    step("roads", "Road network",
         n_roads > 0,
         f"{n_roads} street records" if n_roads else "No roads imported",
         action=None if n_roads else
             "Import the raw OSM XML under 'OSM road network'.",
         blocked_by=None if boundary else "boundary")

    step("buildings", "Buildings",
         n_buildings > 0,
         f"{n_buildings:,} buildings" if n_buildings else "None imported",
         action=None if n_buildings else
             "Import the Overture buildings GeoJSON.",
         blocked_by=None if boundary else "boundary")

    step("assignment", "Street assignment",
         n_assigned > 0,
         (f"{n_assigned:,} of {n_buildings:,} buildings assigned"
          if n_buildings else "No buildings yet"),
         action=None if n_assigned else
             "Run street assignment to link buildings to streets.",
         blocked_by=("buildings" if not n_buildings else
                     "roads" if not n_roads else None))

    step("naming", "Street naming",
         n_named > 0,
         f"{n_named} of {n_roads} streets named" if n_roads else "No streets",
         action=None if n_named else
             "Name streets in the register, or match your survey names.",
         blocked_by=None if n_roads else "roads")

    step("design", "Network design",
         design is not None,
         (f"{design.summary.get('zones', 0)} FATs, "
          f"{design.summary.get('fdh_count', 0)} FDHs"
          if design else "Not run"),
         action=None if design else
             "Run the design (tick Pilot mode for the connectorised core).",
         blocked_by="buildings" if not n_buildings else None)

    # Next actionable step: first pending (not blocked) step.
    nxt = next((s for s in steps if s["status"] == "pending"), None)
    blocked = [s for s in steps if s["status"] == "blocked"]

    return {
        "project": project.name,
        "steps": steps,
        "complete": all(s["status"] == "done" for s in steps),
        "next_step": nxt,
        "blocked_steps": blocked,
        "summary": (f"Next: {nxt['action']}" if nxt else
                    "All core steps complete." ),
    }
