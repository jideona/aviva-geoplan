"""Import and match field-survey data (route-analysis workbook)."""
import uuid
from datetime import date

from geoalchemy2.shape import to_shape
from shapely.ops import transform
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.building import Building
from app.db.models.media import MediaAsset
from app.db.models.project import Project
from app.db.models.boundary import ProjectBoundary
from app.db.models.street import Street
from app.db.models.survey_data import PremisesObservation, RecordedStreet
from app.db.models.user import User
from app.domain.crs import STORAGE_EPSG, _transformer
from app.domain.name_matching import is_possible, is_strong, similarity
from app.domain.naming import NameSource
from app.domain.premises_model import (Observation, Typology, district_total,
                                       fit, sampling_bias)
from app.domain.route_analysis import WorkbookParseError, parse
from app.services import audit_service, naming_service


class FieldDataError(ValueError):
    """Message is safe to show the user."""


def import_workbook(db: Session, user: User, project: Project, filename: str,
                    data: bytes, survey_date: date | None = None,
                    surveyor: str | None = None) -> dict:
    try:
        streets, estates = parse(data)
    except WorkbookParseError as exc:
        raise FieldDataError(str(exc)) from exc

    existing = {r.name.strip().lower() for r in db.scalars(
        select(RecordedStreet).where(RecordedStreet.project_id == project.id))}

    added_streets = 0
    for s in streets:
        if s.name.strip().lower() in existing:
            continue
        db.add(RecordedStreet(
            project_id=project.id, name=s.name, recorded_length_m=s.length_m,
            survey_date=survey_date, surveyor=surveyor, source_file=filename,
            match_status="unmatched"))
        existing.add(s.name.strip().lower())
        added_streets += 1

    # Observations are replaced per source file rather than merged, so a
    # corrected workbook supersedes cleanly.
    db.query(PremisesObservation).filter(
        PremisesObservation.project_id == project.id,
        PremisesObservation.source_file == filename).delete()

    added_obs = 0
    for e in estates:
        db.add(PremisesObservation(
            project_id=project.id, estate_name=e.estate_name,
            building_count=e.building_count,
            units_per_building=e.units_per_building, typology=e.typology,
            street_hint=e.street_hint, survey_date=survey_date,
            surveyor=surveyor, source_file=filename,
            verification_state="field_observed"))
        added_obs += 1

    result = {
        "recorded_streets_added": added_streets,
        "recorded_streets_skipped": len(streets) - added_streets,
        "premises_observations": added_obs,
        "buildings_observed": sum(e.building_count for e in estates),
        "units_observed": sum(e.building_count * e.units_per_building
                              for e in estates),
    }
    audit_service.record(
        db, actor=user, entity_type="project", entity_id=project.id,
        action="import_field_data", project_id=project.id,
        changes={"file": {"before": None, "after": filename},
                 "result": {"before": None, "after": result}},
    )
    db.commit()
    return result


# --------------------------------------------------------------------------
# Street name matching
# --------------------------------------------------------------------------

def candidates(db: Session, project: Project, recorded_id: uuid.UUID,
               tolerance: float = 0.25, limit: int = 12) -> dict:
    """Roads that could be this recorded street.

    Named roads are included, not excluded. A recorded street may already carry
    a name in OpenStreetMap, and where it does, comparing names is far stronger
    evidence than comparing lengths.

    Length is a weak and sometimes misleading signal: a street crossing the
    district boundary is measured here only within it, while the surveyor
    recorded the whole street. Roads touching the boundary are flagged and
    their length delta is not held against them.
    """
    rec = db.scalar(select(RecordedStreet).where(
        RecordedStreet.id == recorded_id,
        RecordedStreet.project_id == project.id))
    if rec is None:
        raise FieldDataError("Recorded street not found.")

    boundary = db.scalar(select(ProjectBoundary).where(
        ProjectBoundary.project_id == project.id,
        ProjectBoundary.is_current.is_(True)))
    edge = None
    if boundary is not None:
        # A road within a few metres of the boundary is very likely clipped.
        edge = transform(
            _transformer(STORAGE_EPSG, project.metric_crs_epsg).transform,
            to_shape(boundary.geom)).boundary

    target = float(rec.recorded_length_m) if rec.recorded_length_m else None
    to_metric = _transformer(STORAGE_EPSG, project.metric_crs_epsg).transform

    rows = []
    for st in db.scalars(select(Street).where(Street.project_id == project.id)):
        length = float(st.length_m)
        geom = transform(to_metric, to_shape(st.geom))
        clipped = bool(edge is not None and geom.distance(edge) < 5.0)

        delta = None if not target else (length - target) / target * 100
        name_score = similarity(rec.name, st.name) if st.name else 0.0

        # Ranking. Name agreement dominates where a name exists; otherwise
        # length proximity orders the shortlist, discounted for clipped roads.
        if name_score:
            rank = 1000 - name_score * 1000
        elif delta is None:
            rank = 900
        else:
            penalty = abs(delta) * (0.35 if clipped else 1.0)
            rank = 500 + penalty

        rows.append({
            "street_id": str(st.id), "street_code": st.street_code,
            "existing_name": st.name, "road_class": st.road_class,
            "length_m": round(length),
            "delta_pct": None if delta is None else round(delta, 1),
            "name_similarity": name_score or None,
            "name_match": "strong" if is_strong(name_score) else (
                "possible" if is_possible(name_score) else None),
            "crosses_boundary": clipped,
            "_rank": rank,
        })

    rows.sort(key=lambda r: r["_rank"])
    shortlist = rows[:limit]
    # Always surface a strong name match, even if it fell outside the cut.
    for r in rows:
        if r["name_match"] == "strong" and r not in shortlist:
            shortlist.insert(0, r)
    for r in shortlist:
        r.pop("_rank", None)

    strong = [r for r in shortlist if r["name_match"] == "strong"]
    within = sum(1 for r in rows if r["delta_pct"] is not None
                 and abs(r["delta_pct"]) <= tolerance * 100)

    if strong:
        note = (f"{len(strong)} road already carries a closely matching name. "
                "Confirm it on the map — this is far stronger evidence than "
                "length agreement.")
    else:
        note = (f"No existing name matches. {within} roads are within "
                f"{tolerance * 100:.0f}% of the recorded length, which ranks "
                "the shortlist but does not identify the road. Confirm against "
                "the map.")

    return {
        "recorded": {"id": str(rec.id), "name": rec.name,
                     "recorded_length_m": target,
                     "match_status": rec.match_status},
        "candidates": shortlist,
        "candidates_within_tolerance": within,
        "strong_name_matches": len(strong),
        "note": note,
    }


