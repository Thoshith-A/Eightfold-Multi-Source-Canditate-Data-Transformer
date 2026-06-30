"""Country normalization -> ISO-3166-1 alpha-2 (e.g. ``"US"``).

Deterministic and offline (``pycountry`` ships a fixed dataset).  We deliberately
**do not** use ``pycountry.search_fuzzy``: it can silently mis-map ambiguous
strings (e.g. "Georgia" the US state vs. the country), which is exactly the kind
of invented data the brief forbids.  Instead we resolve against an exhaustive
*exact* lookup (every alpha-2, alpha-3, name, official name, common name) plus a
small curated alias map for the messy forms people actually type ("USA", "UK",
"England").  No match -> ``None``.
"""

from __future__ import annotations

import functools

import pycountry

# Curated aliases for forms pycountry's official data doesn't carry verbatim.
# Keys are lowercased; punctuation is stripped from the input before lookup, so
# "U.S.A." and "U.K." resolve via "usa"/"uk" here.
_ALIASES: dict[str, str] = {
    # United States
    "usa": "US",
    "us": "US",
    "america": "US",
    "united states of america": "US",
    "states": "US",
    # United Kingdom (pycountry name is "United Kingdom ...")
    "uk": "GB",
    "great britain": "GB",
    "britain": "GB",
    "england": "GB",
    "scotland": "GB",
    "wales": "GB",
    "northern ireland": "GB",
    # Other commonly-typed short forms / informal names
    "uae": "AE",
    "russia": "RU",
    "south korea": "KR",
    "korea": "KR",
    "north korea": "KP",
    "vietnam": "VN",
    "iran": "IR",
    "syria": "SY",
    "laos": "LA",
    "venezuela": "VE",
    "bolivia": "BO",
    "tanzania": "TZ",
    "moldova": "MD",
    "czech republic": "CZ",
    "czechia": "CZ",
    "holland": "NL",
    "the netherlands": "NL",
    "turkey": "TR",
    "ivory coast": "CI",
}


@functools.lru_cache(maxsize=1)
def _exact_lookup() -> dict[str, str]:
    """Build {lowercased name/code -> alpha_2} from pycountry, once, cached.

    Cached because it's built from a static dataset and reused across thousands
    of candidates (scale: no repeated O(countries) rebuilds).
    """

    table: dict[str, str] = {}
    for country in pycountry.countries:
        a2 = country.alpha_2
        keys = [country.alpha_2, country.alpha_3, country.name]
        for attr in ("official_name", "common_name"):
            value = getattr(country, attr, None)
            if value:
                keys.append(value)
        for key in keys:
            table[key.lower()] = a2
    # Curated aliases layered on top (won't be overwritten by the loop above).
    table.update(_ALIASES)
    return table


def _candidate_keys(text: str) -> list[str]:
    """Lookup candidates for a raw string: as-is and punctuation-stripped."""

    lowered = text.lower()
    # Strip anything that isn't a letter, digit, or space ("u.s.a." -> "usa").
    stripped = "".join(ch for ch in lowered if ch.isalnum() or ch.isspace())
    stripped = " ".join(stripped.split())  # collapse whitespace
    # Order matters only for determinism; both map to the same table.
    candidates = [lowered, stripped]
    # De-dup while preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def normalize_country(raw: str | None) -> str | None:
    """Return the ISO-3166-1 alpha-2 code for ``raw``, or ``None``.

    Handles codes ("US", "USA"), names ("United States", "United Kingdom"),
    punctuated forms ("U.S.A."), and curated aliases ("UK", "England").  As a
    convenience for location strings like ``"SF, CA, USA"``, if the whole string
    doesn't resolve and it contains commas, the last comma-separated chunk is
    retried (that's where a country usually sits).
    """

    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None

    table = _exact_lookup()

    for key in _candidate_keys(text):
        hit = table.get(key)
        if hit:
            return hit

    # Convenience fallback: "City, Region, Country" -> try the trailing chunk.
    if "," in text:
        last = text.rsplit(",", 1)[-1].strip()
        if last and last != text:
            for key in _candidate_keys(last):
                hit = table.get(key)
                if hit:
                    return hit

    return None
