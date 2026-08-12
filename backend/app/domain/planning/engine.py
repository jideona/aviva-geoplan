"""Serving zone clustering and FAT placement.

Stage 1 of the planning engine (SAD Figure 4). Capacitated clustering under a
maximum drop length, then siting each FAT where a cable can actually reach it —
on a road, not in the middle of a compound.

Deterministic by construction: every tie is broken on identifier, so the same
input yields the same design (SRD FR-RTE-011).
"""
import math

from shapely.geometry import Point
from shapely.ops import nearest_points
from shapely.strtree import STRtree

from app.domain.planning.model import (Fdh, PlanningBuilding, PlanningResult,
                                       PlanningRoad, ServingZone)
from app.domain.planning.rules import DesignRules


class PlanningError(ValueError):
    """Message is safe to show the user."""


def plan(buildings: list[PlanningBuilding], roads: list[PlanningRoad],
         rules: DesignRules) -> PlanningResult:
    errors = rules.validate()
    if errors:
        raise PlanningError("; ".join(errors))
    if not buildings:
        raise PlanningError("No buildings to plan for.")

    capacity = rules.usable_ports
    oversized = [b for b in buildings if b.premises > capacity]

    clusters = _cluster(buildings, rules, capacity)
    zones = _place(clusters, roads, rules)
    # Clustering measures drops from the cluster seed, but the FAT is then
    # moved to the road. Buildings can end up beyond the drop limit as a
    # result, so the constraint is re-imposed after siting rather than merely
    # asserted before it.
    zones, evicted = _enforce_drop_limit(zones, buildings, roads, rules, capacity)
    _merge_undersized(zones, rules)

    for index, zone in enumerate(zones, start=1):
        zone.index = index

    served = {bid for z in zones for bid in z.building_ids}
    unassigned = sorted(b.id for b in buildings if b.id not in served)

    warnings: list[str] = []
    assumed = sum(1 for b in buildings if b.premises_is_assumed)
    if assumed:
        warnings.append(
            f"{assumed:,} of {len(buildings):,} buildings have no surveyed or "
            f"modelled premises count and were planned at "
            f"{rules.assumed_premises_per_building} premises each. Zone "
            f"capacity is therefore a lower bound, not a design figure."
        )
    if oversized:
        warnings.append(
            f"{len(oversized)} building(s) exceed a single FAT's usable "
            f"capacity of {capacity} and need a dedicated splitter."
        )
    if unassigned:
        warnings.append(
            f"{len(unassigned)} building(s) could not be placed within "
            f"{rules.max_drop_length_m:.0f} m of any viable FAT position."
        )

    if evicted:
        warnings.append(
            f"{evicted} building(s) were moved between zones so that every "
            f"drop stays within {rules.max_drop_length_m:.0f} m of its FAT."
        )

    fdhs = _cluster_fdh(zones, roads, rules)
    for i, fdh in enumerate(fdhs, start=1):
        fdh.index = i

    premises_served = sum(z.premises for z in zones)
    splitters = _splitter_allocation(premises_served, rules)
    for msg in splitters["warnings"]:
        warnings.append(msg)

    return PlanningResult(
        zones=zones,
        unassigned_building_ids=unassigned,
        engine_version=rules.engine_version,
        rules_applied={
            "split_stage": rules.split_stage,
            "overall_split": rules.overall_split,
            "fdh_split_ratio": rules.fdh_split_ratio,
            "fat_port_count": rules.fat_port_count,
            "spare_port_ratio": rules.spare_port_ratio,
            "usable_ports": capacity,
            "max_drop_length_m": rules.max_drop_length_m,
            "assumed_premises_per_building": rules.assumed_premises_per_building,
        },
        premises_total=sum(b.premises for b in buildings),
        premises_assumed_count=assumed,
        splitter_allocation=splitters,
        fdhs=fdhs,
        warnings=warnings,
    )


