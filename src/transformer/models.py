"""Canonical data models — the internal source of truth for the whole pipeline.

Everything the deterministic core produces is expressed as a
:class:`CanonicalProfile`.  The *projection* layer (``projection.py``) later maps
this internal model onto whatever output shape a caller's config asks for, so we
keep a hard wall between "what we know about a candidate" (this file) and "what
we choose to emit" (the projection).

Design choices worth defending on the demo:

* **Almost every field is optional.**  Constraint #2 of the brief says a missing
  or garbage source must never crash the run and that *unknown values become
  null — never invented*.  The cleanest way to guarantee that is to make the
  canonical model permissive: only ``candidate_id`` is required (it is the
  identity we merge on); everything else defaults to ``None`` or an empty list.
  Required-ness for a *given output* is enforced later by the projection config,
  not here.

* **Collections default to empty lists, scalars to ``None``.**  This means an
  adapter that finds nothing simply contributes nothing — no sentinel values, no
  fabricated placeholders.

* **Confidence and provenance are first-class.**  Every retained value can be
  traced to a ``(field, source, method)`` provenance entry, and skills/overall
  carry explicit confidence.  These are not optional decorations; they are the
  product.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Source identity + trust weights
# ---------------------------------------------------------------------------


class SourceType(str, Enum):
    """Canonical identifier for each kind of input source.

    The string value is what gets recorded in provenance (``source`` field) and
    is what trust weights are keyed on, so these values are part of the public
    contract — keep them stable.
    """

    ATS_JSON = "ats_json"
    CSV_RECRUITER = "csv_recruiter"
    GITHUB = "github"
    RESUME = "resume"
    NOTES = "notes"
    # Enrichment is the lowest-trust "source".  It never participates in merge or
    # conflict resolution (see merge.py / enrich/) — it only gap-fills fields the
    # deterministic core left null.  We still give it a weight so it sorts
    # predictably and so confidence math has a number to work with.
    LLM = "llm"


# Trust weights drive conflict resolution: when two sources disagree on a field,
# the higher-trust source wins (deterministic tie-break: higher weight, then
# source name alphabetical — implemented in merge.py).
#
# Rationale for the ordering (brief: "ATS/CSV > GitHub > resume prose > notes"):
#   ATS_JSON       100  structured system-of-record, strongly typed fields
#   CSV_RECRUITER   90  structured export, but hand-maintained / lossy formats
#   GITHUB          70  semi-structured public API, self-reported but real
#   RESUME          50  prose; regex/heuristic extraction is inherently noisier
#   NOTES           30  free-text recruiter notes; loosest of all
#   LLM             10  enrichment only; never used as a merge participant
SOURCE_TRUST: dict[SourceType, int] = {
    SourceType.ATS_JSON: 100,
    SourceType.CSV_RECRUITER: 90,
    SourceType.GITHUB: 70,
    SourceType.RESUME: 50,
    SourceType.NOTES: 30,
    SourceType.LLM: 10,
}


def trust_for(source: str) -> int:
    """Return the trust weight for a provenance ``source`` string.

    Accepts both bare source ids (``"ats_json"``) and the enrichment form
    ``"llm:<model_id>"`` (e.g. ``"llm:gemini-2.5-flash"``).  Unknown sources get
    a weight of ``0`` so they always lose a conflict rather than crashing.
    """

    if source.startswith("llm:") or source == SourceType.LLM.value:
        return SOURCE_TRUST[SourceType.LLM]
    try:
        return SOURCE_TRUST[SourceType(source)]
    except ValueError:
        return 0


class Method:
    """Provenance ``method`` vocabulary (string constants, not an enum).

    These are the values that appear in :class:`ProvenanceEntry.method`.  We keep
    them as named constants so adapters/merge can't drift apart via typos, while
    the wire format stays a plain string (easy to read in JSON output).

    The vocabulary mirrors the brief and splits into three groups:

    * *extraction* — how a raw value was located in a source
      (``csv_column``, ``ats_field_map``, ``github_api``, ``regex_extraction``,
      ``heuristic_extraction``);
    * *normalization* — the deterministic transform applied to it
      (``phone_normalize``, ``date_parse``, ``country_normalize``,
      ``skill_canonicalize``);
    * *merge* / *enrichment* — ``merge_winner`` (won a conflict) and
      ``llm_extraction`` (the optional, off-by-default enrichment lane).
    """

    # Extraction
    CSV_COLUMN = "csv_column"
    ATS_FIELD_MAP = "ats_field_map"
    GITHUB_API = "github_api"
    REGEX = "regex_extraction"
    HEURISTIC = "heuristic_extraction"
    # Normalization
    PHONE_NORMALIZE = "phone_normalize"
    DATE_PARSE = "date_parse"
    COUNTRY_NORMALIZE = "country_normalize"
    SKILL_CANONICALIZE = "skill_canonicalize"
    # Merge / enrichment
    MERGE_WINNER = "merge_winner"
    DERIVED_ID = "derived_id"  # candidate_id synthesized from the strongest identifier
    LLM_EXTRACTION = "llm_extraction"


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------

# Shared config for every canonical model:
#   * extra="forbid"  -> typos in field names fail loudly instead of silently
#                        creating phantom attributes (cheap correctness win).
#   * validate_assignment -> mutating a field after construction is re-validated,
#                        which matters because merge.py builds profiles up
#                        incrementally.
_MODEL_CONFIG = ConfigDict(extra="forbid", validate_assignment=True)


class Location(BaseModel):
    """A normalized location.  ``country`` is ISO-3166-1 alpha-2 (e.g. ``"US"``)."""

    model_config = _MODEL_CONFIG

    city: str | None = None
    region: str | None = None  # state / province / region
    country: str | None = None  # ISO-3166-1 alpha-2


class Links(BaseModel):
    """Known web presences for the candidate."""

    model_config = _MODEL_CONFIG

    linkedin: str | None = None
    github: str | None = None
    portfolio: str | None = None
    other: list[str] = Field(default_factory=list)


class Skill(BaseModel):
    """A canonicalized skill.

    ``name`` is the canonical taxonomy name (e.g. ``"React"``, not ``"reactjs"``).
    ``confidence`` reflects how many sources agreed and how cleanly it canonicalized.
    ``sources`` lists every source that contributed it (deduped, sorted).
    """

    model_config = _MODEL_CONFIG

    name: str
    confidence: float = Field(ge=0.0, le=1.0)
    sources: list[str] = Field(default_factory=list)


class Experience(BaseModel):
    """One work-history entry.  ``start``/``end`` are ``"YYYY-MM"`` strings.

    ``end`` may be ``None`` to mean "present"/ongoing.  ``summary`` is one of the
    few prose fields the optional LLM lane may gap-fill (never overwrite).
    """

    model_config = _MODEL_CONFIG

    company: str | None = None
    title: str | None = None
    start: str | None = None  # "YYYY-MM"
    end: str | None = None  # "YYYY-MM" or None == present
    summary: str | None = None


class Education(BaseModel):
    """One education entry."""

    model_config = _MODEL_CONFIG

    institution: str | None = None
    degree: str | None = None
    field: str | None = None
    end_year: int | None = None


class ProvenanceEntry(BaseModel):
    """Audit trail: which ``source`` produced ``field`` via which ``method``.

    Constraint #4: *every output value maps to a (source, method) entry*.  We
    append one of these for every value we retain.  ``method`` is a small
    vocabulary, e.g. ``csv_column``, ``ats_field_map``, ``github_api``,
    ``regex_extraction``, ``date_parse``, ``phone_normalize``,
    ``skill_canonicalize``, ``merge_winner``, ``llm_extraction``.
    """

    model_config = _MODEL_CONFIG

    # Canonical field path. Scalars use their dotted path ("full_name",
    # "location.city"); list/collection fields are recorded at the field level
    # ("emails", "skills", "experience", "education"), with "experience.title"
    # added when a title conflict is resolved. (Per-entry indices like
    # "experience[0]" are intentionally NOT used — entry order is config-driven
    # at projection time, so an index here would be misleading.)
    field: str
    source: str  # source id ("ats_json"), "llm:<model_id>", or "merge" (derived)
    method: str


# ---------------------------------------------------------------------------
# Top-level canonical profile
# ---------------------------------------------------------------------------


class CanonicalProfile(BaseModel):
    """The single, merged, normalized profile for one candidate.

    This is the internal representation only.  Callers never see it directly;
    they see whatever ``projection.py`` derives from it per their output config.
    """

    model_config = _MODEL_CONFIG

    candidate_id: str

    full_name: str | None = None
    emails: list[str] = Field(default_factory=list)
    phones: list[str] = Field(default_factory=list)  # E.164
    location: Location = Field(default_factory=Location)
    links: Links = Field(default_factory=Links)

    headline: str | None = None  # prose; LLM-gap-fillable
    years_experience: float | None = None

    skills: list[Skill] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)

    provenance: list[ProvenanceEntry] = Field(default_factory=list)
    overall_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
