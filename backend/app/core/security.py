"""Password hashing and JWT issue/verify."""
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import (InvalidHashError, VerificationError,
                               VerifyMismatchError)

from app.core.config import get_settings

_hasher = PasswordHasher()
ALGORITHM = "HS256"


def hash_password(raw: str) -> str:
    return _hasher.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, raw)
    # VerifyMismatchError = wrong password. InvalidHashError = the stored hash
    # is not a parseable argon2 hash (e.g. a legacy bcrypt hash). Both mean
    # "not authenticated" — never a 500. Failing closed here keeps a corrupt or
    # legacy hash from taking the whole login endpoint down.
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def is_valid_hash(hashed: str) -> bool:
    """Whether a stored hash can be parsed by the current hasher — used by the
    seed to detect and repair legacy/corrupt admin hashes."""
    try:
        _hasher.check_needs_rehash(hashed)
        return True
    except Exception:
        return False


def needs_rehash(hashed: str) -> bool:
    return _hasher.check_needs_rehash(hashed)


def create_token(subject: UUID, kind: Literal["access", "refresh"]) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    delta = (timedelta(minutes=s.jwt_access_minutes) if kind == "access"
             else timedelta(days=s.jwt_refresh_days))
    payload: dict[str, Any] = {
        "sub": str(subject),
        "typ": kind,
        "iat": int(now.timestamp()),
        "exp": int((now + delta).timestamp()),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str, expect: Literal["access", "refresh"]) -> UUID | None:
    """Return the subject, or None if the token is invalid or the wrong kind."""
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    if payload.get("typ") != expect:
        return None
    try:
        return UUID(payload["sub"])
    except (KeyError, ValueError):
        return None
