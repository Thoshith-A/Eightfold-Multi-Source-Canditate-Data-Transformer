"""ATS JSON adapter (STRUCTURED, but with foreign field names).

This is the "semi-structured" source: it's clean JSON, but the field names are
the ATS vendor's, not ours (``givenName``/``surname``/``phoneNumber``/
``skillTags``/``currentTitle`` ...).  The whole job of this adapter is the
**explicit mapping** from their schema to our canonical field paths — no guessing.

Accepts a single candidate object, a top-level list of them, or a
``{"candidates": [...]}`` envelope.  Malformed JSON is caught and yields nothing
(the pipeline also isolates adapters), so a corrupt ATS export never crashes a run.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from transformer.adapters.base import FieldFragment, RawSource, clean_email
from transformer.models import Method, SourceType
from transformer.normalize.country import normalize_country
from transformer.normalize.phones import normalize_phone
from transformer.normalize.skills import canonicalize_skill

# Content markers used for cheap, parse-free detection (so detect() never throws).
_ATS_MARKERS = (
    '"givenName"',
    '"surname"',
    '"skillTags"',
    '"currentTitle"',
    '"phoneNumber"',
    '"candidates"',
)


class AtsJsonAdapter:
    """Adapter for ATS vendor JSON exports."""

    source_type: ClassVar[SourceType] = SourceType.ATS_JSON

    def detect(self, raw: RawSource) -> bool:
        if raw.path.suffix.lower() != ".json":
            return False
        text = raw.text or ""
        if not text.strip():
            return False
        # Cheap substring check — do NOT json.loads here (detect must be safe even
        # on corrupt input; parsing is the extract step's job, wrapped in try).
        return any(marker in text for marker in _ATS_MARKERS)

    def extract(self, raw: RawSource) -> list[FieldFragment]:
        if not raw.text:
            return []
        try:
            doc = json.loads(raw.text)
        except (json.JSONDecodeError, ValueError):
            # Corrupt/garbage ATS file -> degrade gracefully, no fragments.
            return []

        records = self._as_records(doc)
        fragments: list[FieldFragment] = []
        for index, record in enumerate(records):
            if isinstance(record, dict):
                self._emit_record(fragments, record, index, raw.path.stem)
        return fragments

    @staticmethod
    def _as_records(doc: Any) -> list[Any]:
        """Normalize the three accepted envelopes into a list of candidate dicts."""

        if isinstance(doc, list):
            return doc
        if isinstance(doc, dict):
            if isinstance(doc.get("candidates"), list):
                return doc["candidates"]
            return [doc]
        return []

    def _emit_record(
        self, out: list[FieldFragment], rec: dict[str, Any], index: int, stem: str
    ) -> None:
        src = self.source_type.value

        # Resolve the record key first (id -> email -> synthetic).
        candidate_id = _first_str(rec, "candidate_id", "candidateId", "id")
        emails = _collect_emails(rec)
        record_key = candidate_id or (emails[0] if emails else f"{stem}#{index}")

        def add(field_path: str, value: object, conf: float, normalize: str | None = None) -> None:
            out.append(
                FieldFragment(
                    field_path=field_path,
                    value=value,
                    source=src,
                    method=Method.ATS_FIELD_MAP,
                    raw_confidence=conf,
                    record_key=record_key,
                    normalize_method=normalize,
                )
            )

        if candidate_id:
            add("candidate_id", candidate_id, 1.0)

        # Name: prefer an explicit full name, else join given + surname.
        full_name = _first_str(rec, "fullName", "name")
        if not full_name:
            given = _first_str(rec, "givenName", "firstName")
            surname = _first_str(rec, "surname", "lastName", "familyName")
            joined = " ".join(p for p in (given, surname) if p)
            full_name = joined or None
        if full_name:
            add("full_name", full_name, 0.95)

        for email in emails:
            add("emails", email, 0.95)

        phone_raw = _first_str(rec, "phoneNumber", "phone", "mobile")
        if phone_raw:
            phone = normalize_phone(phone_raw)
            if phone:
                add("phones", phone, 0.9, normalize=Method.PHONE_NORMALIZE)

        # Current role -> experience entry (its title is the one that conflicts
        # with the CSV's title for the same company; merge resolves by trust).
        title = _first_str(rec, "currentTitle", "title", "jobTitle")
        company = _first_str(rec, "currentEmployer", "currentCompany", "company", "employer")
        if title or company:
            add(
                "experience",
                {"company": company, "title": title, "start": None, "end": None, "summary": None},
                0.92,
            )

        # Location: city / state(region) / country.
        city = _first_str(rec, "city", "locationCity")
        if city:
            add("location.city", city, 0.9)
        region = _first_str(rec, "state", "region", "province")
        if region:
            add("location.region", region, 0.9)
        country_raw = _first_str(rec, "country", "countryCode")
        if country_raw:
            country = normalize_country(country_raw)
            if country:
                add("location.country", country, 0.9, normalize=Method.COUNTRY_NORMALIZE)

        # LinkedIn link.
        linkedin = _first_str(rec, "linkedin", "linkedInUrl", "linkedIn")
        if linkedin:
            add("links.linkedin", linkedin, 0.9)

        # Years of experience (numeric).
        years = rec.get("yearsExperience", rec.get("years_experience"))
        if isinstance(years, (int, float)) and not isinstance(years, bool):
            add("years_experience", float(years), 0.9)

        # Skill tags -> canonicalized skills.
        tags = rec.get("skillTags") or rec.get("skills") or []
        if isinstance(tags, list):
            for tag in tags:
                if not isinstance(tag, str):
                    continue
                canon = canonicalize_skill(tag)
                if not canon.name:
                    continue
                add(
                    "skills",
                    canon.name,
                    0.9 if canon.canonical else 0.6,
                    normalize=Method.SKILL_CANONICALIZE,
                )


def _first_str(rec: dict[str, Any], *keys: str) -> str | None:
    """Return the first non-empty string value among ``keys`` (case as given)."""

    for key in keys:
        value = rec.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _collect_emails(rec: dict[str, Any]) -> list[str]:
    """Gather emails from either an ``emails`` list or a singular ``email`` field."""

    out: list[str] = []
    raw = rec.get("emails")
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                cleaned = clean_email(item)
                if cleaned and cleaned not in out:
                    out.append(cleaned)
    single = rec.get("email")
    if isinstance(single, str):
        cleaned = clean_email(single)
        if cleaned and cleaned not in out:
            out.append(cleaned)
    return out
