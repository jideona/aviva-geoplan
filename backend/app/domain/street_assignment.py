"""Street assignment (SRD FR-STA-001 to FR-STA-009).

Pure: geometry and parameters in, proposals out. No database.

Every proposal carries a confidence and the reason behind it, because the
output is a proposal for a human to accept, not an answer.
"""
from dataclasses import dataclass

from shapely.geometry.base import BaseGeometry
from shapely.strtree import STRtree


@dataclass(frozen=True)
class AssignmentCandidate:
    """A road, already projected into the project metric CRS."""
    street_id: str
    name: str | None
    class_rank: int
    geometry: BaseGeometry


@dataclass
class AssignmentProposal:
    building_id: str
    street_id: str | None
    distance_m: float
    confidence: float
    reason: str
    needs_field_name: bool = False


@dataclass(frozen=True)
class AssignmentParams:
    max_distance_m: float = 60.0
    # A closer road only wins over a better-classed one by this margin.
    class_tolerance_m: float = 12.0
    # A named road wins over an unnamed one within this margin.
    name_tolerance_m: float = 8.0
    frontage_buffer_m: float = 25.0


def assign(
    buildings: list[tuple[str, BaseGeometry]],
    candidates: list[AssignmentCandidate],
    params: AssignmentParams = AssignmentParams(),
) -> list[AssignmentProposal]:
    """Propose a street for each building.

    `buildings` are (id, access_point) where the access point is the compound
    gate where one is known, the building entrance where that is known, and the
    centroid otherwise — in that order of preference (FR-STA-003).
    """
    if not candidates:
        return [AssignmentProposal(bid, None, float("inf"), 0.0,
                                   "no streets available")
                for bid, _ in buildings]

    geoms = [c.geometry for c in candidates]
    tree = STRtree(geoms)
    out: list[AssignmentProposal] = []

    for bid, access in buildings:
        nearby = tree.query(access.buffer(params.max_distance_m))
        scored = []
        for i in nearby:
            cand = candidates[int(i)]
            d = cand.geometry.distance(access)
            if d > params.max_distance_m:
                continue
            scored.append((d, cand))

        if not scored:
            out.append(AssignmentProposal(
                bid, None, float("inf"), 0.0,
                f"no road within {params.max_distance_m:.0f} m"))
            continue

        scored.sort(key=lambda x: x[0])
        best_d, best = scored[0]

        # A better-classed road slightly further away is usually the address.
        for d, cand in scored[1:]:
            if d - best_d > params.class_tolerance_m:
                break
            if cand.class_rank < best.class_rank:
                best_d, best = d, cand

        # Prefer a named road over an unnamed one at similar distance.
        if best.name is None:
            for d, cand in scored:
                if cand.name and d - best_d <= params.name_tolerance_m:
                    best_d, best = d, cand
                    break

        confidence, reason = _score(best_d, best, scored, params)
        out.append(AssignmentProposal(
            building_id=bid, street_id=best.street_id, distance_m=round(best_d, 2),
            confidence=round(confidence, 3), reason=reason,
            needs_field_name=best.name is None,
        ))
    return out


def _score(distance: float, chosen: AssignmentCandidate,
           scored: list, params: AssignmentParams) -> tuple[float, str]:
    """Confidence falls with distance and with ambiguity between candidates."""
    proximity = max(0.0, 1.0 - distance / params.max_distance_m)

    runners = [d for d, c in scored if c.street_id != chosen.street_id]
    if runners:
        margin = min(runners) - distance
        separation = min(1.0, max(0.0, margin / params.class_tolerance_m))
    else:
        separation = 1.0

    confidence = 0.6 * proximity + 0.4 * separation
    if chosen.name is None:
        # The geometry may be right while the address is still unknown.
        confidence *= 0.75

    if chosen.name is None:
        reason = f"nearest road at {distance:.0f} m — unnamed, needs a field name"
    elif separation < 0.3:
        reason = f"{distance:.0f} m from {chosen.name}, but another road is nearly as close"
    elif proximity > 0.7:
        reason = f"clearly fronts {chosen.name} at {distance:.0f} m"
    else:
        reason = f"nearest named road {chosen.name} at {distance:.0f} m"
    return confidence, reason


def summarise(proposals: list[AssignmentProposal],
              high: float = 0.7, low: float = 0.4) -> dict:
    assigned = [p for p in proposals if p.street_id]
    return {
        "total": len(proposals),
        "assigned": len(assigned),
        "unassigned": len(proposals) - len(assigned),
        "high_confidence": sum(1 for p in assigned if p.confidence >= high),
        "needs_review": sum(1 for p in assigned if low <= p.confidence < high),
        "low_confidence": sum(1 for p in assigned if p.confidence < low),
        "needs_field_name": sum(1 for p in assigned if p.needs_field_name),
    }
