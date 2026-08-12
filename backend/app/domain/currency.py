"""Data currency — how old the evidence behind a record is (SRD FR-IMP-046).

Wuye is still building. A footprint captured in 2023 is a claim about 2023,
and 57% of the current register rests on data that old. Treating age as a
first-class attribute lets it drive where surveyors go, rather than sitting in
a footnote nobody reads.
"""
from dataclasses import dataclass
from datetime import date
from enum import Enum


class Currency(str, Enum):
    CURRENT = "current"        # within a year
    AGEING = "ageing"          # 1–2 years
    STALE = "stale"            # 2–4 years
    OBSOLETE = "obsolete"      # over 4 years
    UNKNOWN = "unknown"        # no source date recorded


@dataclass(frozen=True)
class CurrencyBand:
    max_years: float | None
    label: str
    survey_priority: int  # 1 = visit first
    note: str


BANDS: dict[Currency, CurrencyBand] = {
    Currency.CURRENT: CurrencyBand(
        1.0, "Current", 4,
        "Within a year. Spot-check only."),
    Currency.AGEING: CurrencyBand(
        2.0, "Ageing", 3,
        "One to two years. Verify during the normal walkthrough."),
    Currency.STALE: CurrencyBand(
        4.0, "Stale", 2,
        "Two to four years. Expect missing new build and altered footprints."),
    Currency.OBSOLETE: CurrencyBand(
        None, "Obsolete", 1,
        "Over four years. Treat the geometry as indicative only and re-survey."),
    Currency.UNKNOWN: CurrencyBand(
        None, "Unknown", 1,
        "No source date. Cannot be relied upon without field confirmation."),
}


def age_years(source_date: date | None, today: date) -> float | None:
    if source_date is None:
        return None
    return round((today - source_date).days / 365.25, 2)


def classify(source_date: date | None, today: date) -> Currency:
    age = age_years(source_date, today)
    if age is None:
        return Currency.UNKNOWN
    if age < 1.0:
        return Currency.CURRENT
    if age < 2.0:
        return Currency.AGEING
    if age < 4.0:
        return Currency.STALE
    return Currency.OBSOLETE


def survey_priority(source_date: date | None, today: date) -> int:
    return BANDS[classify(source_date, today)].survey_priority


def requires_field_check(source_date: date | None, today: date) -> bool:
    """Beyond two years the record should not be relied on for a design that
    commits capital without a field check."""
    return classify(source_date, today) in {
        Currency.STALE, Currency.OBSOLETE, Currency.UNKNOWN}
