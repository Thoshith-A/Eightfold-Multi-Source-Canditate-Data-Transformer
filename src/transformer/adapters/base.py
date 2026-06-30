"""The adapter contract: how every source plugs into the pipeline.

The pipeline never reaches into a source file directly.  Instead each source
type has an *adapter* that does two things:

1. ``detect(raw)``  — cheaply decide "is this input mine?" (extension + a content
   sniff).  This is how the CLI auto-routes an arbitrary file to the right adapter.
2. ``extract(raw)`` — pull out everything it can as a flat list of
   :class:`FieldFragment` objects.

A ``FieldFragment`` is the atomic unit flowing through the pipeline: a single
claim — "this *source* says this *field* has this *value*, extracted via this
*method*, with this *raw_confidence*".  The merge engine consumes fragments from
all sources and resolves them into one :class:`~transformer.models.CanonicalProfile`.

Keeping the adapter output *flat and uniform* (always a list of fragments,
regardless of source) is what lets merge.py stay source-agnostic: it reasons
about fragments and trust weights, never about CSV columns vs PDF prose.

**Normalization happens here, at extraction time.**  Each adapter applies the
shared :mod:`transformer.normalize` functions to its raw values (phones ->
E.164, dates -> ``YYYY-MM``, country -> alpha-2, skills -> canonical), so every
emitted fragment already carries a canonical value *and* records which
normalization produced it (``normalize_method``).  This folds the pipeline's
conceptual "normalize" stage into extraction without a redundant second pass,
and gives provenance the full lineage (extraction method + normalization method).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, ClassVar, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from transformer.models import SourceType

# A pragmatic email matcher: good enough to find/validate the addresses that
# appear in this data without dragging in a full RFC-5322 parser. Used by the
# unstructured adapters (résumé, notes) and reused for light validation.
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


def clean_email(raw: str | None) -> str | None:
    """Normalize an email: trim, lowercase, and validate shape. ``None`` if bad."""

    if not raw:
        return None
    candidate = raw.strip().lower()
    match = EMAIL_RE.fullmatch(candidate)
    return match.group(0) if match else None


class RawSource(BaseModel):
    """A single input handed to the adapters, pre-loaded by the pipeline.

    The pipeline reads the bytes/text once and passes this around so adapters
    don't each re-open the file.  ``text`` is the best-effort UTF-8 decode (it is
    ``None`` for binary formats like PDF/DOCX, where the adapter parses ``path``
    itself).  ``candidate_id_hint`` lets a caller force a grouping id (e.g. when
    a whole folder is known to be one candidate).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    path: Path
    raw_bytes: bytes | None = None
    text: str | None = None
    candidate_id_hint: str | None = None

    @classmethod
    def load(cls, path: str | Path, candidate_id_hint: str | None = None) -> RawSource:
        """Read a file once into a ``RawSource`` (bytes always; text if it decodes).

        Binary formats (PDF/DOCX) won't decode as UTF-8, so ``text`` stays
        ``None`` and the adapter reads ``path`` directly.  Never raises on a
        decode problem — that would defeat the robustness guarantee.
        """

        p = Path(path)
        data = p.read_bytes()
        try:
            text: str | None = data.decode("utf-8")
        except UnicodeDecodeError:
            text = None
        return cls(path=p, raw_bytes=data, text=text, candidate_id_hint=candidate_id_hint)


class FieldFragment(BaseModel):
    """One atomic claim about one canonical field, from one source.

    Examples::

        FieldFragment(field_path="emails", value="a@b.com",
                      source="csv_recruiter", method="csv_column",
                      raw_confidence=0.9)

        FieldFragment(field_path="phones", value="+14155550132",
                      source="csv_recruiter", method="csv_column",
                      normalize_method="phone_normalize", raw_confidence=0.9)

    ``field_path`` uses canonical names (``"full_name"``, ``"emails"``,
    ``"skills"``, ``"experience"`` ...) and dotted sub-paths for nested scalars
    (``"location.city"``, ``"links.github"``).  For list fields an adapter emits
    one fragment per item; merge.py collects/dedupes them.

    ``record_key`` groups fragments that belong to the *same candidate instance
    within one source* — essential because a recruiter CSV holds many rows
    (candidates).  Single-candidate sources (a résumé) use a constant key.  The
    merge layer links records *across* sources via shared identifiers.

    ``method`` is the *extraction* method; ``normalize_method`` (optional) is the
    deterministic transform applied afterwards.  Together they give provenance
    the complete lineage of a value.

    ``raw_confidence`` is the *adapter's own* confidence in this single
    extraction (clean structured column vs. a fuzzy heuristic).  It is one input
    to the final per-field confidence, which also factors in cross-source
    agreement and source trust (see merge.py).
    """

    model_config = ConfigDict(extra="forbid")

    field_path: str
    value: Any
    source: str  # SourceType value, e.g. "csv_recruiter"
    method: str  # extraction method tag, e.g. "csv_column"
    raw_confidence: float = Field(ge=0.0, le=1.0)
    record_key: str = ""  # within-source grouping key (e.g. CSV row id)
    normalize_method: str | None = None  # secondary lineage, e.g. "phone_normalize"


@runtime_checkable
class Adapter(Protocol):
    """Structural contract every source adapter satisfies.

    Adapters are stateless: ``detect`` and ``extract`` take the ``RawSource`` as
    an argument rather than holding it, so a single adapter instance can be
    reused across thousands of inputs without per-file state (scale: no leaks,
    no O(n) memory growth).
    """

    #: Which source this adapter produces fragments for (drives trust weight).
    source_type: ClassVar[SourceType]

    def detect(self, raw: RawSource) -> bool:
        """Return ``True`` if this adapter can handle ``raw``.

        Must be cheap and side-effect free — the pipeline calls ``detect`` on
        every adapter to route an input.  Must never raise.
        """
        ...

    def extract(self, raw: RawSource) -> list[FieldFragment]:
        """Pull every fragment this adapter can find from ``raw``.

        Should be robust: on partially-malformed input, return what *can* be
        parsed rather than raising.  The pipeline additionally wraps every
        ``extract`` call in try/except (constraint #2), so a hard failure here
        is contained to this one source — but well-behaved adapters degrade
        gracefully on their own.
        """
        ...
