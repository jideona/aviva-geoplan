from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, TimestampMixin, UUIDMixin


class Organisation(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "organisation"

    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    country: Mapped[str] = mapped_column(String(2), nullable=False, default="NG")