def _cluster_fdh(zones: list[ServingZone], roads: list[PlanningRoad],
                 rules: DesignRules) -> list[Fdh]:
    """Group FAT zones into FDH cabinets under the splitter-budget capacity.

    Same capacitated clustering as FAT placement, one tier up: FATs cluster
    instead of buildings, and the capacity is premises per FDH.
    """
    if not zones:
        return []
    capacity = rules.fdh_premises_capacity
    reach = rules.max_fdh_distribution_m

    remaining = {z.code_suffix: z for z in zones}
    def within(z, r):
        return [o for o in remaining.values()
                if z.fat_point.distance(o.fat_point) <= r]

    if rules.noc_anchor is not None:
        # Anchored: build outward from the head-end so the first FDHs sit near
        # the NOC. A connectorised pilot's feeder cannot reach a distant FDH,
        # so the pilot cabinets must be close in.
        from shapely.geometry import Point as _P
        anchor = _P(rules.noc_anchor[0], rules.noc_anchor[1])
        order = sorted(zones, key=lambda z: (anchor.distance(z.fat_point),
                                             z.code_suffix))
    else:
        # Unanchored: seed on the densest FAT.
        order = sorted(zones, key=lambda z: (-len(within(z, reach)), z.code_suffix))

    clusters: list[list[ServingZone]] = []
    for seed in order:
        if seed.code_suffix not in remaining:
            continue
        group = [seed]
        used = seed.premises
        del remaining[seed.code_suffix]
        for cand in sorted((o for o in remaining.values()
                            if seed.fat_point.distance(o.fat_point) <= reach),
                           key=lambda o: (seed.fat_point.distance(o.fat_point),
                                          o.code_suffix)):
            if used + cand.premises > capacity:
                continue
            group.append(cand)
            used += cand.premises
            del remaining[cand.code_suffix]
            if used >= capacity:
                break
        clusters.append(group)

    fdhs = []
    for group in clusters:
        cx = sum(z.fat_point.x for z in group) / len(group)
        cy = sum(z.fat_point.y for z in group) / len(group)
        from shapely.geometry import Point
        centre = Point(cx, cy)
        point, road_id, offset = centre, None, None
        if roads:
            pool = [r for r in roads
                    if r.road_class in rules.prefer_road_classes] or roads
            geoms = [r.geometry for r in pool]
            tree = STRtree(geoms)
            road = pool[int(tree.nearest(centre))]
            snapped, _ = nearest_points(road.geometry, centre)
            point, road_id, offset = snapped, road.id, round(snapped.distance(centre), 1)

        premises = sum(z.premises for z in group)
        fdhs.append(Fdh(
            index=0, point=point,
            fat_codes=sorted(z.code_suffix for z in group),
            premises=premises,
            splitters=rules.splitters_per_fdh,
            splitter_ratio=rules.fdh_split_ratio,
            road_id=road_id, road_offset_m=offset,
            max_distribution_m=round(max(point.distance(z.fat_point) for z in group), 1),
        ))
    return fdhs


def _splitter_allocation(premises: int, rules: DesignRules) -> dict:
    """How many splitters this design needs, and whether stock covers it.

    Single-stage 1:32: one 1:32 splitter per PON port; each serves 32 premises.
    """
    import math

    stock = rules.stock_map
    lines = []
    if rules.split_stage == "single":
        r = rules.fdh_split_ratio
        need = math.ceil(premises / r) if premises else 0
        have = stock.get(r, 0)
        lines.append({"ratio": r, "role": "FDH single-stage",
                      "required": need, "in_stock": have,
                      "gap": max(0, need - have),
                      "surplus": max(0, have - need)})
    else:
        primary = math.ceil(premises / rules.overall_split) if premises else 0
        secondary = math.ceil(premises / rules.fat_split_ratio) if premises else 0
        for ratio, role, need in ((rules.fdh_split_ratio, "FDH primary", primary),
                                  (rules.fat_split_ratio, "FAT secondary", secondary)):
            have = stock.get(ratio, 0)
            lines.append({"ratio": ratio, "role": role, "required": need,
                          "in_stock": have, "gap": max(0, need - have),
                          "surplus": max(0, have - need)})

    warnings = []
    for l in lines:
        if l["gap"]:
            warnings.append(
                f"Splitters: need {l['required']} x 1:{l['ratio']} "
                f"({l['role']}), {l['in_stock']} in stock — buy {l['gap']}.")
    return {"lines": lines, "zero_purchase": all(l["gap"] == 0 for l in lines),
            "warnings": warnings}


