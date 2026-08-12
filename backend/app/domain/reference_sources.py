"""Pure helpers for matching and assembling reference boundary data. No I/O —
bytes/records in, shapely-ready structures out, so this is unit-testable
without a network connection or a database.
"""
import re

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^a-z0-9 ]")
# Words that appear inconsistently across sources ("Wuye" vs "Wuye District")
# and would otherwise stop an exact match from resolving.
_SUFFIXES = re.compile(
    r"\b(district|ward|estate|extension|area council|council)\b")


def normalize_name(name: str) -> str:
    """Lowercase, strip punctuation and common administrative suffixes, and
    collapse whitespace, so 'Wuye District', 'wuye', and 'WUYE  ' all match.
    Deliberately keeps ordinal/number suffixes ('Wuse II', 'Garki 2') since
    those distinguish genuinely different districts, not the same one.
    """
    cleaned = _PUNCT.sub(" ", name.strip().lower())
    cleaned = _SUFFIXES.sub(" ", cleaned)
    return _WS.sub(" ", cleaned).strip()


_ROUND = 7


def _point_key(pt: tuple[float, float]) -> tuple[float, float]:
    return (round(pt[0], _ROUND), round(pt[1], _ROUND))


class RingAssemblyError(ValueError):
    """Raised with a message safe to show to a caller/log."""


def assemble_rings(
    segments: list[list[tuple[float, float]]],
) -> list[list[tuple[float, float]]]:
    """Chain way segments (as returned by an Overpass `out geom;` query, one
    coordinate list per way) into closed polygon rings.

    OSM relation members don't come pre-ordered or consistently wound — two
    adjacent "outer" ways can point in opposite directions — so this walks
    the pool of segments, extending the current ring from either end of the
    next matching segment, until every segment is consumed. A relation with
    more than one disjoint outer ring (an exclave) yields more than one ring.
    Raises if a partially-built ring cannot be closed, since a boundary
    that doesn't close is a real data problem, not something to paper over.
    """
    pool = [list(seg) for seg in segments if len(seg) >= 2]
    rings: list[list[tuple[float, float]]] = []

    while pool:
        ring = pool.pop(0)
        guard = len(pool) + 1  # a segment is consumed each successful step
        while _point_key(ring[0]) != _point_key(ring[-1]):
            if guard <= 0:
                raise RingAssemblyError(
                    "Could not close a ring from the given way segments — "
                    f"{len(pool) + 1} segment(s) left unconsumed with an open end at "
                    f"{ring[-1]!r}."
                )
            guard -= 1
            tail = _point_key(ring[-1])
            for i, seg in enumerate(pool):
                if _point_key(seg[0]) == tail:
                    ring.extend(seg[1:])
                    pool.pop(i)
                    break
                if _point_key(seg[-1]) == tail:
                    ring.extend(list(reversed(seg))[1:])
                    pool.pop(i)
                    break
            else:
                raise RingAssemblyError(
                    "Could not close a ring from the given way segments — no "
                    f"remaining segment continues from {ring[-1]!r}."
                )
        rings.append(ring)

    return rings
