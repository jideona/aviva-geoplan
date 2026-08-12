"""Deployment task tracking — phase 1 of the GeoPlan_Deployment_PM_Proposal.docx
plan. Replaces the "Deployment plan" monday.com board: area, status, owner,
dates, free-text updates/issues, on a real project with a real map underneath
it instead of a spreadsheet row with no coordinates.

Two edit paths, deliberately different in what they allow:
  - Permission.TASK_MANAGE (project manager / survey coordinator / construction
    manager) can create, edit any field, reassign, and delete.
  - Anyone else who can see the project can update status/updates/issues on a
    task they are personally assigned to — that's the whole point of an
    "assignee": the person doing the work reports progress on it without
    needing task-management rights over the whole project.
"""
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import Permission, has_permission
from app.db.models.deployment import (TASK_AREAS, TASK_ENTITY_TYPES,
                                      TASK_STATUSES, DeploymentTask)
from app.db.models.project import Project
from app.db.models.user import User

# Fields a self-updating assignee (no TASK_MANAGE) may touch.
_SELF_UPDATE_FIELDS = {"status", "updates", "issues"}
_MANAGE_FIELDS = {"title", "area", "status", "assignee_id", "start_date",
                  "end_date", "updates", "issues", "entity_type", "entity_id"}


class DeploymentError(ValueError):
    """Message is safe to show the user."""


def _user_dict(user: User | None) -> dict | None:
    if user is None:
        return None
    return {"id": str(user.id), "full_name": user.full_name, "email": user.email}


def _task_dict(task: DeploymentTask, users_by_id: dict[uuid.UUID, User]) -> dict:
    today = date.today()
    overdue = bool(task.end_date and task.end_date < today and task.status != "done")
    return {
        "id": str(task.id),
        "project_id": str(task.project_id),
        "title": task.title,
        "area": task.area,
        "status": task.status,
        "assignee": _user_dict(users_by_id.get(task.assignee_id)) if task.assignee_id else None,
        "start_date": task.start_date.isoformat() if task.start_date else None,
        "end_date": task.end_date.isoformat() if task.end_date else None,
        "overdue": overdue,
        "updates": task.updates,
        "issues": task.issues,
        "has_issue": bool(task.issues and task.issues.strip()),
        "entity_type": task.entity_type,
        "entity_id": str(task.entity_id) if task.entity_id else None,
        "created_by": _user_dict(users_by_id.get(task.created_by_id)) if task.created_by_id else None,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
    }


def _load_users(db: Session, organisation_id: uuid.UUID,
                tasks: list[DeploymentTask]) -> dict[uuid.UUID, User]:
    ids = {t.assignee_id for t in tasks if t.assignee_id}
    ids |= {t.created_by_id for t in tasks if t.created_by_id}
    if not ids:
        return {}
    rows = db.scalars(select(User).where(User.id.in_(ids),
                                         User.organisation_id == organisation_id))
    return {u.id: u for u in rows}


def list_tasks(db: Session, project: Project, *, area: str | None = None,
               status: str | None = None, assignee_id: uuid.UUID | None = None,
               ) -> list[dict]:
    stmt = select(DeploymentTask).where(DeploymentTask.project_id == project.id)
    if area:
        stmt = stmt.where(DeploymentTask.area == area)
    if status:
        stmt = stmt.where(DeploymentTask.status == status)
    if assignee_id:
        stmt = stmt.where(DeploymentTask.assignee_id == assignee_id)
    stmt = stmt.order_by(DeploymentTask.area, DeploymentTask.created_at)
    tasks = list(db.scalars(stmt))
    users = _load_users(db, project.organisation_id, tasks)
    return [_task_dict(t, users) for t in tasks]


def summary(db: Session, project: Project) -> dict:
    tasks = list(db.scalars(
        select(DeploymentTask).where(DeploymentTask.project_id == project.id)))
    today = date.today()
    by_area: dict[str, dict[str, int]] = {a: {s: 0 for s in TASK_STATUSES} for a in TASK_AREAS}
    by_status = {s: 0 for s in TASK_STATUSES}
    overdue = 0
    open_issues = 0
    for t in tasks:
        by_area.setdefault(t.area, {s: 0 for s in TASK_STATUSES})
        by_area[t.area][t.status] = by_area[t.area].get(t.status, 0) + 1
        by_status[t.status] = by_status.get(t.status, 0) + 1
        if t.end_date and t.end_date < today and t.status != "done":
            overdue += 1
        if t.issues and t.issues.strip():
            open_issues += 1
    return {
        "total": len(tasks),
        "by_area": by_area,
        "by_status": by_status,
        "overdue": overdue,
        "open_issues": open_issues,
        "percent_done": round(100 * by_status.get("done", 0) / len(tasks)) if tasks else 0,
    }


