"""Runtime output configuration — parsed and self-validated with pydantic.

An :class:`OutputConfig` describes *what shape* a caller wants out of the engine,
entirely at runtime: which canonical paths map to which output keys, what type
each should be, whether it's required, what normalization to re-apply, and how to
treat missing values.  The projection engine (``projection.py``) consumes this;
no code changes are needed to support a new output shape.

The config is itself validated by pydantic (``extra="forbid"`` everywhere), so a
typo'd key or an unknown enum value fails loudly at load time rather than
silently producing wrong output — important when the output feeds an ATS.
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class OnMissing(str, Enum):
    """What to do when a field's source path resolves to nothing/null."""

    NULL = "null"   # emit the key with a null value
    OMIT = "omit"   # drop the key entirely
    ERROR = "error"  # raise — caller wants missing data to be a hard failure


class FieldType(str, Enum):
    """Declared output type for a projected field (validated post-projection)."""

    STRING = "string"
    STRING_ARRAY = "string[]"
    NUMBER = "number"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    OBJECT = "object"
    OBJECT_ARRAY = "object[]"
    ANY = "any"


class Normalize(str, Enum):
    """Normalization to (re-)apply at projection time.

    The canonical record is already normalized by the core, so these are usually
    idempotent — but applying them at projection guarantees the output honors the
    declared format regardless of which path it was pulled from.
    """

    E164 = "E164"            # phone -> E.164
    CANONICAL = "canonical"  # skill -> canonical taxonomy name
    YYYY_MM = "YYYY-MM"      # date -> "YYYY-MM"
    LOWER = "lower"
    UPPER = "upper"
    TRIM = "trim"


class FieldSpec(BaseModel):
    """One output field: where it comes from, its type, and how to treat it."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    path: str  # the OUTPUT key
    # The canonical source path (mini-language). ``from`` is a Python keyword, so
    # the attribute is ``from_`` with a JSON alias of "from". Defaults to ``path``.
    from_: str | None = Field(default=None, alias="from")
    type: FieldType = FieldType.ANY
    required: bool = False
    normalize: Normalize | None = None
    on_missing: OnMissing | None = None  # per-field override of the global default

    @property
    def source_path(self) -> str:
        """The canonical path to read from (``from`` if set, else ``path``)."""

        return self.from_ if self.from_ is not None else self.path


class EnrichmentConfig(BaseModel):
    """Optional LLM enrichment settings (consumed by the Stage 8 lane; OFF here)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    provider: str = "gemini"
    model: str = "gemini-2.5-flash"
    fields: list[str] = Field(default_factory=lambda: ["headline", "summary"])


class OutputConfig(BaseModel):
    """The full runtime output configuration."""

    model_config = ConfigDict(extra="forbid")

    fields: list[FieldSpec]
    include_confidence: bool = False
    include_provenance: bool = False
    on_missing: OnMissing = OnMissing.NULL
    enrichment: EnrichmentConfig | None = None

    @classmethod
    def from_obj(cls, obj: dict) -> OutputConfig:
        """Validate a plain dict (e.g. parsed JSON) into an OutputConfig."""

        return cls.model_validate(obj)

    @classmethod
    def from_file(cls, path: str | Path) -> OutputConfig:
        """Load + validate a config JSON file."""

        with Path(path).open("r", encoding="utf-8") as fh:
            return cls.from_obj(json.load(fh))


def default_output_config() -> OutputConfig:
    """The ``--default`` config: every canonical field, 1:1, full schema.

    Emits the complete canonical profile through the *same* projection engine
    (confidence + provenance included), so the default output is just a special
    case of the configurable path — not a separate code path.
    """

    return OutputConfig(
        fields=[
            FieldSpec(path="candidate_id", type=FieldType.STRING, required=True),
            FieldSpec(path="full_name", type=FieldType.STRING),
            FieldSpec(path="emails", type=FieldType.STRING_ARRAY),
            FieldSpec(path="phones", type=FieldType.STRING_ARRAY),
            FieldSpec(path="location", type=FieldType.OBJECT),
            FieldSpec(path="links", type=FieldType.OBJECT),
            FieldSpec(path="headline", type=FieldType.STRING),
            FieldSpec(path="years_experience", type=FieldType.NUMBER),
            FieldSpec(path="skills", type=FieldType.OBJECT_ARRAY),
            FieldSpec(path="experience", type=FieldType.OBJECT_ARRAY),
            FieldSpec(path="education", type=FieldType.OBJECT_ARRAY),
        ],
        include_confidence=True,
        include_provenance=True,
        on_missing=OnMissing.NULL,
    )
