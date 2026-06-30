"""Unit tests for the source adapters: detection, extraction, graceful degradation.

Each adapter is exercised in isolation against the committed sample fixtures.
We assert on the *fragments* an adapter emits (canonical field_path -> values),
which is the contract the merge engine depends on.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import pytest

from transformer.adapters import detect_adapter
from transformer.adapters.base import FieldFragment, RawSource
from transformer.models import SourceType

SAMPLES = Path(__file__).resolve().parent.parent / "samples" / "sources"


def _load(name: str) -> RawSource:
    return RawSource.load(SAMPLES / name)


def _extract(name: str) -> list[FieldFragment]:
    raw = _load(name)
    adapter = detect_adapter(raw)
    assert adapter is not None, f"no adapter detected {name}"
    return adapter.extract(raw)


def _by_field(fragments: list[FieldFragment]) -> dict[str, list[Any]]:
    out: dict[str, list[Any]] = defaultdict(list)
    for fr in fragments:
        out[fr.field_path].append(fr.value)
    return out


# --------------------------------------------------------------------------- #
# Detection routing
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "name,expected",
    [
        ("john_smith_recruiter.csv", SourceType.CSV_RECRUITER),
        ("john_smith_ats.json", SourceType.ATS_JSON),
        ("john_smith_github.json", SourceType.GITHUB),
        ("john_smith_resume.docx", SourceType.RESUME),
        ("john_smith_notes.txt", SourceType.NOTES),
        ("empty_source.csv", SourceType.CSV_RECRUITER),  # detected by extension
        ("garbage_source.json", SourceType.ATS_JSON),  # routed by ATS marker
    ],
)
def test_detection_routing(name: str, expected: SourceType) -> None:
    adapter = detect_adapter(_load(name))
    assert adapter is not None
    assert adapter.source_type == expected


# --------------------------------------------------------------------------- #
# CSV
# --------------------------------------------------------------------------- #
def test_csv_extract() -> None:
    by = _by_field(_extract("john_smith_recruiter.csv"))
    assert by["candidate_id"] == ["cand-001"]
    assert by["full_name"] == ["John A. Smith"]
    assert by["emails"] == ["john.smith@example.com"]
    assert by["phones"] == ["+14155550132"]  # weird local format -> E.164
    assert by["experience"] == [
        {"company": "Acme Corp", "title": "Senior Software Engineer",
         "start": None, "end": None, "summary": None}
    ]


# --------------------------------------------------------------------------- #
# ATS JSON
# --------------------------------------------------------------------------- #
def test_ats_extract() -> None:
    by = _by_field(_extract("john_smith_ats.json"))
    assert by["candidate_id"] == ["cand-001"]
    assert by["full_name"] == ["John Smith"]  # givenName + surname
    assert sorted(by["emails"]) == ["j.smith@workmail.com", "john.smith@example.com"]
    assert by["phones"] == ["+14155550144"]
    assert by["experience"] == [
        {"company": "Acme Corp", "title": "Staff Software Engineer",
         "start": None, "end": None, "summary": None}
    ]
    assert by["location.city"] == ["San Francisco"]
    assert by["location.region"] == ["California"]
    assert by["location.country"] == ["US"]  # "United States" -> US
    assert by["years_experience"] == [8.0]
    assert sorted(by["skills"]) == ["Go", "Kubernetes", "Python"]
    assert by["links.linkedin"] == ["https://www.linkedin.com/in/johnasmith"]


# --------------------------------------------------------------------------- #
# GitHub
# --------------------------------------------------------------------------- #
def test_github_extract() -> None:
    by = _by_field(_extract("john_smith_github.json"))
    assert by["full_name"] == ["John Smith"]
    assert by["links.github"] == ["https://github.com/johnasmith"]
    assert by["links.portfolio"] == ["https://johnsmith.dev"]
    assert by["location.city"] == ["SF"]
    assert by["location.region"] == ["CA"]
    assert by["location.country"] == ["US"]
    # "@Acme Corp" -> company cleaned of the leading "@".
    assert by["experience"] == [
        {"company": "Acme Corp", "title": None, "start": None, "end": None, "summary": None}
    ]
    # Languages -> canonical skills (sorted, deduped).
    assert sorted(by["skills"]) == ["Go", "JavaScript", "Python", "Shell"]


# --------------------------------------------------------------------------- #
# Resume (DOCX)
# --------------------------------------------------------------------------- #
def test_resume_extract() -> None:
    by = _by_field(_extract("john_smith_resume.docx"))
    assert "john.smith@example.com" in by["emails"]
    assert "+14155550132" in by["phones"]

    experiences = by["experience"]
    acme = next(e for e in experiences if e["company"] == "Acme Corp")
    globex = next(e for e in experiences if e["company"] == "Globex Inc")
    assert acme["title"] == "Senior Software Engineer"
    assert (acme["start"], acme["end"]) == ("2021-01", None)  # "Jan 2021 - Present"
    assert (globex["start"], globex["end"]) == ("2019-01", "2021-01")  # "2019-2021"

    edu = by["education"][0]
    assert edu["institution"] == "Massachusetts Institute of Technology"
    assert edu["field"] == "Computer Science"
    assert edu["end_year"] == 2018

    # "ReactJS" canonicalizes to "React"; section parsed into canonical skills.
    assert "React" in by["skills"]
    for expected in ("Python", "Kubernetes", "Go", "PostgreSQL", "REST APIs"):
        assert expected in by["skills"], expected


# --------------------------------------------------------------------------- #
# Notes
# --------------------------------------------------------------------------- #
def test_notes_extract() -> None:
    by = _by_field(_extract("john_smith_notes.txt"))
    assert by["full_name"] == ["John A. Smith"]
    assert by["phones"] == ["+14155550177"]  # the third, distinct number
    assert by["location.city"] == ["San Francisco"]
    assert by["location.region"] == ["CA"]
    assert by["skills"] == ["Mentoring"]  # "mentorship" -> Mentoring


# --------------------------------------------------------------------------- #
# Graceful degradation
# --------------------------------------------------------------------------- #
def test_empty_source_yields_nothing() -> None:
    assert _extract("empty_source.csv") == []


def test_garbage_source_does_not_crash() -> None:
    # Routed to ATS by marker, fails JSON parse inside extract -> [] (no raise).
    assert _extract("garbage_source.json") == []


# --------------------------------------------------------------------------- #
# Determinism (each adapter is a pure function of its input)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "name",
    ["john_smith_recruiter.csv", "john_smith_ats.json", "john_smith_github.json",
     "john_smith_resume.docx", "john_smith_notes.txt"],
)
def test_extraction_is_deterministic(name: str) -> None:
    assert _extract(name) == _extract(name)
