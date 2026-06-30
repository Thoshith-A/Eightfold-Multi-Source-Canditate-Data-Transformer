"""Unit tests for phone normalization (local -> E.164)."""

from __future__ import annotations

import pytest

from transformer.normalize.phones import extract_phones, normalize_phone


@pytest.mark.parametrize(
    "raw,expected",
    [
        # Weird US local formats all collapse to the same E.164 number.
        ("(415) 555-0132", "+14155550132"),
        ("415-555-0132", "+14155550132"),
        ("415.555.0132", "+14155550132"),
        ("4155550132", "+14155550132"),
        # Already-international input is parsed region-independently.
        ("+1 415 555 0132", "+14155550132"),
        ("+44 20 7946 0958", "+442079460958"),
    ],
)
def test_local_and_international_to_e164(raw: str, expected: str) -> None:
    assert normalize_phone(raw) == expected


def test_non_us_local_needs_region() -> None:
    # A UK local number only resolves when told the region is GB.
    assert normalize_phone("020 7946 0958", default_region="GB") == "+442079460958"


@pytest.mark.parametrize("raw", [None, "", "   ", "N/A", "call me", "not a phone", "12345"])
def test_garbage_returns_none(raw: str | None) -> None:
    # Unknown / unparseable / invalid -> None, never an exception.
    assert normalize_phone(raw) is None


def test_invalid_but_parseable_is_rejected() -> None:
    # 999-999-9999 parses shape-wise but is not a valid US number.
    assert normalize_phone("(999) 999-9999") is None


def test_determinism() -> None:
    assert normalize_phone("(415) 555-0132") == normalize_phone("(415) 555-0132")


def test_extract_phones_from_free_text() -> None:
    text = "Best reached at 415-555-0132 or, after hours, +1 (212) 736-5000. Cheers!"
    assert extract_phones(text) == ["+12127365000", "+14155550132"]  # sorted, deduped


def test_extract_phones_empty() -> None:
    assert extract_phones(None) == []
    assert extract_phones("no numbers here") == []
