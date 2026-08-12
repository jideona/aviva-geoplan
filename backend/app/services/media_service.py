"""Photo / video attachments via MinIO object storage.

Two-phase upload keeps big media off the application server:
  1. request_upload  -> creates a MediaAsset row (uploaded=False) and returns a
     presigned PUT URL the device uploads the bytes to directly.
  2. confirm_upload  -> marks the row uploaded once the device reports success.
Viewing returns a short-lived presigned GET URL.

The MinIO client is created lazily and the bucket ensured on first use, so the
API still boots if object storage is briefly unavailable.
"""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models.media import MEDIA_KINDS, MediaAsset
from app.db.models.project import Project
from app.db.models.user import User
from app.services import audit_service

_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/heic": "heic",
        "video/mp4": "mp4", "video/quicktime": "mov"}


class MediaError(ValueError):
    """Message is safe to show the user."""


_client = None


def _minio():
    global _client
    if _client is None:
        from minio import Minio
        s = get_settings()
        _client = Minio(s.minio_endpoint, access_key=s.minio_access_key,
                        secret_key=s.minio_secret_key, secure=s.minio_secure)
        if not _client.bucket_exists(s.minio_bucket):
            _client.make_bucket(s.minio_bucket)
    return _client


def _public_url(url: str) -> str:
    """Rewrite the in-cluster host in a presigned URL to the host-reachable one,
    so a phone off the Docker network can actually use it."""
    s = get_settings()
    return url.replace(f"//{s.minio_endpoint}/", f"//{s.minio_public_endpoint}/")


def request_upload(db: Session, user: User, project: Project, *, entity_type: str,
                   entity_id: uuid.UUID, kind: str, content_type: str,
                   client_id: str | None = None, caption: str | None = None,
                   captured_lat=None, captured_lon=None, captured_at=None,
                   survey_session_id=None) -> dict:
    if kind not in MEDIA_KINDS:
        raise MediaError(f"kind must be one of {', '.join(MEDIA_KINDS)}.")
    # Idempotency: a replayed offline request returns the same asset + URL.
    if client_id:
        existing = db.scalar(select(MediaAsset).where(
            MediaAsset.project_id == project.id, MediaAsset.client_id == client_id))
        if existing is not None:
            return _with_url(existing, put=True)

    ext = _EXT.get(content_type, "bin")
    key = f"{project.id}/{entity_type}/{entity_id}/{uuid.uuid4().hex}.{ext}"
    row = MediaAsset(
        project_id=project.id, entity_type=entity_type, entity_id=entity_id,
        client_id=client_id, kind=kind, object_key=key, content_type=content_type,
        caption=caption, captured_lat=captured_lat, captured_lon=captured_lon,
        captured_at=captured_at or datetime.now(timezone.utc),
        captured_by=user.email, survey_session_id=survey_session_id,
        uploaded=False)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _with_url(row, put=True)


def confirm_upload(db: Session, user: User, project: Project, media_id: uuid.UUID,
                   size_bytes: int | None = None) -> dict:
    row = db.scalar(select(MediaAsset).where(
        MediaAsset.id == media_id, MediaAsset.project_id == project.id))
    if row is None:
        raise MediaError("Media not found.")
    row.uploaded = True
    if size_bytes is not None:
        row.size_bytes = size_bytes
    audit_service.record(db, actor=user, entity_type="media_asset",
                         entity_id=row.id, action="upload_media",
                         project_id=project.id,
                         changes={"entity": {"before": None,
                                             "after": row.entity_type}})
    db.commit()
    return _with_url(row)


def list_for(db: Session, project: Project, entity_type: str,
             entity_id: uuid.UUID) -> list[dict]:
    rows = db.scalars(select(MediaAsset).where(
        MediaAsset.project_id == project.id,
        MediaAsset.entity_type == entity_type,
        MediaAsset.entity_id == entity_id).order_by(MediaAsset.created_at))
    return [_with_url(r) for r in rows if r.uploaded]


def _with_url(row: MediaAsset, put: bool = False) -> dict:
    try:
        c = _minio()
        s = get_settings()
        if put:
            url = c.presigned_put_object(s.minio_bucket, row.object_key,
                                         expires=timedelta(hours=6))
        else:
            url = c.presigned_get_object(s.minio_bucket, row.object_key,
                                         expires=timedelta(hours=6))
        url = _public_url(url)
    except Exception:                                   # noqa: BLE001
        url = None                                       # object storage unavailable
    out = {"id": str(row.id), "entity_type": row.entity_type,
           "entity_id": str(row.entity_id), "kind": row.kind,
           "object_key": row.object_key, "content_type": row.content_type,
           "caption": row.caption, "uploaded": row.uploaded,
           "captured_at": row.captured_at.isoformat() if row.captured_at else None}
    out["upload_url" if put else "view_url"] = url
    return out
