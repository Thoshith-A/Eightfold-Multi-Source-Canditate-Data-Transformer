"""Tests for the projection engine: path mini-language, normalize, on_missing, validation."""

from __future__ import annotations

import pytest

from transformer.config import (
    FieldSpec,
    FieldType,
    Normalize,
    OnMissing,
    OutputConfig,
)
from transformer.models import (
    CanonicalProfile,
    Education,
    Experience,
    Links,
    Location,
    ProvenanceEntry,
    Skill,
)
from transformer.projection import (
    MISSING,
    ProjectionError,
    ProjectionValidationError,
    apply_normalize,
    project,
    project_and_validate,
    resolve_path,
    validate_output,
)


@pytest.fixture
def profile() -> CanonicalProfile:
    return CanonicalProfile(
        candidate_id="cand-001",
        full_name="John Smith",
        emails=["a@x.com", "b@y.com"],
        phones=["+14155550132", "+14155550144"],
        location=Location(city="San Francisco", region="California", country="US"),
        links=Links(linkedin="https://li/in/js", github="https://gh/js", portfolio=None, other=[]),
        headline=None,
        years_experience=8.0,
        skills=[
            Skill(name="Go", confidence=0.99, sources=["ats_json"]),
            Skill(name="Python", confidence=0.9, sources=["ats_json", "github"]),
        ],
        experience=[
            Experience(company="Acme Corp", title="Staff Software Engineer",
                       start="2021-01", end=None, summary=None),
        ],
        education=[Education(institution="MIT", degree="B.S.", field="CS", end_year=2018)],
        provenance=[ProvenanceEntry(field="full_name", source="ats_json", method="ats_field_map")],
        overall_confidence=0.7,
    )


def _data(profile: CanonicalProfile) -> dict:
    return profile.model_dump()


# --------------------------------------------------------------------------- #
# Path mini-language
# --------------------------------------------------------------------------- #
def test_path_scalar(profile) -> None:
    assert resolve_path(_data(profile), "full_name") == "John Smith"


def test_path_nested(profile) -> None:
    assert resolve_path(_data(profile), "location.city") == "San Francisco"


def test_path_index(profile) -> None:
    assert resolve_path(_data(profile), "emails[0]") == "a@x.com"
    assert resolve_path(_data(profile), "phones[1]") == "+14155550144"


def test_path_index_out_of_range_is_missing(profile) -> None:
    assert resolve_path(_data(profile), "emails[5]") is MISSING


def test_path_wildcard_subfield(profile) -> None:
    assert resolve_path(_data(profile), "skills[].name") == ["Go", "Python"]


def test_path_wildcard_whole_list(profile) -> None:
    skills = resolve_path(_data(profile), "skills[]")
    assert isinstance(skills, list) and skills[0]["name"] == "Go"


def test_path_index_then_subfield(profile) -> None:
    assert resolve_path(_data(profile), "skills[0].confidence") == 0.99
    assert resolve_path(_data(profile), "experience[].title") == ["Staff Software Engineer"]


def test_path_null_vs_missing(profile) -> None:
    assert resolve_path(_data(profile), "headline") is None  # present-but-null
    assert resolve_path(_data(profile), "nonexistent") is MISSING


def test_wildcard_on_empty_list_is_empty(profile) -> None:
    profile.skills = []
    assert resolve_path(_data(profile), "skills[].name") == []


# --------------------------------------------------------------------------- #
# Normalize
# --------------------------------------------------------------------------- #
def test_normalize_e164_idempotent() -> None:
    assert apply_normalize("+14155550132", Normalize.E164) == "+14155550132"


def test_normalize_e164_drops_invalid_in_list() -> None:
    assert apply_normalize(["+14155550132", "not-a-phone"], Normalize.E164) == ["+14155550132"]


def test_normalize_canonical() -> None:
    assert apply_normalize(["js", "reactjs"], Normalize.CANONICAL) == ["JavaScript", "React"]


def test_normalize_yyyy_mm() -> None:
    assert apply_normalize("Jan 2021", Normalize.YYYY_MM) == "2021-01"


def test_normalize_string_ops() -> None:
    assert apply_normalize("  Hi ", Normalize.TRIM) == "Hi"
    assert apply_normalize("Hi", Normalize.UPPER) == "HI"
    assert apply_normalize("Hi", Normalize.LOWER) == "hi"


