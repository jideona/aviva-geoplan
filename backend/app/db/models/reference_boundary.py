"""Cached ward/district boundaries pulled from public reference sources
(GRID3's ward FeatureServer, OSM's admin_level=7 district relations).

Deliberately NOT project-scoped or organisation-scoped: this is public
geodata, the same polygon serves every project that happens to sit in that
ward or district. A row here means "we already fetched this once" — the
whole point is that after the first fetch, nothing here ever touches the
network again unless a caller explicitly asks for a refresh. That is the
lesson from GRID3's old GeoServer endpoint going NXDOMAIN out from under us:
live reference-data dependencies rot silently, so fetch once and keep it.
"""
from geoalchemy2 import Geometry
from sqlalchemy import DateTime, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, TimestampMixin, UUIDMixin

REFERENCE_KINDS = ("ward", "district")
REFERENCE_SOURCES = ("grid3_wards", "osm_admin")


class ReferenceBoundary(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "reference_boundary"

    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    # Lowercased, punctuation-stripped form of `name`, used for lookup so
    # "Wuse II" and "wuse-ii" resolve to the same cached row.
    name_normalized: Mapped[str] = mapped_column(
        String(150), nullable=False, index=True)
    state_code: Mapped[str] = mapped_column(String(10), nullable=False)
    lga_name: Mapped[str | None] = mapped_column(String(100))

    source: Mapped[str] = mapped_column(String(30), nullable=False)
    # wardcode for GRID3, OSM relation id for osm_admin — whatever lets a
    # human trace this row back to the exact upstream record.
    source_ref: Mapped[str] = mapped_column(String(200), nullable=False)

    geom: Mapped[object] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326, spatial_index=True),
        nullable=False)
    area_sqkm: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    fetched_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False)
