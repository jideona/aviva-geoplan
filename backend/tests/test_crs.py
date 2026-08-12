"""Spatial regression fixtures (SAD 11.1).

These guard against the class of bug where geometry is measured in degrees.
A change in any expected value here fails the build.
"""
import pytest
from shapely.geometry import Polygon

from app.domain.crs import DEFAULT_METRIC_EPSG, area_sqm, is_metric, length_m


def _square_at(lon: float, lat: float, side_deg: float) -> Polygon:
    return Polygon([(lon, lat), (lon + side_deg, lat),
                    (lon + side_deg, lat + side_deg), (lon, lat + side_deg)])


def test_wgs84_is_rejected_for_measurement():
    with pytest.raises(ValueError):
        area_sqm(_square_at(7.45, 9.06, 0.01), 4326)


def test_known_area_in_abuja():
    # ~0.01 degree square near Wuye. At this latitude that is roughly 1.1 km
    # per side, so about 1.2 km^2. Tolerance is wide because the point is to
    # catch degree/metre confusion, not to assert survey precision.
    area = area_sqm(_square_at(7.45, 9.06, 0.01), DEFAULT_METRIC_EPSG)
    assert 1_100_000 < area < 1_400_000


def test_perimeter_is_in_metres():
    perimeter = length_m(_square_at(7.45, 9.06, 0.01), DEFAULT_METRIC_EPSG)
    assert 4_200 < perimeter < 4_800


def test_metric_crs_detection():
    assert is_metric(32632)      # UTM 32N
    assert is_metric(26392)      # Minna / Nigeria Mid Belt
    assert not is_metric(4326)   # degrees
