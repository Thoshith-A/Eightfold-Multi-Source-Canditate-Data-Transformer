"""Locks the section-aware résumé parsing against a real-world layout.

Uses a synthetic candidate (not real PII) in the common format that the original
regex-only adapter could not handle: a "Name — Email — GitHub — LinkedIn" header,
"Title – Company   Mon YYYY – Present" experience, categorized "Category: a, b"
skills, and multi-line "Degree ... YYYY–YYYY / Institution" education.
"""

from __future__ import annotations

from collections import defaultdict

from transformer.adapters.resume import _fragments_from_text

_RESUME = """Jordan P. Rivera
Jordan P. Rivera — Email: jordan.rivera@example.com — Phone: +1-415-555-0165 — GitHub: github.com/jordan-rivera — LinkedIn: linkedin.com/in/jordan-rivera-01
Summary
Backend engineer proficient in Go, Python, and distributed systems.
Experience
Senior Backend Engineer – Globex Systems Feb 2022 – Present
- Led migration to a microservices architecture.
Software Engineer, Initech Jan 2019 – Jan 2022
- Built internal tooling.
Education
B.Tech in Information Technology 2015 – 2019
National Institute of Technology, Karnataka
GPA: 8.9/10.0
Skills
Programming Languages: Go, Python, JavaScript, SQL
Cloud & Infra: AWS, Kubernetes, Docker, Terraform
Certifications
- Some Cert"""


def _by(text: str) -> dict[str, list]:
    out = defaultdict(list)
    for f in _fragments_from_text(text, "rw"):
        out[f.field_path].append(f.value)
    return out


def test_realworld_header_name_and_links() -> None:
    by = _by(_RESUME)
    assert by["full_name"] == ["Jordan P. Rivera"]
    assert by["emails"] == ["jordan.rivera@example.com"]
    assert by["phones"] == ["+14155550165"]
    assert by["links.github"] == ["https://github.com/jordan-rivera"]
    assert by["links.linkedin"] == ["https://linkedin.com/in/jordan-rivera-01"]


def test_realworld_experience_dash_and_comma_formats() -> None:
    exp = {e["company"]: e for e in _by(_RESUME)["experience"]}
    assert exp["Globex Systems"]["title"] == "Senior Backend Engineer"      # "–" separator
    assert (exp["Globex Systems"]["start"], exp["Globex Systems"]["end"]) == ("2022-02", None)
    assert exp["Initech"]["title"] == "Software Engineer"                    # "," separator
    assert (exp["Initech"]["start"], exp["Initech"]["end"]) == ("2019-01", "2022-01")


def test_realworld_multiline_education() -> None:
    edu = _by(_RESUME)["education"][0]
    assert edu["degree"] == "B.Tech"
    assert edu["field"] == "Information Technology"
    assert edu["institution"] == "National Institute of Technology"
    assert edu["end_year"] == 2019


def test_realworld_categorized_skills() -> None:
    skills = set(_by(_RESUME)["skills"])
    # Category prefixes ("Programming Languages:", "Cloud & Infra:") are stripped.
    assert {"Go", "Python", "JavaScript", "SQL", "AWS", "Kubernetes", "Docker", "Terraform"} <= skills
    # No category label leaked in as a skill.
    assert not any("Programming Languages" in s or "Cloud" in s for s in skills)
