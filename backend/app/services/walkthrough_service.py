"""The field walkthrough pack.

Turns the register into a worklist a surveyor can carry: which streets need a
name, which areas rest on stale data, and which buildings must be confirmed
before a design commits capital.
"""
import uuid
from collections import defaultdict
from datetime import date, timezone, datetime

from geoalchemy2.shape import to_shape
from shapely.ops import transform
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.building import Building
from app.db.models.project import Project
from app.db.models.street import Street
from app.db.models.survey_data import PremisesObservation
from app.domain.name_matching import similarity
from app.domain.crs import STORAGE_EPSG, _transformer
from app.domain.currency import BANDS, Currency, age_years, classify

GRID_M = 250


def _today() -> date:
    return datetime.now(timezone.utc).date()


def currency_report(db: Session, project_id: uuid.UUID) -> dict:
    today = _today()
    rows = db.execute(
        select(Building.source_update_date, func.count())
        .where(Building.project_id == project_id)
        .group_by(Building.source_update_date)
    ).all()

    buckets: dict[str, int] = defaultdict(int)
    ages: list[float] = []
    total = 0
    for source_date, count in rows:
        total += count
        buckets[classify(source_date, today).value] += count
        age = age_years(source_date, today)
        if age is not None:
            ages.extend([age] * count)

    ages.sort()
    needs_check = sum(buckets[c.value] for c in
                      (Currency.STALE, Currency.OBSOLETE, Currency.UNKNOWN))

    return {
        "total": total,
        "by_currency": dict(buckets),
        "median_age_years": ages[len(ages) // 2] if ages else None,
        "oldest_age_years": ages[-1] if ages else None,
        "requires_field_check": needs_check,
        "requires_field_check_pct": (round(needs_check / total * 100, 1)
                                     if total else 0.0),
        "bands": {c.value: {"label": BANDS[c].label,
                            "survey_priority": BANDS[c].survey_priority,
                            "note": BANDS[c].note}
                  for c in Currency},
        "note": (
            "Wuye is still developing. Records older than two years may miss "
            "new build and altered footprints; the survey grid below ranks "
            "where that risk is concentrated."
        ),
    }


def survey_grid(db: Session, project: Project) -> dict:
    """Group buildings into cells and rank them for the walkthrough.

    A surveyor works an area, not a spreadsheet row, so staleness is aggregated
    spatially rather than reported per building.
    """
    today = _today()
    to_metric = _transformer(STORAGE_EPSG, project.metric_crs_epsg).transform

    cells: dict[tuple[int, int], dict] = {}
    for b in db.scalars(select(Building).where(Building.project_id == project.id)):
        pt = transform(to_metric, to_shape(b.centroid))
        key = (int(pt.x // GRID_M), int(pt.y // GRID_M))
        cell = cells.setdefault(key, {"buildings": 0, "ages": [], "unassigned": 0,
                                      "unknown_date": 0, "lon": 0.0, "lat": 0.0})
        cell["buildings"] += 1
        age = age_years(b.source_update_date, today)
        if age is None:
            cell["unknown_date"] += 1
        else:
            cell["ages"].append(age)
        if b.street_id is None:
            cell["unassigned"] += 1
        centroid = to_shape(b.centroid)
        cell["lon"] += centroid.x
        cell["lat"] += centroid.y

    out = []
    for (gx, gy), c in cells.items():
        ages = sorted(c["ages"])
        median = ages[len(ages) // 2] if ages else None
        priority = 1 if (median is None or median >= 4 or c["unknown_date"]) else (
            2 if median >= 2 else 3 if median >= 1 else 4)
        out.append({
            "cell": f"{gx}:{gy}",
            "centre_lon": round(c["lon"] / c["buildings"], 6),
            "centre_lat": round(c["lat"] / c["buildings"], 6),
            "buildings": c["buildings"],
            "median_age_years": median,
            "unknown_date": c["unknown_date"],
            "unassigned": c["unassigned"],
            "survey_priority": priority,
        })
    out.sort(key=lambda r: (r["survey_priority"], -r["buildings"]))

    p1 = [r for r in out if r["survey_priority"] == 1]
    p2 = [r for r in out if r["survey_priority"] == 2]
    return {
        "cell_size_m": GRID_M,
        "cells": out,
        "priority_1_cells": len(p1),
        "priority_1_buildings": sum(r["buildings"] for r in p1),
        "priority_2_cells": len(p2),
        "priority_2_buildings": sum(r["buildings"] for r in p2),
    }


def naming_worklist(db: Session, project_id: uuid.UUID) -> list[dict]:
    """Unnamed streets ranked by dependent buildings, with their provisional
    code — which is what the surveyor writes against in the field."""
    rows = db.execute(
        select(Street, func.count(Building.id))
        .outerjoin(Building, Building.street_id == Street.id)
        .where(Street.project_id == project_id, Street.name.is_(None))
        .group_by(Street.id)
        .order_by(func.count(Building.id).desc())
    ).all()
    return [{
        "street_id": str(s.id),
        "provisional_code": s.street_code,
        "road_class": s.road_class,
        "length_m": float(s.length_m),
        "buildings_depending": n,
    } for s, n in rows]


def survey_coverage(db: Session, project: Project) -> dict:
    """Where in the district unit counts have actually been observed.

    A survey confined to one part of a district can be perfectly accurate and
    still support no district figure. Typology mix does not reveal this —
    a sample can match the register's mix and come entirely from one corner.
    """
    today = _today()
    to_metric = _transformer(STORAGE_EPSG, project.metric_crs_epsg).transform

    observations = list(db.scalars(select(PremisesObservation)
                                   .where(PremisesObservation.project_id == project.id)))
    if not observations:
        return {"available": False,
                "reason": "No premises observations imported yet."}

    # An observation is locatable through the street its estate names.
    streets = [(s, s.name or "") for s in db.scalars(
        select(Street).where(Street.project_id == project.id,
                             Street.name.isnot(None)))]
    located_street_ids: set[uuid.UUID] = set()
    located_units = 0
    for row in observations:
        probe = row.street_hint or row.estate_name
        best, score = None, 0.0
        for street, name in streets:
            sim = similarity(probe, name)
            if sim > score:
                best, score = street, sim
        if best is not None and score >= 0.35:
            located_street_ids.add(best.id)
            located_units += row.building_count * row.units_per_building

    cells: dict[tuple[int, int], dict] = {}
    for b in db.scalars(select(Building).where(Building.project_id == project.id)):
        pt = transform(to_metric, to_shape(b.centroid))
        key = (int(pt.x // GRID_M), int(pt.y // GRID_M))
        cell = cells.setdefault(key, {"buildings": 0, "observed": 0,
                                      "lon": 0.0, "lat": 0.0, "ages": []})
        cell["buildings"] += 1
        if b.street_id in located_street_ids:
            cell["observed"] += 1
        centroid = to_shape(b.centroid)
        cell["lon"] += centroid.x
        cell["lat"] += centroid.y
        age = age_years(b.source_update_date, today)
        if age is not None:
            cell["ages"].append(age)

    rows = []
    for (gx, gy), c in cells.items():
        ages = sorted(c["ages"])
        rows.append({
            "cell": f"{gx}:{gy}",
            "centre_lon": round(c["lon"] / c["buildings"], 6),
            "centre_lat": round(c["lat"] / c["buildings"], 6),
            "buildings": c["buildings"],
            "observed_buildings": c["observed"],
            "coverage_pct": round(c["observed"] / c["buildings"] * 100, 1),
            "median_age_years": ages[len(ages) // 2] if ages else None,
        })

    covered = [r for r in rows if r["coverage_pct"] >= 20]
    uncovered = [r for r in rows if r["coverage_pct"] == 0]
    uncovered.sort(key=lambda r: -r["buildings"])

    total_b = sum(r["buildings"] for r in rows)
    obs_b = sum(r["observed_buildings"] for r in rows)

    return {
        "available": True,
        "cell_size_m": GRID_M,
        "cells_total": len(rows),
        "cells_with_coverage": len(covered),
        "cells_without_coverage": len(uncovered),
        "buildings_total": total_b,
        "buildings_in_surveyed_areas": obs_b,
        "coverage_pct": round(obs_b / total_b * 100, 1) if total_b else 0.0,
        "units_located": located_units,
        "uncovered_cells": uncovered[:30],
        "spatially_representative": len(uncovered) <= len(rows) * 0.25,
        "note": (
            "Survey coverage is concentrated. Premises estimates are defensible "
            "inside surveyed areas and are extrapolation outside them; the "
            "uncovered cells below carry the most buildings and should be "
            "surveyed next."
        ) if len(uncovered) > len(rows) * 0.25 else
        "Survey coverage is spread across the district.",
    }
