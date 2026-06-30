"""Location-string parsing -> (city, region, country-alpha-2).

A small, deterministic helper for the unstructured sources whose location is a
single messy string ("SF, CA, USA", "London, UK", "Bengaluru, India").  It is a
normalizer (pure, offline, no invention) and lives alongside the others.

The one genuinely tricky case it handles: ``"CA"`` is *both* a US state
abbreviation (California) and an ISO country code (Canada).  In a comma list the
country sits at the end, but a trailing ``"CA"`` almost always means California,
not Canada.  So we refuse to read a trailing 2-letter token as a country when it
is a known US state abbreviation — preventing a "San Francisco, CA" from being
mislabeled as Canada.
"""

from __future__ import annotations

from dataclasses import dataclass

from transformer.normalize.country import normalize_country

# US state abbreviations — used only to veto the "trailing CA == Canada" misread.
_US_STATE_ABBR = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL",
    "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT",
    "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI",
    "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
}


@dataclass(frozen=True)
class ParsedLocation:
    city: str | None
    region: str | None
    country: str | None  # ISO-3166-1 alpha-2


def parse_location_string(raw: str | None) -> ParsedLocation:
    """Split a free-form location into ``(city, region, country)``.

    Examples::

        "SF, CA, USA"          -> ("SF", "CA", "US")
        "San Francisco, CA"    -> ("San Francisco", "CA", None)
        "London, UK"           -> ("London", None, "GB")
        "Bengaluru, India"     -> ("Bengaluru", None, "IN")
        "USA"                  -> (None, None, "US")
        "Remote"               -> ("Remote", None, None)
    """

    if not raw or not raw.strip():
        return ParsedLocation(None, None, None)

    # Split on commas and strip surrounding whitespace AND trailing sentence
    # punctuation. Without this, "based in San Francisco, CA." yields a "CA."
    # token that (being length 3) would dodge the state-abbreviation veto below
    # and get mis-resolved to Canada. Strip it back to a clean "CA".
    parts = [seg.strip(" \t.,;:") for seg in raw.split(",")]
    parts = [p for p in parts if p]
    if not parts:
        return ParsedLocation(None, None, None)

    country: str | None = None
    # Consider the trailing token as a country candidate, but NOT if it's a
    # US state abbreviation ("...,CA" -> California, not Canada).
    last = parts[-1]
    if not (len(last) == 2 and last.upper() in _US_STATE_ABBR):
        maybe_country = normalize_country(last)
        if maybe_country is not None:
            country = maybe_country
            parts = parts[:-1]  # consume the country token

    # If a single token was itself the country, there's no city/region left.
    if not parts:
        return ParsedLocation(None, None, country)

    # Remaining tokens: [city] or [city, region].
    city = parts[0]
    region = parts[1] if len(parts) >= 2 else None
    return ParsedLocation(city=city or None, region=region, country=country)
