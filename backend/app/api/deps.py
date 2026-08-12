from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import Permission, has_permission
from app.core.security import decode_token
from app.db.models.user import User
from app.db.session import get_db

DbSession = Annotated[Session, Depends(get_db)]

_UNAUTH = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated.",
    headers={"WWW-Authenticate": "Bearer"},
)


def current_user(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _UNAUTH
    subject = decode_token(authorization.split(" ", 1)[1].strip(), expect="access")
    if subject is None:
        raise _UNAUTH
    user = db.scalar(select(User).where(User.id == subject))
    if user is None or not user.is_active:
        raise _UNAUTH
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require(permission: Permission):
    """Route dependency enforcing a permission server-side."""
    def _guard(user: CurrentUser) -> User:
        if not has_permission(user.roles, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Your role does not permit {permission.value}.",
            )
        return user
    return _guard