def confirm_match(db: Session, user: User, project: Project,
                  recorded_id: uuid.UUID, street_id: uuid.UUID) -> dict:
    rec = db.scalar(select(RecordedStreet).where(
        RecordedStreet.id == recorded_id,
        RecordedStreet.project_id == project.id))
    if rec is None:
        raise FieldDataError("Recorded street not found.")
    street = db.scalar(select(Street).where(Street.id == street_id,
                                            Street.project_id == project.id))
    if street is None:
        raise FieldDataError("Street not found.")

    delta = None
    if rec.recorded_length_m and float(rec.recorded_length_m) > 0:
        delta = round((float(street.length_m) - float(rec.recorded_length_m))
                      / float(rec.recorded_length_m) * 100, 2)

    # Where the road already carries a name, record whether the field survey
    # agrees with it rather than silently overwriting.
    prior = street.name
    agreement = similarity(rec.name, prior) if prior else None

    rec.matched_street_id = street.id
    rec.match_status = "confirmed"
    rec.matched_by = user.email
    rec.length_delta_pct = delta

    # The name now carries field provenance — it came from Aviva's own survey.
    parts = ["Matched to field survey record."]
    if delta is not None:
        parts.append(f"Length delta {delta}% (recorded length may span "
                     "districts where the road crosses the boundary).")
    if prior and agreement is not None:
        parts.append(f"Previously named {prior!r} "
                     f"(similarity {agreement}); field survey takes precedence.")
    naming_service.name_street(
        db, user, project, street.id, rec.name,
        NameSource.FIELD_OBSERVED.value, note=" ".join(parts))

    # Photos captured against the recorded street (before it had a confirmed
    # location) now have one — re-point them at the real street so they show
    # up in its gallery on the map, not just on this now-closed matching card.
    moved_media = db.execute(
        MediaAsset.__table__.update()
        .where(MediaAsset.project_id == project.id,
               MediaAsset.entity_type == "recorded_street",
               MediaAsset.entity_id == rec.id)
        .values(entity_type="street", entity_id=street.id)
    ).rowcount

    audit_service.record(
        db, actor=user, entity_type="recorded_street", entity_id=rec.id,
        action="match", project_id=project.id,
        changes={"matched_street_id": {"before": None, "after": str(street.id)},
                 "length_delta_pct": {"before": None, "after": delta},
                 "media_relinked": {"before": None, "after": moved_media}},
    )
    db.commit()
    return {"recorded_id": str(rec.id), "street_id": str(street.id),
            "street_code": street.street_code, "name": rec.name,
            "length_delta_pct": delta, "previous_name": prior,
            "name_agreement": agreement, "media_relinked": moved_media}


def matching_queue(db: Session, project_id: uuid.UUID) -> dict:
    rows = list(db.scalars(select(RecordedStreet)
                           .where(RecordedStreet.project_id == project_id)
                           .order_by(RecordedStreet.recorded_length_m.desc()
                                     .nullslast())))
    return {
        "total": len(rows),
        "confirmed": sum(1 for r in rows if r.match_status == "confirmed"),
        "unmatched": sum(1 for r in rows if r.match_status == "unmatched"),
        "streets": [{"id": str(r.id), "name": r.name,
                     "recorded_length_m": (float(r.recorded_length_m)
                                           if r.recorded_length_m else None),
                     "match_status": r.match_status,
                     "matched_street_id": (str(r.matched_street_id)
                                           if r.matched_street_id else None),
                     "length_delta_pct": (float(r.length_delta_pct)
                                          if r.length_delta_pct is not None
                                          else None)}
                    for r in rows],
    }