def _cluster(buildings: list[PlanningBuilding], rules: DesignRules,
             capacity: int) -> list[list[PlanningBuilding]]:
    """Grow clusters from the densest unassigned point outwards.

    Seeding on local density rather than arbitrary order produces zones centred
    on real clusters of dwellings instead of splitting them across FATs.
    """
    radius = rules.max_drop_length_m
    points = [b.point for b in buildings]
    tree = STRtree(points)

    # Local density: how many other buildings sit within a drop of each.
    density: dict[str, int] = {}
    for b in buildings:
        near = tree.query(b.point.buffer(radius))
        density[b.id] = len(near)

    remaining = {b.id: b for b in buildings}
    # Seed from grouped (estate) buildings first, densest within each, so an
    # estate anchors its own FATs before generic infill starts.
    order = sorted(buildings,
                   key=lambda b: (b.group_id is None, -density[b.id], b.id))
    clusters: list[list[PlanningBuilding]] = []

    for seed in order:
        if seed.id not in remaining:
            continue
        cluster = [seed]
        used = seed.premises
        del remaining[seed.id]

        # Candidates within a drop of the seed. Same-estate buildings come
        # first so an estate fills whole FATs before neighbours are pulled in —
        # otherwise a single estate scatters across several shared FATs.
        candidates = sorted(
            (b for b in remaining.values()
             if seed.point.distance(b.point) <= radius),
            key=lambda b: (b.group_id != seed.group_id,
                           seed.point.distance(b.point), b.id),
        )
        for cand in candidates:
            if used + cand.premises > capacity:
                continue
            cluster.append(cand)
            used += cand.premises
            del remaining[cand.id]
            if used >= capacity:
                break
        clusters.append(cluster)

    return clusters


def _centroid(cluster: list[PlanningBuilding]) -> Point:
    return Point(sum(b.point.x for b in cluster) / len(cluster),
                 sum(b.point.y for b in cluster) / len(cluster))


def _place(clusters: list[list[PlanningBuilding]], roads: list[PlanningRoad],
           rules: DesignRules) -> list[ServingZone]:
    """Site each FAT on the nearest suitable road.

    A FAT in the middle of a block cannot be built. Snapping to a road is the
    minimum viable constraint; kerb lines and chamber positions refine it later.
    """
    preferred = [r for r in roads if r.road_class in rules.prefer_road_classes]
    pool = preferred or roads
    geoms = [r.geometry for r in pool]
    tree = STRtree(geoms) if geoms else None

    zones: list[ServingZone] = []
    for cluster in clusters:
        centre = _centroid(cluster)
        fat_point, road_id, offset = centre, None, None

        if tree is not None:
            idx = tree.nearest(centre)
            road = pool[int(idx)]
            snapped, _ = nearest_points(road.geometry, centre)
            # Always snap. A FAT sits on a pole or in a chamber at the kerb; it
            # is never in the middle of a block. A large offset does not mean
            # "do not snap", it means the drops are long and someone should
            # look at the zone.
            fat_point = snapped
            road_id = road.id
            offset = snapped.distance(centre)

        drops = [fat_point.distance(b.point) for b in cluster]
        zone = ServingZone(
            index=0,
            fat_point=fat_point,
            building_ids=sorted(b.id for b in cluster),
            premises=sum(b.premises for b in cluster),
            max_drop_m=round(max(drops), 1),
            avg_drop_m=round(sum(drops) / len(drops), 1),
            road_id=road_id,
            road_offset_m=None if offset is None else round(offset, 1),
        )
        if offset is not None and offset > rules.max_fat_road_offset_m:
            zone.warnings.append(
                f"Nearest road is {offset:.0f} m away, beyond the "
                f"{rules.max_fat_road_offset_m:.0f} m siting limit. Position "
                "needs manual review.")
        if zone.max_drop_m > rules.max_drop_length_m:
            zone.warnings.append(
                f"Longest drop {zone.max_drop_m:.0f} m exceeds the "
                f"{rules.max_drop_length_m:.0f} m limit after siting.")
        zones.append(zone)

    return zones


