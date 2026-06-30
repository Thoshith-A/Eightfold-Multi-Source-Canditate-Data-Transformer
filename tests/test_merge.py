"""Tests for the merge engine: linking, conflict resolution, confidence, provenance."""

from __future__ import annotations

from pathlib import Path

import pytest

from transformer.adapters import detect_adapter
from transformer.adapters.base import FieldFragment, RawSource
from transformer.merge import (
    _Claim,
    _field_confidence,
    _resolve,
    merge,
    normalize_company,
    normalize_name,
)

SAMPLES = Path(__file__).resolve().parent.parent / "samples" / "sources"


def frag(field_path, value, source, method="m", rc=0.9, record_key="r", nm=None) -> FieldFragment:
    return FieldFragment(
        field_path=field_path, value=value, source=source, method=method,
        raw_confidence=rc, record_key=record_key, normalize_method=nm,
    )


def _provset(profile) -> set[tuple[str, str, str]]:
    return {(p.field, p.source, p.method) for p in profile.provenance}


# --------------------------------------------------------------------------- #
# Normalizers used for matching
# --------------------------------------------------------------------------- #
def test_normalize_name_drops_middle_initial() -> None:
    assert normalize_name("John A. Smith") == "john smith"
    assert normalize_name("John Smith") == "john smith"


def test_normalize_company_strips_suffix() -> None:
    assert normalize_company("Acme Corp") == "acme"
    assert normalize_company("Acme") == "acme"
    assert normalize_company("Globex Inc.") == "globex"


# --------------------------------------------------------------------------- #
# Scalar conflict resolution
# --------------------------------------------------------------------------- #
def test_resolve_highest_trust_wins() -> None:
    res = _resolve([
        _Claim("Senior Engineer", "csv_recruiter", 0.9, "csv_column"),
        _Claim("Staff Engineer", "ats_json", 0.92, "ats_field_map"),
    ])
    assert res.value == "Staff Engineer"  # ATS (100) beats CSV (90)
    assert res.conflict is True
    assert res.winner_source == "ats_json"


def test_resolve_tie_breaks_alphabetically() -> None:
    # Two unknown sources -> equal trust (0); alphabetical source wins.
    res = _resolve([
        _Claim("X", "zzz", 0.9, "m"),
        _Claim("Y", "aaa", 0.9, "m"),
    ])
    assert res.value == "Y"
    assert res.winner_source == "aaa"


def test_agreement_boosts_confidence() -> None:
    one = _field_confidence([_Claim("v", "ats_json", 0.9, "m")], conflict=False)
    three = _field_confidence([
        _Claim("v", "ats_json", 0.9, "m"),
        _Claim("v", "github", 0.9, "m"),
        _Claim("v", "resume", 0.9, "m"),
    ], conflict=False)
    assert three > one


def test_conflict_lowers_confidence() -> None:
    supporters = [_Claim("v", "ats_json", 0.9, "m")]
    assert _field_confidence(supporters, conflict=True) < _field_confidence(supporters, conflict=False)


# --------------------------------------------------------------------------- #
# Title conflict (the brief's headline test)
# --------------------------------------------------------------------------- #
def test_title_conflict_resolution() -> None:
    fragments = [
        frag("candidate_id", "c1", "csv_recruiter", "csv_column", 1.0),
        frag("candidate_id", "c1", "ats_json", "ats_field_map", 1.0),
        frag("experience", {"company": "Acme Corp", "title": "Senior Software Engineer",
                            "start": None, "end": None, "summary": None},
             "csv_recruiter", "csv_column", 0.9),
        frag("experience", {"company": "Acme Corp", "title": "Staff Software Engineer",
                            "start": None, "end": None, "summary": None},
             "ats_json", "ats_field_map", 0.92),
    ]
    [profile] = merge(fragments)
    assert len(profile.experience) == 1
    # Highest-trust source (ATS) wins the contested title.
    assert profile.experience[0].title == "Staff Software Engineer"
    # The conflict is recorded in provenance as a merge_winner from the winner.
    assert ("experience.title", "ats_json", "merge_winner") in _provset(profile)


