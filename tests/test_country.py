"""Unit tests for country normalization (-> ISO-3166-1 alpha-2)."""

from __future__ import annotations

import pytest

from transformer.normalize.country import normalize_country


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("US", "US"),
        ("us", "US"),
        ("USA", "US"),
        ("U.S.A.", "US"),
        ("United States", "US"),
        ("United States of America", "US"),
        ("America", "US"),
        ("UK", "GB"),
        ("U.K.", "GB"),
        ("England", "GB"),
        ("United Kingdom", "GB"),
        ("India", "IN"),
        ("IN", "IN"),
        ("Germany", "DE"),
        ("DEU", "DE"),
        # Location-string convenience: trailing chunk is the country.
        ("SF, CA, USA", "US"),
        ("London, UK", "GB"),
    ],
)
def test_normalize_country(raw: str, expected: str) -> None:
    assert normalize_country(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "   ", "Nowhere", "XYZ", "12345"])
def test_unknown_returns_none(raw: str | None) -> None:
    assert normalize_country(raw) is None


def test_determinism() -> None:
    assert normalize_country("USA") == normalize_country("USA") == "US"
