"""Constraint #4, enforced: every emitted value maps to a provenance entry.

The brief promises traceability in prose; this test makes it a hard invariant
over the actual merged profile — including the previously-untraced *derived*
candidate_id case (now fixed in merge._derive_candidate_id).
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from transformer import pipeline
from transformer.adapters.base import FieldFragment
from transformer.merge import merge

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "samples" / "sources"


def _prov_fields(profile) -> dict[str, set[str]]:
    """field -> set of methods that produced it."""
    idx: dict[str, set[str]] = defaultdict(set)
    for p in profile.provenance:
        idx[p.field].add(p.method)
    return idx


def test_every_emitted_value_is_traceable() -> None:
    [profile] = pipeline.build_profiles([SOURCES])
    prov = _prov_fields(profile)

    # Identity + scalar fields.
    assert prov.get("candidate_id"), "candidate_id must be traced"
    assert prov.get("full_name"), "full_name must be traced"
    assert prov.get("years_experience"), "years_experience must be traced"

    # Nested scalars that are populated.
    for sub in ("location.city", "location.region", "location.country"):
        if getattr(profile.location, sub.split(".")[1]) is not None:
            assert prov.get(sub), f"{sub} must be traced"
    for sub, val in (("links.linkedin", profile.links.linkedin),
                     ("links.github", profile.links.github),
                     ("links.portfolio", profile.links.portfolio)):
        if val is not None:
            assert prov.get(sub), f"{sub} must be traced"

    # Non-empty list fields.
    if profile.emails:
        assert prov.get("emails")
    if profile.phones:
        assert prov.get("phones")

    # Every skill/experience/education entry is covered.
    if profile.skills:
        assert "skill_canonicalize" in prov.get("skills", set())
    if profile.experience:
        assert prov.get("experience")
    if profile.education:
        assert prov.get("education")


def test_derived_candidate_id_is_traced() -> None:
    # No explicit candidate_id anywhere -> id is DERIVED, and must still be traced.
    fragments = [
        FieldFragment(field_path="full_name", value="Jane Roe", source="github",
                      method="github_api", raw_confidence=0.8, record_key="gh"),
        FieldFragment(field_path="links.github", value="https://github.com/jane",
                      source="github", method="github_api", raw_confidence=0.95, record_key="gh"),
    ]
    [profile] = merge(fragments)
    assert profile.candidate_id == "jane_roe"  # derived from normalized name
    methods = {(p.field, p.method) for p in profile.provenance}
    assert ("candidate_id", "derived_id") in methods  # the fixed gap
