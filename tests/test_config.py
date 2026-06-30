"""Tests for OutputConfig parsing + self-validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from transformer.config import (
    FieldType,
    Normalize,
    OnMissing,
    OutputConfig,
    default_output_config,
)


def test_brief_example_config_parses() -> None:
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
    assert cfg.include_confidence is True
    assert cfg.on_missing is OnMissing.NULL
    # `from` alias maps to source_path; absent `from` falls back to `path`.
    assert cfg.fields[0].source_path == "full_name"
    assert cfg.fields[1].source_path == "emails[0]"
    assert cfg.fields[2].normalize is Normalize.E164
    assert cfg.fields[3].type is FieldType.STRING_ARRAY


def test_default_config_covers_full_schema() -> None:
    cfg = default_output_config()
    paths = {f.path for f in cfg.fields}
    assert paths == {
        "candidate_id", "full_name", "emails", "phones", "location", "links",
        "headline", "years_experience", "skills", "experience", "education",
    }
    assert cfg.include_confidence and cfg.include_provenance


def test_unknown_config_key_is_rejected() -> None:
    with pytest.raises(ValidationError):
        OutputConfig.from_obj({"fields": [], "include_confdence": True})  # typo


def test_unknown_field_key_is_rejected() -> None:
    with pytest.raises(ValidationError):
        OutputConfig.from_obj({"fields": [{"path": "x", "typ": "string"}]})  # typo


def test_invalid_enum_is_rejected() -> None:
    with pytest.raises(ValidationError):
        OutputConfig.from_obj({"fields": [{"path": "x", "type": "stringg"}]})


def test_per_field_on_missing_override_parses() -> None:
    cfg = OutputConfig.from_obj(
        {"fields": [{"path": "headline", "on_missing": "omit"}], "on_missing": "null"}
    )
    assert cfg.on_missing is OnMissing.NULL
    assert cfg.fields[0].on_missing is OnMissing.OMIT