def assignable_users(db: Session, project: Project) -> list[dict]:
    rows = db.scalars(
        select(User).where(User.organisation_id == project.organisation_id,
                           User.is_active.is_(True))
        .order_by(User.full_name))
    return [{"id": str(u.id), "full_name": u.full_name, "email": u.email,
            "roles": u.roles} for u in rows]


def _get(db: Session, project: Project, task_id: uuid.UUID) -> DeploymentTask:
    task = db.scalar(select(DeploymentTask).where(
        DeploymentTask.id == task_id, DeploymentTask.project_id == project.id))
    if task is None:
        raise DeploymentError("Task not found.")
    return task


def _validate_common(payload: dict) -> None:
    if "area" in payload and payload["area"] not in TASK_AREAS:
        raise DeploymentError(f"area must be one of {', '.join(TASK_AREAS)}.")
    if "status" in payload and payload["status"] not in TASK_STATUSES:
        raise DeploymentError(f"status must be one of {', '.join(TASK_STATUSES)}.")
    if payload.get("entity_type") and payload["entity_type"] not in TASK_ENTITY_TYPES:
        raise DeploymentError(f"entity_type must be one of {', '.join(TASK_ENTITY_TYPES)}.")
    start, end = payload.get("start_date"), payload.get("end_date")
    if start and end and start > end:
        raise DeploymentError("start_date must not be after end_date.")


def create_task(db: Session, user: User, project: Project, payload: dict) -> dict:
    title = (payload.get("title") or "").strip()
    if not title:
        raise DeploymentError("title is required.")
    _validate_common(payload)
    assignee_id = payload.get("assignee_id")
    if assignee_id:
        assignee = db.get(User, assignee_id)
        if assignee is None or assignee.organisation_id != project.organisation_id:
            raise DeploymentError("assignee_id is not a user in this organisation.")
    task = DeploymentTask(
        project_id=project.id, title=title, area=payload.get("area", "other"),
        status=payload.get("status", "not_started"), assignee_id=assignee_id,
        start_date=payload.get("start_date"), end_date=payload.get("end_date"),
        updates=payload.get("updates"), issues=payload.get("issues"),
        entity_type=payload.get("entity_type"), entity_id=payload.get("entity_id"),
        created_by_id=user.id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    users = _load_users(db, project.organisation_id, [task])
    return _task_dict(task, users)


def update_task(db: Session, user: User, project: Project, task_id: uuid.UUID,
                payload: dict) -> dict:
    task = _get(db, project, task_id)
    can_manage = has_permission(user.roles, Permission.TASK_MANAGE)
    is_own_task = task.assignee_id is not None and task.assignee_id == user.id

    if not can_manage and not is_own_task:
        raise DeploymentError(
            "You can only update status, updates or issues on a task assigned to you.")

    allowed = _MANAGE_FIELDS if can_manage else _SELF_UPDATE_FIELDS
    extra = set(payload) - allowed
    if extra and not can_manage:
        raise DeploymentError(
            f"You can only change {', '.join(sorted(_SELF_UPDATE_FIELDS))} on your own tasks "
            f"(tried to change {', '.join(sorted(extra))}).")

    _validate_common({k: v for k, v in payload.items() if k in allowed})

    if "assignee_id" in payload and payload["assignee_id"]:
        assignee = db.get(User, payload["assignee_id"])
        if assignee is None or assignee.organisation_id != project.organisation_id:
            raise DeploymentError("assignee_id is not a user in this organisation.")

    for field_name in allowed:
        if field_name in payload:
            value = payload[field_name]
            if field_name == "title" and not (value or "").strip():
                raise DeploymentError("title cannot be empty.")
            setattr(task, field_name, value)

    db.commit()
    db.refresh(task)
    users = _load_users(db, project.organisation_id, [task])
    return _task_dict(task, users)


def delete_task(db: Session, project: Project, task_id: uuid.UUID) -> None:
    task = _get(db, project, task_id)
    db.delete(task)
    db.commit()
