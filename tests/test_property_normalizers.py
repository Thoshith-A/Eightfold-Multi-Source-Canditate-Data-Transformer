"""Property-based tests (Hypothesis) for the five pure normalizers.

These assert UNIVERSAL invariants the brief leans on, over arbitrary input —
not just hand-picked examples. A surfaced counterexample is a real defect to
fix in the normalizer, never a test to weaken. ``derandomize=True`` keeps CI
reproducible (no flakes).
"""

from __future__ import annotations

import re

from hypothesis import given, settings
from hypothesis import strategies as st

from transformer.normalize.country import normalize_country
from transformer.normalize.dates import normalize_year_month, parse_date_range
from transformer.normalize.location import parse_location_string
from transformer.normalize.phones import normalize_phone
from transformer.normalize.skills import canonicalize_skill

SETTINGS = settings(derandomize=True, max_examples=300)

_E164 = re.compile(r"\+[1-9]\d{1,14}")
_YYYY_MM = re.compile(r"\d{4}-(0[1-9]|1[0-2])")
_ALPHA2 = re.compile(r"[A-Z]{2}")

# A mix of arbitrary text and plausible domain-shaped values.
text = st.text(max_size=40)
phoneish = st.from_regex(r"[+(]?[0-9 ()+.\-]{0,18}", fullmatch=True)
dateish = st.from_regex(r"[A-Za-z0-9 /\-]{0,16}", fullmatch=True)


# --- total-ness: NEVER raise on any string input (constraint #2) ----------- #
@SETTINGS
@given(st.one_of(text, phoneish, dateish))
def test_normalizers_never_raise(s: str) -> None:
    normalize_phone(s)
    normalize_year_month(s)
    parse_date_range(s)
    normalize_country(s)
    canonicalize_skill(s)
    parse_location_string(s)


# --- determinism: same input -> same output ------------------------------- #
@SETTINGS
@given(st.one_of(text, phoneish, dateish))
def test_normalizers_are_deterministic(s: str) -> None:
    assert normalize_phone(s) == normalize_phone(s)
    assert normalize_year_month(s) == normalize_year_month(s)
    assert normalize_country(s) == normalize_country(s)
    assert canonicalize_skill(s) == canonicalize_skill(s)
    assert parse_location_string(s) == parse_location_string(s)


# --- format contracts + idempotence --------------------------------------- #
@SETTINGS
@given(st.one_of(phoneish, text))
def test_phone_is_e164_or_none_and_idempotent(s: str) -> None:
    out = normalize_phone(s)
    if out is not None:
        assert _E164.fullmatch(out), out
        assert normalize_phone(out) == out  # idempotent


@SETTINGS
@given(st.one_of(dateish, text))
def test_year_month_format_or_none_and_idempotent(s: str) -> None:
    out = normalize_year_month(s)
    if out is not None:
        assert _YYYY_MM.fullmatch(out), out
        assert normalize_year_month(out) == out


@SETTINGS
@given(text)
def test_country_is_alpha2_or_none_and_idempotent(s: str) -> None:
    out = normalize_country(s)
    if out is not None:
        assert _ALPHA2.fullmatch(out), out
        assert normalize_country(out) == out  # a code round-trips to itself


@SETTINGS
@given(text)
def test_canonicalize_skill_shape(s: str) -> None:
    result = canonicalize_skill(s)
    assert isinstance(result.name, str)
    assert 0.0 <= result.score <= 100.0
    # Canonicalizing an already-canonical name is stable.
    if result.canonical and result.name:
        assert canonicalize_skill(result.name).name == result.name
