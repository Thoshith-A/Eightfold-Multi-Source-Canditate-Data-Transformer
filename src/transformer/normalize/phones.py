"""Phone normalization -> E.164.

Deterministic, offline (``phonenumbers`` ships its own metadata), and robust:
anything that isn't a parseable, *valid* phone number returns ``None`` rather
than raising or emitting garbage.  We gate on ``is_valid_number`` (not merely
``is_possible_number``) so we never write a malformed number into an ATS — a
wrong phone number is worse than a missing one.

Local-format numbers (no ``+`` country code) are inherently ambiguous about
region, so the caller supplies a ``default_region`` (ISO-3166 alpha-2).  We
default it to ``"US"`` because the demo dataset is US-based; it is an explicit,
documented parameter, never a hidden global.  Numbers that already carry a ``+``
country code are parsed region-independently.
"""

from __future__ import annotations

import phonenumbers
from phonenumbers import NumberParseException

DEFAULT_REGION = "US"


def normalize_phone(raw: str | None, default_region: str | None = DEFAULT_REGION) -> str | None:
    """Return ``raw`` as an E.164 string (e.g. ``"+14155550132"``) or ``None``.

    * ``None``/blank input            -> ``None``
    * unparseable / non-phone text    -> ``None`` (exception caught)
    * parseable but *invalid* number  -> ``None`` (we refuse to emit it)
    * numbers starting with ``+``     -> parsed as international (region ignored)
    * otherwise                       -> parsed using ``default_region``
    """

    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None

    # A leading "+" means the number is already international; passing a region
    # in that case is harmless but we make the intent explicit by using None.
    region = None if text.startswith("+") else default_region

    try:
        parsed = phonenumbers.parse(text, region)
    except NumberParseException:
        # Not a phone number at all ("N/A", "call me", free text). Unknown -> null.
        return None

    if not phonenumbers.is_valid_number(parsed):
        # Parseable shape but not a real, dialable number for its region.
        return None

    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def extract_phones(text: str | None, default_region: str | None = DEFAULT_REGION) -> list[str]:
    """Find every valid phone number embedded in free text, as E.164.

    Used by the unstructured adapters (résumé prose, recruiter notes) where a
    number is buried in a sentence.  Uses ``PhoneNumberMatcher`` so we only pick
    up things that actually parse as numbers.  Results are de-duplicated and
    returned sorted for determinism (the merge layer also sorts, but keeping the
    primitive deterministic makes it independently testable).
    """

    if not text:
        return []

    found: set[str] = set()
    region = default_region
    try:
        for match in phonenumbers.PhoneNumberMatcher(text, region):
            if phonenumbers.is_valid_number(match.number):
                found.add(
                    phonenumbers.format_number(match.number, phonenumbers.PhoneNumberFormat.E164)
                )
    except Exception:
        # Matcher should not raise on normal text, but never let it crash a run.
        return sorted(found)

    return sorted(found)