def test_full_name_conflict_records_merge_winner() -> None:
    fragments = [
        frag("full_name", "John A. Smith", "csv_recruiter", "csv_column", 0.95),
        frag("full_name", "John Smith", "ats_json", "ats_field_map", 0.95),
    ]
    [profile] = merge(fragments)
    assert profile.full_name == "John Smith"
    assert ("full_name", "ats_json", "merge_winner") in _provset(profile)


# --------------------------------------------------------------------------- #
# Record linking
# --------------------------------------------------------------------------- #
def test_same_person_linked_via_shared_email() -> None:
    fragments = [
        frag("full_name", "Jane Doe", "csv_recruiter", "csv_column", 0.95, record_key="row0"),
        frag("emails", "jane@x.com", "csv_recruiter", "csv_column", 0.95, record_key="row0"),
        frag("emails", "jane@x.com", "resume", "regex_extraction", 0.8, record_key="resume"),
        frag("skills", "Python", "resume", "skill_canonicalize", 0.7, record_key="resume"),
    ]
    profiles = merge(fragments)
    assert len(profiles) == 1
    assert profiles[0].full_name == "Jane Doe"
    assert profiles[0].skills[0].name == "Python"


def test_over_merge_on_shared_email_is_warned(caplog) -> None:
    # Two DIFFERENT candidate_ids force-joined by a shared (mistyped) email is the
    # worst-case ATS error. We don't silently split, but we MUST warn loudly.
    import logging

    fragments = [
        frag("candidate_id", "c1", "ats_json", "ats_field_map", 1.0, record_key="c1"),
        frag("emails", "shared@typo.com", "ats_json", "ats_field_map", 0.95, record_key="c1"),
        frag("candidate_id", "c2", "ats_json", "ats_field_map", 1.0, record_key="c2"),
        frag("emails", "shared@typo.com", "ats_json", "ats_field_map", 0.95, record_key="c2"),
    ]
    with caplog.at_level(logging.WARNING, logger="transformer.merge"):
        profiles = merge(fragments)
    # Fused into one cluster (shared email) — and flagged.
    assert len(profiles) == 1
    assert any("over-merge" in r.message for r in caplog.records)


def test_conflicting_candidate_ids_not_merged_by_name() -> None:
    # Two different people, same name, distinct candidate_ids -> stay separate.
    fragments = [
        frag("candidate_id", "c1", "ats_json", "ats_field_map", 1.0, record_key="c1"),
        frag("full_name", "John Smith", "ats_json", "ats_field_map", 0.95, record_key="c1"),
        frag("candidate_id", "c2", "ats_json", "ats_field_map", 1.0, record_key="c2"),
        frag("full_name", "John Smith", "ats_json", "ats_field_map", 0.95, record_key="c2"),
    ]
    profiles = merge(fragments)
    assert {p.candidate_id for p in profiles} == {"c1", "c2"}


def test_name_only_source_attaches_to_unique_candidate() -> None:
    # A bare name-only record (no ids) attaches to the single id-bearing cluster.
    fragments = [
        frag("candidate_id", "c1", "ats_json", "ats_field_map", 1.0, record_key="c1"),
        frag("full_name", "John Smith", "ats_json", "ats_field_map", 0.95, record_key="c1"),
        frag("full_name", "John Smith", "github", "github_api", 0.8, record_key="gh"),
        frag("links.github", "https://github.com/js", "github", "github_api", 0.95, record_key="gh"),
    ]
    profiles = merge(fragments)
    assert len(profiles) == 1
    assert profiles[0].links.github == "https://github.com/js"


# --------------------------------------------------------------------------- #
# Robustness + determinism
# --------------------------------------------------------------------------- #
def test_merge_empty() -> None:
    assert merge([]) == []


