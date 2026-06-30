"""Résumé adapter (UNSTRUCTURED prose: PDF or DOCX).

Reads text from a PDF (``pdfplumber``) or DOCX (``python-docx``) and pulls out
the structured-ish bits with regex/heuristics: emails, phone numbers, a SKILLS
section, dated EXPERIENCE lines, and EDUCATION lines.  Prose résumés are noisy,
so this adapter's fragments carry lower ``raw_confidence`` than the structured
sources, and anything that doesn't match a pattern is simply left out (never
guessed).

Everything is wrapped so a corrupt/unreadable file yields ``[]`` instead of
raising — a broken résumé must not sink the run.
"""

from __future__ import annotations

import re
from typing import ClassVar

from transformer.adapters.base import EMAIL_RE, FieldFragment, RawSource, clean_email
from transformer.models import Method, SourceType
from transformer.normalize.dates import parse_date_range
from transformer.normalize.phones import extract_phones
from transformer.normalize.skills import canonicalize_skill

# "Senior Software Engineer, Acme Corp (Jan 2021 – Present)"
_EXPERIENCE_RE = re.compile(r"^(?P<title>[^,]+),\s*(?P<company>.+?)\s*\((?P<dates>[^)]+)\)\s*$")

# "B.S. in Computer Science, Massachusetts Institute of Technology, 2018"
_EDUCATION_RE = re.compile(
    r"^(?P<degree>(?:B\.?S\.?|M\.?S\.?|B\.?A\.?|M\.?A\.?|Ph\.?D\.?|B\.?Eng\.?|"
    r"Bachelor|Master|Associate|Diploma)[^,]*?)(?:\s+in\s+(?P<field>[^,]+))?,\s*"
    r"(?P<institution>[^,]+),\s*(?P<year>\d{4})\s*$",
    re.IGNORECASE,
)

# Section headings we recognize (matched case-insensitively, alone on a line).
_SKILLS_HEADINGS = {"skills", "technical skills", "core skills"}
_SECTION_SPLIT = re.compile(r"[,;•|/•]+")


class ResumeAdapter:
    """Adapter for PDF/DOCX résumés."""

    source_type: ClassVar[SourceType] = SourceType.RESUME

    def detect(self, raw: RawSource) -> bool:
        return raw.path.suffix.lower() in {".pdf", ".docx", ".doc"}

    def extract(self, raw: RawSource) -> list[FieldFragment]:
        text = self._read_text(raw)
        if not text:
            return []

        lines = [ln.strip() for ln in text.splitlines()]
        fragments: list[FieldFragment] = []
        # One résumé == one candidate; stable per-file record key.
        record_key = raw.path.stem

        def add(field_path: str, value: object, conf: float, normalize: str | None = None,
                method: str = Method.REGEX) -> None:
            fragments.append(
                FieldFragment(
                    field_path=field_path,
                    value=value,
                    source=self.source_type.value,
                    method=method,
                    raw_confidence=conf,
                    record_key=record_key,
                    normalize_method=normalize,
                )
            )

        # Emails (deduped, order-stable).
        seen_emails: set[str] = set()
        for match in EMAIL_RE.finditer(text):
            email = clean_email(match.group(0))
            if email and email not in seen_emails:
                seen_emails.add(email)
                add("emails", email, 0.8)

        # Phones (already validated + E.164 by the normalizer).
        for phone in extract_phones(text):
            add("phones", phone, 0.8, normalize=Method.PHONE_NORMALIZE)

        # Experience: dated lines.
        for line in lines:
            m = _EXPERIENCE_RE.match(line)
            if not m:
                continue
            start, end = parse_date_range(m.group("dates"))
            add(
                "experience",
                {
                    "company": m.group("company").strip(),
                    "title": m.group("title").strip(),
                    "start": start,
                    "end": end,
                    "summary": None,
                },
                0.7,
                normalize=Method.DATE_PARSE,
            )

        # Education.
        for line in lines:
            m = _EDUCATION_RE.match(line)
            if not m:
                continue
            field = m.group("field")
            add(
                "education",
                {
                    "institution": m.group("institution").strip(),
                    "degree": m.group("degree").strip(),
                    "field": field.strip() if field else None,
                    "end_year": int(m.group("year")),
                },
                0.7,
            )

        # Skills section.
        for raw_skill in self._skills_section_items(lines):
            canon = canonicalize_skill(raw_skill)
            if canon.name:
                add(
                    "skills",
                    canon.name,
                    0.7 if canon.canonical else 0.5,
                    normalize=Method.SKILL_CANONICALIZE,
                )

        return fragments

    @staticmethod
    def _skills_section_items(lines: list[str]) -> list[str]:
        """Collect raw skill tokens under a SKILLS heading until the next section."""

        items: list[str] = []
        collecting = False
        for line in lines:
            stripped = line.strip()
            low = stripped.lower().rstrip(":")
            if low in _SKILLS_HEADINGS:
                collecting = True
                continue
            if collecting:
                # Stop at a blank line or the next ALL-CAPS section heading.
                if not stripped:
                    break
                if stripped.isupper() and len(stripped) <= 40:
                    break
                items.extend(tok.strip() for tok in _SECTION_SPLIT.split(stripped) if tok.strip())
        return items

    @staticmethod
    def _read_text(raw: RawSource) -> str:
        return read_text(raw)


def read_text(raw: RawSource) -> str:
    """Extract plain text from a PDF or DOCX; '' on any read failure.

    Public so the optional enrichment lane can recover résumé prose (a DOCX/PDF's
    text is never in ``raw.text``, which is the best-effort UTF-8 decode).
    """

    suffix = raw.path.suffix.lower()
    try:
        if suffix == ".pdf":
            import pdfplumber

            with pdfplumber.open(str(raw.path)) as pdf:
                return "\n".join((page.extract_text() or "") for page in pdf.pages)
        if suffix in {".docx", ".doc"}:
            import docx

            document = docx.Document(str(raw.path))
            return "\n".join(p.text for p in document.paragraphs)
    except Exception:
        # Corrupt/unreadable résumé -> graceful empty.
        return ""
    return ""
