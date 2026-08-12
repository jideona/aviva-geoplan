"""Coordinate reference system policy (SAD ADR-001).

All geometry is stored in EPSG:4326. Measurement is performed in a project
metric CRS. Area or length computed in degrees is meaningless, so every
measuring helper here requires an explicit metric EPSG code.
"""
from pyproj import CRS, Transformer
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform

STORAGE_EPSG = 4326

# Sensible metric defaults. UTM 32N covers the FCT; Minna / Nigeria Mid Belt is
# used where alignment with Nigerian survey control is required.
METRIC_CRS_BY_REGION = {
    "NG-FCT": 32632,
    "NG-MIDBELT": 26392,
    "NG-WEST": 26391,
    "NG-EAST": 26393,
}
DEFAULT_METRIC_EPSG = 32632


def _transformer(src: int, dst: int) -> Transformer:
    return Transformer.from_crs(CRS.from_epsg(src), CRS.from_epsg(dst), always_xy=True)


def to_metric(geom: BaseGeometry, metric_epsg: int) -> BaseGeometry:
    """Project a stored (EPSG:4326) geometry into a metric CRS."""
    if metric_epsg == STORAGE_EPSG:
        raise ValueError("EPSG:4326 is not a metric CRS; measurement would be in degrees")
    return transform(_transformer(STORAGE_EPSG, metric_epsg).transform, geom)


def area_sqm(geom: BaseGeometry, metric_epsg: int) -> float:
    return float(to_metric(geom, metric_epsg).area)


def length_m(geom: BaseGeometry, metric_epsg: int) -> float:
    return float(to_metric(geom, metric_epsg).length)


def is_metric(epsg: int) -> bool:
    try:
        crs = CRS.from_epsg(epsg)
    except Exception:
        return False
    units = {ax.unit_name for ax in crs.axis_info}
    return bool(units) and units.issubset({"metre", "meter"})
