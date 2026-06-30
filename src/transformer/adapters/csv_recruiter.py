"""CSV recruiter export adapter (STRUCTURED).

A recruiter CSV is one candidate per row, with columns roughly like
``name, email, phone, current_company, title`` — but header spelling/casing
varies between exports, so we map headers through a small alias table rather
than hard-coding exact names.

Each row becomes its own ``record_key`` (the candidate_id column if present,
else the email, else a synthetic row id), so a multi-thousand-row CSV is handled
one candidate at a time and merge can link rows to the matching résumé/notes.
"""

from __future__ import annotations

import csv
import io
from typing import ClassVar

from transformer.adapters.base import FieldFragment, RawSource, clean_email
from transformer.models import Method, SourceType
from transformer.normalize.phones import normalize_phone

# Header (lowercased/trimmed) -> canonical column role. Add aliases freely; the
# adapter only emits a role when a matching header is present.
_HEADER_ALIASES: dict[str, str] = {
    "candidate_id": "candidate_id",
    "candidateid": "candidate_id",
    "candidate id": "candidate_id",
    "id": "candidate_id",
    "name": "name",
    "full_name": "name",
    "full name": "name",
    "fullname": "name",
    "candidate": "name",
    "candidate name": "name",
    "email": "email",
    "e-mail": "email",
    "email address": "email",
    "phone": "phone",
    "phone number": "phone",
    "phonenumber": "phone",
    "mobile": "phone",
    "cell": "phone",
    "telephone": "phone",
    "current_company": "company",
    "company": "company",
    "current company": "company",
    "employer": "company",
    "title": "title",
    "job title": "title",
    "current title": "title",
    "role": "title",
    "position": "title",
}


class CsvRecruiterAdapter:
    """Adapter for recruiter CSV exports."""

    source_type: ClassVar[SourceType] = SourceType.CSV_RECRUITER

    def detect(self, raw: RawSource) -> bool:
        if raw.path.suffix.lower() == ".csv":
            return True
        # Content sniff for extension-less inputs: looks tabular, not JSON.
        text = (raw.text or "").lstrip()
        if not text or text[0] in "{[":
            return False
        first_line = text.splitlines()[0] if text.splitlines() else ""
        return "," in first_line

    def extract(self, raw: RawSource) -> list[FieldFragment]:
        text = raw.text
        if not text:
            return []

        # csv handles quoting/embedded commas correctly. Strip a UTF-8 BOM that
        # some exporters prepend to the first header cell.
        reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
        if not reader.fieldnames:
            return []

        # Map this file's headers to canonical roles, once.
        role_of: dict[str, str] = {}
        for header in reader.fieldnames:
            if header is None:
                continue
            role = _HEADER_ALIASES.get(header.strip().lower())
            if role:
                role_of[header] = role

        fragments: list[FieldFragment] = []
        for index, row in enumerate(reader):
            values = {role_of[h]: (row.get(h) or "").strip() for h in role_of if row.get(h)}

            # Record key: prefer an explicit id, then email, then a synthetic id.
            record_key = (
                values.get("candidate_id")
                or (clean_email(values.get("email")) or "")
                or f"{raw.path.stem}#row{index}"
            )
            self._emit_row(fragments, values, record_key)

        return fragments

    def _emit_row(
        self, out: list[FieldFragment], values: dict[str, str], record_key: str
    ) -> None:
        src = self.source_type.value

        def add(field_path: str, value: object, conf: float, normalize: str | None = None) -> None:
            out.append(
                FieldFragment(
                    field_path=field_path,
                    value=value,
                    source=src,
                    method=Method.CSV_COLUMN,
                    raw_confidence=conf,
                    record_key=record_key,
                    normalize_method=normalize,
                )
            )

        if values.get("candidate_id"):
            add("candidate_id", values["candidate_id"], 1.0)
        if values.get("name"):
            add("full_name", values["name"], 0.95)
        email = clean_email(values.get("email"))
        if email:
            add("emails", email, 0.95)
        phone = normalize_phone(values.get("phone"))
        if phone:
            add("phones", phone, 0.9, normalize=Method.PHONE_NORMALIZE)

        # current_company + title -> one experience entry (the current role).
        company = values.get("company") or None
        title = values.get("title") or None
        if company or title:
            add(
                "experience",
                {"company": company, "title": title, "start": None, "end": None, "summary": None},
                0.9,
            )