def _enforce_drop_limit(zones: list[ServingZone],
                        buildings: list[PlanningBuilding],
                        roads: list[PlanningRoad], rules: DesignRules,
                        capacity: int, max_passes: int = 4
                        ) -> tuple[list[ServingZone], int]:
    """Re-impose the drop limit measured from the sited FAT.

    Buildings beyond the limit are removed from their zone and re-clustered,
    repeatedly, until the design satisfies the constraint it claims to.
    """
    by_id = {b.id: b for b in buildings}
    limit = rules.max_drop_length_m
    moved = 0

    for _ in range(max_passes):
        homeless: list[PlanningBuilding] = []
        for zone in zones:
            keep = []
            for bid in zone.building_ids:
                if zone.fat_point.distance(by_id[bid].point) <= limit:
                    keep.append(bid)
                else:
                    homeless.append(by_id[bid])
            zone.building_ids = keep
        if not homeless:
            break

        moved += len(homeless)
        zones = [z for z in zones if z.building_ids]
        _recompute(zones, by_id)

        # Try an existing zone with room and reach before opening a new one.
        still: list[PlanningBuilding] = []
        for b in sorted(homeless, key=lambda x: x.id):
            options = [z for z in zones
                       if z.fat_point.distance(b.point) <= limit
                       and z.premises + b.premises <= capacity]
            if options:
                target = min(options,
                             key=lambda z: (z.fat_point.distance(b.point),
                                            z.building_ids[0]))
                target.building_ids = sorted(target.building_ids + [b.id])
                target.premises += b.premises
            else:
                still.append(b)
        _recompute(zones, by_id)

        if still:
            zones.extend(_place(_cluster(still, rules, capacity), roads, rules))
        _recompute(zones, by_id)

    # Anything still beyond reach after the repair passes is not servable at
    # this drop length. It leaves the design rather than sitting inside a zone
    # that breaches its own limit — an unassigned building is a known gap, a
    # breaching one is a false claim.
    for zone in zones:
        zone.building_ids = [bid for bid in zone.building_ids
                             if zone.fat_point.distance(by_id[bid].point) <= limit]
    zones = [z for z in zones if z.building_ids]
    _recompute(zones, by_id)
    return zones, moved


def _recompute(zones: list[ServingZone],
               by_id: dict[str, PlanningBuilding]) -> None:
    for zone in zones:
        if not zone.building_ids:
            continue
        drops = [zone.fat_point.distance(by_id[bid].point)
                 for bid in zone.building_ids]
        zone.premises = sum(by_id[bid].premises for bid in zone.building_ids)
        zone.max_drop_m = round(max(drops), 1)
        zone.avg_drop_m = round(sum(drops) / len(drops), 1)


def _merge_undersized(zones: list[ServingZone], rules: DesignRules) -> None:
    """Fold tiny zones into a neighbour rather than building a FAT for two homes."""
    if len(zones) < 2:
        return
    capacity = rules.usable_ports
    small = [z for z in zones if z.premises < rules.min_premises_per_fat]
    for zone in small:
        if zone not in zones:
            continue
        others = [z for z in zones if z is not zone]
        if not others:
            continue
        nearest = min(others, key=lambda z: (z.fat_point.distance(zone.fat_point),
                                             z.building_ids[0]))
        gap = nearest.fat_point.distance(zone.fat_point)
        if (nearest.premises + zone.premises <= capacity
                and gap <= rules.max_drop_length_m):
            nearest.building_ids = sorted(nearest.building_ids + zone.building_ids)
            nearest.premises += zone.premises
            nearest.max_drop_m = round(max(nearest.max_drop_m, gap), 1)
            zones.remove(zone)


def loss_free_span(a: Point, b: Point) -> float:
    """Straight-line distance. Route-following length replaces this at stage 3."""
    return math.hypot(a.x - b.x, a.y - b.y)
