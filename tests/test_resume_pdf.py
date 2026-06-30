"""Cover the .pdf branch of the résumé adapter (pdfplumber) — a CORE dependency
that no other test exercises. A candidate who submits a PDF hits shipped code;
PDF text extraction differs from DOCX (whitespace/line-breaks), a real source of
silent parsing bugs. We assert on the EXTRACTED values (robust to whitespace),
not exact text, and add a corrupt-PDF graceful case.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import pytest

pytest.importorskip("fpdf")  # fpdf2 is a dev-only fixture generator

from fpdf import FPDF  # noqa: E402

from transformer.adapters.base import RawSource  # noqa: E402
from transformer.adapters.resume import ResumeAdapter  # noqa: E402

# ASCII-only (fpdf2 core fonts are latin-1); a spaced hyphen still parses as a range.
_LINES = [
    "John A. Smith",
    "Senior Software Engineer",
    "john.smith@example.com | (415) 555-0132 | San Francisco, CA",
    "",
    "EXPERIENCE",
    "Senior Software Engineer, Acme Corp (Jan 2021 - Present)",
    "Software Engineer, Globex Inc (2019-2021)",
    "",
    "EDUCATION",
    "B.S. in Computer Science, Massachusetts Institute of Technology, 2018",
    "",
    "SKILLS",
    "Python, ReactJS, Kubernetes, Go, PostgreSQL, REST APIs",
]


def _make_pdf(path: Path) -> None:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    for line in _LINES:
        pdf.cell(0, 8, line, new_x="LMARGIN", new_y="NEXT")
    pdf.output(str(path))


def _by_field(fragments):
    out = defaultdict(list)
    for fr in fragments:
        out[fr.field_path].append(fr.value)
    return out


def test_pdf_resume_extraction(tmp_path: Path) -> None:
    pdf_path = tmp_path / "resume.pdf"
    _make_pdf(pdf_path)

    raw = RawSource.load(pdf_path)
    adapter = ResumeAdapter()
    assert adapter.detect(raw)
    by = _by_field(adapter.extract(raw))

    # Contact details (robust regex over the whole text).
    assert "john.smith@example.com" in by["emails"]
    assert "+14155550132" in by["phones"]

    # Experience parsed, with the date range normalized.
    companies = {e["company"]: e for e in by["experience"]}
    assert "Acme Corp" in companies
    assert companies["Acme Corp"]["title"] == "Senior Software Engineer"
    assert companies["Acme Corp"]["start"] == "2021-01"
    assert ("2019-01", "2021-01") == (companies["Globex Inc"]["start"], companies["Globex Inc"]["end"])

    # Education + skills (ReactJS -> React canonicalization survives the PDF path).
    edu = by["education"][0]
    assert edu["institution"] == "Massachusetts Institute of Technology"
    assert edu["end_year"] == 2018
    assert "React" in by["skills"] and "Python" in by["skills"]


def test_corrupt_pdf_is_graceful(tmp_path: Path) -> None:
    bad = tmp_path / "broken.pdf"
    bad.write_bytes(b"%PDF-1.4 not really a pdf \x00\x01\x02")
    assert ResumeAdapter().extract(RawSource.load(bad)) == []
