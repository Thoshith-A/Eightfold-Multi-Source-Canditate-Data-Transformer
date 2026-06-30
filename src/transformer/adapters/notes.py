"""Recruiter notes adapter (UNSTRUCTURED free text).

The loosest source: a human's free-text notes.  We extract only what we can
spot with confidence — phone numbers, emails, an explicit "Candidate: <name>"
line, a "based in <place>" location, and any canonical skills *explicitly named*
in the prose.  Everything is low ``raw_confidence`` (this is the lowest-trust
source) and unmatched text is ignored rather than guessed at.
"""

from __future__ import annotations

import re
from typing import ClassVar

from transformer.adapters.base import EMAIL_RE, FieldFragment, RawSource, clean_email
from transformer.models import Method, SourceType
from transformer.normalize.location import parse_location_string
from transformer.normalize.phones import extract_phones
from transformer.normalize.skills import scan_skills_in_text

# "Candidate: John A. Smith" / "Name - John A. Smith"
_NAME_RE = re.compile(r"^\s*(?:candidate|name)\s*[:\-]\s*(?P<name>.+?)\s*$", re.IGNORECASE | re.MULTILINE)
# "based in San Francisco, CA" / "located in London, UK"
_LOCATION_RE = re.compile(r"\b(?:based in|located in|lives in)\s+(?P<loc>[A-Za-z .,'-]+)", re.IGNORECASE)


class NotesAdapter:
    """Adapter for plain-text recruiter notes."""

    source_type: ClassVar[SourceType] = SourceType.NOTES

    def detect(self, raw: RawSource) -> bool:
        return raw.path.suffix.lower() in {".txt", ".text", ".md"}

    def extract(self, raw: RawSource) -> list[FieldFragment]:
        text = raw.text
        if not text or not text.strip():
            return []

        fragments: list[FieldFragment] = []
        record_key = raw.path.stem

        def add(field_path: str, value: object, conf: float, normalize: str | None = None) -> None:
            fragments.append(
                FieldFragment(
                    field_path=field_path,
                    value=value,
                    source=self.source_type.value,
                    method=Method.HEURISTIC,
                    raw_confidence=conf,
                    record_key=record_key,
                    normalize_method=normalize,
                )
            )

        # Candidate name (helps merge link this note to the right person).
        name_match = _NAME_RE.search(text)
        if name_match:
            add("full_name", name_match.group("name").strip(), 0.5)

        # Emails.
        seen_emails: set[str] = set()
        for match in EMAIL_RE.finditer(text):
            email = clean_email(match.group(0))
            if email and email not in seen_emails:
                seen_emails.add(email)
                add("emails", email, 0.5)

        # Phones (the "third number" the notes contribute).
        for phone in extract_phones(text):
            add("phones", phone, 0.45, normalize=Method.PHONE_NORMALIZE)

        # Location, if stated.
        loc_match = _LOCATION_RE.search(text)
        if loc_match:
            loc = parse_location_string(loc_match.group("loc"))
            if loc.city:
                add("location.city", loc.city, 0.4)
            if loc.region:
                add("location.region", loc.region, 0.4)
            if loc.country:
                add("location.country", loc.country, 0.45, normalize=Method.COUNTRY_NORMALIZE)

        # Skills explicitly named in the prose (conservative scan).
        for canon in scan_skills_in_text(text):
            add("skills", canon.name, 0.45, normalize=Method.SKILL_CANONICALIZE)

        return fragments
