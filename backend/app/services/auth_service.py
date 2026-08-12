from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password, needs_rehash, verify_password
from app.db.models.user import User


def authenticate(db: Session, email: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.email == email.lower().strip()))
    if user is None:
        # Hash anyway so that a missing account and a wrong password take a
        # comparable amount of time.
        verify_password(password, "$argon2id$v=19$m=65536,t=3,p=4$"
                                  "c29tZXNhbHRzb21lc2FsdA$0000000000000000000000000000000000000000000")
        return None
    if not user.is_active or not verify_password(password, user.password_hash):
        return None
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
        db.commit()
    return user
