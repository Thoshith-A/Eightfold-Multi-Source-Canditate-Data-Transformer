"""Unit tests for the location-string parser."""

from __future__ import annotations

import pytest

from transformer.normalize.location import parse_location_string


@pytest.mark.parametrize(
    "raw,city,region,country",
    [
        ("SF, CA, USA", "SF", "CA", "US"),
        ("San Francisco, California, United States", "San Francisco", "California", "US"),
        ("London, UK", "London", None, "GB"),
        ("Bengaluru, India", "Bengaluru", None, "IN"),
        ("USA", None, None, "US"),
        ("Remote", "Remote", None, None),
        # The disambiguation that matters: trailing "CA" is California, not Canada.
        ("San Francisco, CA", "San Francisco", "CA", None),
    ],
)
def test_parse_location_string(raw, city, region, country) -> None:
    parsed = parse_location_string(raw)
    assert (parsed.city, parsed.region, parsed.country) == (city, region, country)


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_empty_location(raw) -> None:
    parsed = parse_location_string(raw)
    assert (parsed.city, parsed.region, parsed.country) == (None, None, None)
