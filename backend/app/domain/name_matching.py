"""Street name similarity.

Where a road already carries a name, comparing names is far stronger evidence
than comparing lengths — "N Okonjo-Iweala Way" against "Ngozi Okonjo-Iweala"
is obvious to a person and to token overlap, and invisible to a length test.
"""
import re
import unicodedata
from difflib import SequenceMatcher

# Road-type words carry no identifying information; two different streets both
# ending in "Crescent" are not thereby similar.
_SUFFIXES = {
    "street", "str", "st", "crescent", "cres", "close", "cl", "road", "rd",
    "way", "avenue", "ave", "boulevard", "blvd", "drive", "dr", "lane", "ln",
    "court", "ct", "place", "pl", "expressway", "highway", "link", "extension",
}
# Honorifics and initials vary between sources and surveyors.
_NOISE = {"dr", "chief", "sir", "alhaji", "hon", "engr", "prof", "mr", "mrs"}


def normalise(name: str) -> str:
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    text = text.lower().replace("&", " and ")
    return re.sub(r"[^a-z0-9\s]", " ", text)


def tokens(name: str) -> list[str]:
    out = []
    for token in normalise(name).split():
        if token in _SUFFIXES or token in _NOISE:
            continue
        if len(token) == 1:          # a bare initial, e.g. "N" in "N Okonjo"
            continue
        out.append(token)
    return out


def similarity(a: str, b: str) -> float:
    """0.0 to 1.0. Token overlap dominates; sequence ratio breaks ties."""
    ta, tb = set(tokens(a)), set(tokens(b))
    if not ta or not tb:
        return 0.0

    exact = ta & tb
    jaccard = len(exact) / len(ta | tb)

    # Partial credit for near-identical tokens. 0.75 admits single-character
    # transpositions — "Anyim Plus Anyim" for "Anyim Pius Anyim" is a surveyor
    # mishearing, not a different street — while still rejecting unrelated
    # surnames of similar length.
    partial = 0.0
    for x in ta - exact:
        best = max((SequenceMatcher(None, x, y).ratio() for y in tb - exact),
                   default=0.0)
        if best >= 0.75:
            partial += best
    coverage = (len(exact) + partial) / max(len(ta), len(tb))

    whole = SequenceMatcher(None, " ".join(sorted(ta)),
                            " ".join(sorted(tb))).ratio()
    return round(min(1.0, 0.5 * jaccard + 0.35 * coverage + 0.15 * whole), 3)


def is_strong(score: float) -> bool:
    return score >= 0.60


def is_possible(score: float) -> bool:
    return score >= 0.35


# Abbreviations expand to a canonical form so that "Ameh Ebute St" and
# "Ameh Ebute Street" merge, while "Ameh Ebute Close" — a genuinely different
# road — does not. Dropping the suffix entirely would merge all three.
_CANONICAL_SUFFIX = {
    "st": "street", "str": "street", "street": "street",
    "cres": "crescent", "crest": "crescent", "crescent": "crescent",
    "cl": "close", "close": "close",
    "rd": "road", "road": "road",
    "ave": "avenue", "av": "avenue", "avenue": "avenue",
    "blvd": "boulevard", "boulevard": "boulevard", "bvd": "boulevard",
    "dr": "drive", "drive": "drive",
    "ln": "lane", "lane": "lane",
    "ct": "court", "court": "court",
    "pl": "place", "place": "place",
    "way": "way", "link": "link", "expressway": "expressway",
}


def merge_key(name: str) -> str:
    """Identity key for deciding whether two records are the same street.

    Deliberately stricter than `similarity`: this drives automatic merging, so
    it must not join two roads that merely resemble each other.
    """
    words = [w for w in normalise(name).split() if w and w not in _NOISE]
    if not words:
        return ""
    words = [_CANONICAL_SUFFIX.get(w, w) for w in words]
    return " ".join(words)