# --------------------------------------------------------------------------- #
# The brief's verbatim example config
# --------------------------------------------------------------------------- #
def test_brief_example_projection(profile) -> None:
    cfg = OutputConfig.from_obj(
        {
            "fields": [
                {"path": "full_name", "type": "string", "required": True},
                {"path": "primary_email", "from": "emails[0]", "type": "string", "required": True},
                {"path": "phone", "from": "phones[0]", "type": "string", "normalize": "E164"},
                {"path": "skills", "from": "skills[].name", "type": "string[]", "normalize": "canonical"},
            ],
            "include_confidence": True,
            "on_missing": "null",
        }
    )
    out = project_and_validate(profile, cfg)
    assert out == {
        "full_name": "John Smith",
        "primary_email": "a@x.com",
        "phone": "+14155550132",
        "skills": ["Go", "Python"],
        "overall_confidence": 0.7,
    }


# --------------------------------------------------------------------------- #
# on_missing modes
# --------------------------------------------------------------------------- #
def _cfg(field: FieldSpec, **kw) -> OutputConfig:
    return OutputConfig(fields=[field], **kw)


def test_on_missing_null(profile) -> None:
    out = project(profile, _cfg(FieldSpec(path="headline", type=FieldType.STRING),
                                on_missing=OnMissing.NULL))
    assert out == {"headline": None}


def test_on_missing_omit(profile) -> None:
    out = project(profile, _cfg(FieldSpec(path="headline", type=FieldType.STRING),
                                on_missing=OnMissing.OMIT))
    assert out == {}  # key dropped


def test_on_missing_error(profile) -> None:
    with pytest.raises(ProjectionError):
        project(profile, _cfg(FieldSpec(path="headline", type=FieldType.STRING),
                              on_missing=OnMissing.ERROR))


def test_per_field_on_missing_override(profile) -> None:
    # Global null, but headline overridden to omit.
    cfg = OutputConfig(
        fields=[
            FieldSpec(path="full_name", type=FieldType.STRING),
            FieldSpec(path="headline", type=FieldType.STRING, on_missing=OnMissing.OMIT),
        ],
        on_missing=OnMissing.NULL,
    )
    out = project(profile, cfg)
    assert out == {"full_name": "John Smith"}  # headline omitted, full_name present


# --------------------------------------------------------------------------- #
# Validation: required + type
# --------------------------------------------------------------------------- #
def test_required_missing_raises(profile) -> None:
    cfg = _cfg(FieldSpec(path="headline", type=FieldType.STRING, required=True),
               on_missing=OnMissing.NULL)
    out = project(profile, cfg)  # projects to {"headline": None}
    with pytest.raises(ProjectionValidationError):
        validate_output(out, cfg)


def test_required_omitted_raises(profile) -> None:
    cfg = _cfg(FieldSpec(path="headline", type=FieldType.STRING, required=True),
               on_missing=OnMissing.OMIT)
    out = project(profile, cfg)  # key dropped
    with pytest.raises(ProjectionValidationError):
        validate_output(out, cfg)


def test_type_validation_failure(profile) -> None:
    # full_name is a string; declaring it a number must fail validation.
    cfg = _cfg(FieldSpec(path="full_name", type=FieldType.NUMBER))
    out = project(profile, cfg)
    with pytest.raises(ProjectionValidationError):
        validate_output(out, cfg)


def test_string_array_type_ok(profile) -> None:
    cfg = _cfg(FieldSpec(path="emails", type=FieldType.STRING_ARRAY))
    out = project_and_validate(profile, cfg)
    assert out == {"emails": ["a@x.com", "b@y.com"]}


def test_object_array_type_ok(profile) -> None:
    cfg = _cfg(FieldSpec(path="skills", type=FieldType.OBJECT_ARRAY))
    out = project_and_validate(profile, cfg)
    assert isinstance(out["skills"], list) and out["skills"][0]["name"] == "Go"


# --------------------------------------------------------------------------- #
# Confidence / provenance toggles
# --------------------------------------------------------------------------- #
def test_include_confidence_toggle(profile) -> None:
    base = FieldSpec(path="full_name", type=FieldType.STRING)
    assert "overall_confidence" in project(profile, _cfg(base, include_confidence=True))
    assert "overall_confidence" not in project(profile, _cfg(base, include_confidence=False))


def test_include_provenance_toggle(profile) -> None:
    base = FieldSpec(path="full_name", type=FieldType.STRING)
    with_prov = project(profile, _cfg(base, include_provenance=True))
    assert isinstance(with_prov["provenance"], list)
    assert "provenance" not in project(profile, _cfg(base, include_provenance=False))


# --------------------------------------------------------------------------- #
# Determinism
# --------------------------------------------------------------------------- #
def test_projection_is_deterministic(profile) -> None:
    cfg = OutputConfig.from_obj(
        {
            "fields": [
                {"path": "full_name", "type": "string"},
                {"path": "skills", "from": "skills[].name", "type": "string[]"},
            ],
            "include_confidence": True,
            "include_provenance": True,
        }
    )
    assert project_and_validate(profile, cfg) == project_and_validate(profile, cfg)
