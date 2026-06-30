"""Date normalization -> ``"YYYY-MM"`` strings, plus date-range splitting.

Two deterministic helpers:

* :func:`normalize_year_month` — one messy date token -> ``"YYYY-MM"`` or ``None``.
* :func:`parse_date_range` — one range string (``"Jan 2021 - Present"``,
  ``"2019-2021"``) -> ``(start, end)`` where ``end`` is ``None`` for "present".

**The determinism trap we avoid:** ``dateutil.parser.parse`` fills *missing*
components from a ``default`` datetime, and that default is ``datetime.now()``
unless you override it.  Parsing ``"2019"`` on different days would otherwise
yield different months.  We pass a *fixed* sentinel default so the same input
always maps to the same output.

**Documented convention:** a year-only token (``"2019"``) has no month, so we
emit ``"2019-01"``.  This is a deliberate, documented normalization (the schema
requires ``YYYY-MM``); it is recorded under the ``date_parse`` provenance method
so it stays traceable.
"""

from __future__ import annotations

import re
import warnings
from datetime import datetime

from dateutil import parser as _dateparser

# Fixed default: only the day is ever taken from here (year/month come from the
# input when present). Using a constant — never datetime.now() — is what makes
# parsing deterministic. Month defaults to 01 for year-only inputs.
_FIXED_DEFAULT = datetime(2000, 1, 1)

# Tokens that mean "ongoing" -> represented as end == None (never a fake date).
_PRESENT_TOKENS = {
    "present",
    "current",
    "currently",
    "now",
    "ongoing",
    "to date",
    "todate",
    "till date",
    "tilldate",
    "to present",
    "date",
}

# Any unicode dash variant normalized to a plain hyphen before range splitting.
_DASHES = {"–": "-", "—": "-", "−": "-", "‐": "-", "‒": "-"}

# Compact range with no surrounding spaces, both sides whole years: "2019-2021".
_COMPACT_RANGE = re.compile(r"^\s*(\d{4})\s*-\s*(\d{4}|present|current|now)\s*$", re.IGNORECASE)

# Spaced range separators: "Jan 2021 - Present", "2019 to 2021".
_SPACED_RANGE = re.compile(r"^(.+?)\s+(?:-|to|through|until)\s+(.+)$", re.IGNORECASE)

# Plausible calendar bounds — rejects absurd parses (e.g. a stray "12" that
# dateutil might interpret using the default year).
_MIN_YEAR, _MAX_YEAR = 1900, 2100


def _normalize_dashes(text: str) -> str:
    for bad, good in _DASHES.items():
        text = text.replace(bad, good)
    return text


def normalize_year_month(raw: str | None) -> str | None:
    """Parse one date token into ``"YYYY-MM"``; return ``None`` if not a date.

    Present-like tokens ("Present", "current", ...) return ``None`` (the caller
    interprets that as ongoing).  Anything dateutil can't parse, or that lands
    outside :data:`_MIN_YEAR`..:data:`_MAX_YEAR`, returns ``None``.
    """

    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    if text.lower() in _PRESENT_TOKENS:
        return None

    try:
        with warnings.catch_warnings():
            # dateutil emits UnknownTimezoneWarning on some garbage tokens; we
            # reject those below anyway, so the warning is just noise.
            warnings.simplefilter("ignore")
            dt = _dateparser.parse(text, default=_FIXED_DEFAULT)
    except (ValueError, OverflowError, TypeError):
        # dateutil raises ParserError (a ValueError subclass) on non-dates.
        return None

    if not (_MIN_YEAR <= dt.year <= _MAX_YEAR):
        return None

    # Critical guard: dateutil fills MISSING components from the fixed default,
    # so a month-only ("May"), weekday ("Monday"), or time-only ("5pm") token
    # would otherwise borrow the default YEAR and fabricate a date. Require the
    # resolved year to actually appear in the input — never invent a year.
    if str(dt.year) not in text:
        return None

    return f"{dt.year:04d}-{dt.month:02d}"


def parse_date_range(raw: str | None) -> tuple[str | None, str | None]:
    """Split a range string into ``(start, end)`` as ``"YYYY-MM"`` / ``None``.

    Examples::

        "Jan 2021 - Present" -> ("2021-01", None)
        "2019-2021"          -> ("2019-01", "2021-01")
        "2019 to 2021"       -> ("2019-01", "2021-01")
        "Mar 2020"           -> ("2020-03", None)   # single date -> start only
        "garbage"            -> (None, None)
    """

    if raw is None:
        return (None, None)
    text = _normalize_dashes(raw.strip())
    if not text:
        return (None, None)

    # Try compact "YYYY-YYYY" first (so "2021-03" is NOT misread as a range).
    m = _COMPACT_RANGE.match(text)
    if m:
        return (normalize_year_month(m.group(1)), normalize_year_month(m.group(2)))

    # Then spaced separators ("- ", " to ", ...). The separator must be flanked
    # by whitespace, so a single "2021-03" never matches here.
    m = _SPACED_RANGE.match(text)
    if m:
        return (normalize_year_month(m.group(1)), normalize_year_month(m.group(2)))

    # No range -> treat the whole thing as a single (start) date.
    return (normalize_year_month(text), None)
