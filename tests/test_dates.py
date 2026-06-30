"""Unit tests for date normalization (-> "YYYY-MM") and range splitting."""

from __future__ import annotations

import pytest

from transformer.normalize.dates import normalize_year_month, parse_date_range


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Jan 2021", "2021-01"),
        ("January 2021", "2021-01"),
        ("2021-03", "2021-03"),
        ("2018-12", "2018-12"),
        ("March 2020", "2020-03"),
        # Year-only -> documented convention: month defaults to 01.
        ("2019", "2019-01"),
        ("03/2021", "2021-03"),
    ],
)
def test_normalize_year_month(raw: str, expected: str) -> None:
    assert normalize_year_month(raw) == expected


@pytest.mark.parametrize("raw", ["Present", "current", "now", "ongoing"])
def test_present_tokens_are_none(raw: str) -> None:
    assert normalize_year_month(raw) is None


@pytest.mark.parametrize("raw", [None, "", "Summer 2019", "Q1 2020", "manager", "tbd"])
def test_unparseable_returns_none(raw: str | None) -> None:
    assert normalize_year_month(raw) is None


@pytest.mark.parametrize("raw", ["May", "Monday", "5pm", "12:30", "noon", "March"])
def test_no_year_in_input_is_never_invented(raw: str) -> None:
    # A month/weekday/time token must NOT borrow the fixed-default year and
    # fabricate a date — that would put a fake date on a candidate's timeline.
    assert normalize_year_month(raw) is None


def test_determinism_no_today_bleed() -> None:
    # The whole point of the fixed default: a year-only token is stable.
    assert normalize_year_month("2019") == "2019-01"
    assert normalize_year_month("2019") == normalize_year_month("2019")


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Jan 2021 - Present", ("2021-01", None)),
        ("Jan 2021 – Present", ("2021-01", None)),  # en dash
        ("2019-2021", ("2019-01", "2021-01")),
        ("2019 to 2021", ("2019-01", "2021-01")),
        ("2019 — 2021", ("2019-01", "2021-01")),  # em dash
        # A single YYYY-MM must NOT be misread as a range.
        ("2021-03", ("2021-03", None)),
        ("Mar 2020", ("2020-03", None)),
        ("garbage", (None, None)),
        (None, (None, None)),
    ],
)
def test_parse_date_range(raw: str | None, expected: tuple[str | None, str | None]) -> None:
    assert parse_date_range(raw) == expected