# --------------------------------------------------------------------------
# Premises model
# --------------------------------------------------------------------------

def build_model(db: Session, project: Project) -> dict:
    obs_rows = list(db.scalars(select(PremisesObservation)
                               .where(PremisesObservation.project_id == project.id)))
    if not obs_rows:
        return {"available": False,
                "reason": "No premises observations imported yet."}

    # One row is one observation covering many buildings, not many
    # observations. Expanding it would treat a uniform estate design as
    # independent corroboration.
    observations = [
        Observation(units=row.units_per_building,
                    building_count=row.building_count,
                    label=row.estate_name)
        for row in obs_rows
    ]

    version = f"{project.code_prefix}-{len(observations)}obs"
    model = fit(observations, version)

    # Register typology mix. Buildings are unclassified until surveyed, so the
    # comparison is honest about how little of the register is characterised.
    mix_rows = db.execute(
        select(Building.building_type, func.count())
        .where(Building.project_id == project.id)
        .group_by(Building.building_type)).all()
    register_mix: dict[Typology, int] = {}
    unclassified = 0
    for btype, count in mix_rows:
        if btype in {"unclassified", "other"}:
            unclassified += count
        else:
            register_mix[Typology.UNKNOWN] = register_mix.get(
                Typology.UNKNOWN, 0) + count
    if unclassified:
        register_mix[Typology.UNKNOWN] = register_mix.get(
            Typology.UNKNOWN, 0) + unclassified

    bias = sampling_bias(model, register_mix)
    from app.services import walkthrough_service
    coverage = walkthrough_service.survey_coverage(db, project)
    total = district_total(model, register_mix, bias, coverage)

    return {
        "available": True,
        "version": model.version,
        "observations": model.total_observations,
        "buildings_covered": model.total_buildings,
        "bands": {
            t.value: {
                "sample_size": b.sample_size,
                "buildings_covered": b.buildings_covered,
                "replication": b.replication,
                "distinct_estates": b.distinct_estates,
                "median": b.median,
                "mean": b.mean, "p25": b.p25, "p75": b.p75,
                "min": b.minimum, "max": b.maximum,
                "well_evidenced": b.well_evidenced,
            } for t, b in model.bands.items()
        },
        "sampling_bias": bias,
        "spatial_coverage": coverage,
        "district_total": total,
    }


# --------------------------------------------------------------------------
# Estate location — turning observed unit counts into locatable premises
# --------------------------------------------------------------------------

def estate_worklist(db: Session, project: Project) -> dict:
    """Which estates can be located, and which still cannot.

    An estate is locatable when its label names a street, or its name resembles
    a street already in the register — which is what happens when an access way
    is named after the estate it serves. Each unlocked estate converts observed
    unit counts into premises on real buildings.
    """
    observations = list(db.scalars(select(PremisesObservation)
                                   .where(PremisesObservation.project_id == project.id)))
    if not observations:
        return {"available": False,
                "reason": "No premises observations imported yet."}

    streets = [s for s in db.scalars(select(Street).where(
        Street.project_id == project.id, Street.name.isnot(None)))]
    street_names = [(s, s.name or "") for s in streets]

    estates: dict[str, dict] = {}
    for row in observations:
        e = estates.setdefault(row.estate_name, {
            "buildings": 0, "units": 0, "hint": row.street_hint})
        e["buildings"] += row.building_count
        e["units"] += row.building_count * row.units_per_building
        if row.street_hint and not e["hint"]:
            e["hint"] = row.street_hint

    located, pending = [], []
    for name, e in estates.items():
        best_street, best_score = None, 0.0
        probe = e["hint"] or name
        for street, sname in street_names:
            score = similarity(probe, sname)
            if score > best_score:
                best_street, best_score = street, score

        entry = {
            "estate": name, "buildings": e["buildings"], "units": e["units"],
            "street_hint": e["hint"],
            "street_id": str(best_street.id) if best_street else None,
            "street_name": best_street.name if best_street else None,
            "match_score": round(best_score, 2),
        }
        if is_possible(best_score):
            located.append(entry)
        else:
            pending.append(entry)

    pending.sort(key=lambda r: (-r["units"], -r["buildings"]))
    located.sort(key=lambda r: -r["units"])

    return {
        "available": True,
        "estates_total": len(estates),
        "located": len(located),
        "pending": len(pending),
        "units_located": sum(r["units"] for r in located),
        "units_pending": sum(r["units"] for r in pending),
        "buildings_located": sum(r["buildings"] for r in located),
        "buildings_pending": sum(r["buildings"] for r in pending),
        "worklist": pending[:40],
        "located_estates": located[:40],
        "note": (
            "Naming an estate's access way after the estate makes its observed "
            "unit counts locatable. The list is ordered by how many units each "
            "unlocks."
        ),
    }