def test_determinism_under_fragment_reordering() -> None:
    fragments = [
        frag("candidate_id", "c1", "ats_json", "ats_field_map", 1.0),
        frag("full_name", "John Smith", "ats_json", "ats_field_map", 0.95),
        frag("emails", "a@x.com", "csv_recruiter", "csv_column", 0.95),
        frag("skills", "Python", "github", "skill_canonicalize", 0.75),
        frag("skills", "Go", "resume", "skill_canonicalize", 0.7),
    ]
    assert merge(fragments) == merge(list(reversed(fragments)))


# --------------------------------------------------------------------------- #
# Full integration over the real sample fixtures
# --------------------------------------------------------------------------- #
def _all_sample_fragments() -> list[FieldFragment]:
    out: list[FieldFragment] = []
    for path in sorted(SAMPLES.iterdir()):
        raw = RawSource.load(path)
        adapter = detect_adapter(raw)
        if adapter is None:
            continue
        out.extend(adapter.extract(raw))
    return out


@pytest.fixture(scope="module")
def merged_profile():
    profiles = merge(_all_sample_fragments())
    assert len(profiles) == 1  # all five real sources are one person
    return profiles[0]


def test_integration_identity(merged_profile) -> None:
    p = merged_profile
    assert p.candidate_id == "cand-001"
    assert p.full_name == "John Smith"  # ATS (100) over CSV's "John A. Smith"
    assert p.emails == ["j.smith@workmail.com", "john.smith@example.com"]
    assert p.phones == ["+14155550132", "+14155550144", "+14155550177"]


def test_integration_location_conflict(merged_profile) -> None:
    loc = merged_profile.location
    assert (loc.city, loc.region, loc.country) == ("San Francisco", "California", "US")


def test_integration_experience(merged_profile) -> None:
    exp = merged_profile.experience
    assert [e.company for e in exp] == ["Acme Corp", "Globex Inc"]  # recent first
    acme = exp[0]
    assert acme.title == "Staff Software Engineer"  # ATS wins the title conflict
    assert (acme.start, acme.end) == ("2021-01", None)
    globex = exp[1]
    assert (globex.start, globex.end) == ("2019-01", "2021-01")
    assert ("experience.title", "ats_json", "merge_winner") in _provset(merged_profile)


def test_integration_education(merged_profile) -> None:
    edu = merged_profile.education[0]
    assert edu.institution == "Massachusetts Institute of Technology"
    assert edu.degree == "B.S."
    assert edu.field == "Computer Science"
    assert edu.end_year == 2018


def test_integration_skills_confidence_reflects_agreement(merged_profile) -> None:
    by_name = {s.name: s for s in merged_profile.skills}
    # Python is corroborated by ATS + GitHub + résumé -> high confidence, 3 sources.
    assert by_name["Python"].sources == ["ats_json", "github", "resume"]
    assert by_name["Python"].confidence >= 0.9
    # React appears only in the résumé -> single source, lower confidence.
    assert by_name["React"].sources == ["resume"]
    assert by_name["React"].confidence < by_name["Python"].confidence
    # Soft skill from the notes only.
    assert "Mentoring" in by_name


def test_integration_years_and_links(merged_profile) -> None:
    p = merged_profile
    assert p.years_experience == 8.0
    assert p.links.linkedin == "https://www.linkedin.com/in/johnasmith"
    assert p.links.github == "https://github.com/johnasmith"
    assert p.links.portfolio == "https://johnsmith.dev"


def test_integration_headline_is_null_deterministically(merged_profile) -> None:
    # No deterministic source for a prose headline -> null (enrichment may fill).
    assert merged_profile.headline is None


def test_integration_overall_confidence_in_range(merged_profile) -> None:
    assert 0.0 < merged_profile.overall_confidence <= 1.0


def test_integration_determinism() -> None:
    frags = _all_sample_fragments()
    assert merge(frags) == merge(list(reversed(frags)))
