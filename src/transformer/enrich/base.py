"""The enrichment lane: gap-fill prose-only fields, fenced outside the core.

This runs AFTER merge and touches ONLY fields the deterministic engine left
null/empty — `headline` and experience `summary`.  It NEVER overwrites a
deterministic value, NEVER participates in conflict resolution, and NEVER runs
for phones/emails/dates/skills/years (those stay 100% deterministic).

Guarantees enforced here (so the LLM can't violate the brief):

* **Extract-or-null, never invent** — the prompt forbids inference; the schema
  permits null.
* **Structured + validated** — the model is constrained to a strict JSON schema
  and the response is re-validated with pydantic; ANY parse/validation failure
  makes the field stay null (never partial/garbage).
* **Failure-isolated** — any client error (network/quota/bad key/timeout) is
  caught; affected fields stay null; the run continues.
* **Reproducible via cache** — responses are content-addressed; a cache hit
  needs no network call.
* **Low confidence + provenance** — every filled value gets a fixed low
  confidence (:data:`LLM_CONFIDENCE`) recorded in the run report, and a
  provenance entry ``{field, source: "llm:<model>", method: "llm_extraction"}``.
* **Scale/cost guard** — only candidates with actual gaps trigger a call, and a
  ``max_calls`` cap bounds live invocations.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from transformer.adapters.base import FieldFragment, RawSource
from transformer.enrich.cache import ContentAddressedCache
from transformer.enrich.context import build_context
from transformer.merge import normalize_company
from transformer.models import CanonicalProfile, Method, ProvenanceEntry

logger = logging.getLogger("transformer.enrich")

# Bump this whenever the prompt changes — it's part of the cache key, so a new
# template never silently reuses an old cached response.
TEMPLATE_VERSION = "headline-summary-v1"

# Fixed, low confidence assigned to every LLM-derived value (auditable in the
# run report; the canonical schema has no per-field scalar confidence slot, so
# this lives in run metadata, not in the profile).
LLM_CONFIDENCE = 0.4

# Defensive cap on prompt size (prose context can be large for real résumés).
_MAX_CONTEXT_CHARS = 8000


# --------------------------------------------------------------------------- #
# Strict response schema (what the model is constrained to return)
# --------------------------------------------------------------------------- #
class ExperienceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company: str
    summary: str | None = None


class EnrichmentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    headline: str | None = None
    experience: list[ExperienceSummary] = Field(default_factory=list)


def _schema_fingerprint() -> str:
    """Stable string form of the response schema, for the cache key."""

    return json.dumps(EnrichmentResponse.model_json_schema(), sort_keys=True)


# --------------------------------------------------------------------------- #
# Provider-agnostic client contract + run report
# --------------------------------------------------------------------------- #
@runtime_checkable
class LLMClient(Protocol):
    """Minimal, provider-agnostic LLM interface (Gemini impl ships in ``llm.py``).

    Implementations must request structured JSON constrained to ``schema`` at
    temperature 0, and return the raw JSON text.  They may raise on
    network/quota/auth errors — the enricher catches those.
    """

    def complete_json(self, *, prompt: str, schema: type[BaseModel], model: str) -> str:
        ...


@dataclass
class EnrichedField:
    """One audit record of an LLM-filled value (run metadata, not in the schema)."""

    candidate_id: str
    field: str
    value: Any
    confidence: float
    source: str
    method: str
    cache_hit: bool


def _render_prompt(context_text: str) -> str:
    """The extract-or-null prompt. Phrasing is part of the auditable template."""

    return (
        "You are a precise information extractor for a candidate profile.\n"
        "Use ONLY the text provided below. Do NOT infer, guess, or embellish.\n"
        "If a value is not explicitly supported by the text, return null for it.\n\n"
        "Return JSON with exactly these fields:\n"
        '- "headline": a short professional headline/title for the candidate\n'
        '  (e.g. "Senior Software Engineer") ONLY if such a title is explicitly\n'
        "  stated in the text; otherwise null.\n"
        '- "experience": a list of objects {"company", "summary"} — one per\n'
        "  company named in the text. \"summary\" is a 1-2 sentence description\n"
        "  built ONLY from facts present in the text, or null if the text says\n"
        "  nothing about that role.\n\n"
        "CANDIDATE SOURCE TEXT:\n"
        f"{context_text}"
    )


class Enricher:
    """Orchestrates gap-fill enrichment over merged profiles (off the core path)."""

    def __init__(
        self,
        client: LLMClient,
        *,
        model: str,
        cache: ContentAddressedCache,
        fields: tuple[str, ...] = ("headline", "summary"),
        confidence: float = LLM_CONFIDENCE,
        max_calls: int = 1000,
    ) -> None:
        self._client = client
        self._model = model
        self._cache = cache
        self._fields = fields
        self._confidence = confidence
        self._max_calls = max_calls
        #: Audit trail of what was filled this run (model metadata, cache hits).
        self.report: list[EnrichedField] = []

    # -- pipeline.Enricher protocol -------------------------------------------
    def enrich_profiles(
        self,
        profiles: list[CanonicalProfile],
        extractions: list[tuple[RawSource, list[FieldFragment]]],
    ) -> list[CanonicalProfile]:
        self.report = []
        live_calls = 0
        out: list[CanonicalProfile] = []

        for profile in profiles:
            if not self._has_gaps(profile):
                out.append(profile)  # nothing to fill -> no call (cost guard)
                continue

            context = build_context(profile, extractions)[:_MAX_CONTEXT_CHARS]
            if not context.strip():
                out.append(profile)  # no prose to extract from -> leave null
                continue

            if live_calls >= self._max_calls:
                logger.warning("enrichment call cap (%d) reached; skipping further candidates",
                               self._max_calls)
                out.append(profile)
                continue

            response, cache_hit = self._fetch(context)
            if not cache_hit:
                live_calls += 1
            if response is None:
                out.append(profile)  # error or invalid JSON -> fields stay null
                continue

            out.append(self._apply(profile, response, cache_hit))

        return out

    # -- internals ------------------------------------------------------------
    def _has_gaps(self, profile: CanonicalProfile) -> bool:
        if "headline" in self._fields and not profile.headline:
            return True
        if "summary" in self._fields and any(not e.summary for e in profile.experience):
            return True
        return False

    def _fetch(self, context: str) -> tuple[EnrichmentResponse | None, bool]:
        """Cache-aware fetch. Returns (validated response | None, cache_hit).

        ``None`` means "leave fields null": either the client errored or the
        response failed schema validation. Never raises.
        """

        key = self._cache.key(
            model=self._model,
            template_version=TEMPLATE_VERSION,
            input_text=context,
            schema=_schema_fingerprint(),
        )
        raw = self._cache.get(key)
        cache_hit = raw is not None

        if not cache_hit:
            try:
                raw = self._client.complete_json(
                    prompt=_render_prompt(context),
                    schema=EnrichmentResponse,
                    model=self._model,
                )
            except Exception as exc:  # network / quota / bad key / timeout
                logger.warning("enrichment call failed: %s; leaving fields null", exc)
                return None, False
            self._cache.put(key, raw)

        try:
            return EnrichmentResponse.model_validate_json(raw or ""), cache_hit
        except (ValidationError, ValueError) as exc:
            logger.warning("enrichment response failed validation: %s; leaving fields null", exc)
            return None, cache_hit

    def _apply(
        self, profile: CanonicalProfile, response: EnrichmentResponse, cache_hit: bool
    ) -> CanonicalProfile:
        """Gap-fill ONLY empty fields; record provenance + a report entry per fill."""

        enriched = profile.model_copy(deep=True)
        source = f"llm:{self._model}"
        prov: set[tuple[str, str, str]] = {(p.field, p.source, p.method) for p in enriched.provenance}

        def record(field_path: str, value: Any) -> None:
            prov.add((field_path, source, Method.LLM_EXTRACTION))
            self.report.append(
                EnrichedField(enriched.candidate_id, field_path, value,
                              self._confidence, source, Method.LLM_EXTRACTION, cache_hit)
            )

        if "headline" in self._fields and not enriched.headline and response.headline:
            enriched.headline = response.headline
            record("headline", response.headline)

        if "summary" in self._fields:
            by_company = {
                normalize_company(item.company): item.summary
                for item in response.experience
                if item.summary
            }
            for exp in enriched.experience:
                if exp.summary:  # never overwrite a deterministic value
                    continue
                summary = by_company.get(normalize_company(exp.company or ""))
                if summary:
                    exp.summary = summary
                    record("experience.summary", summary)

        # Re-emit provenance deterministically (sorted, deduped).
        enriched.provenance = [
            ProvenanceEntry(field=f, source=s, method=m) for (f, s, m) in sorted(prov)
        ]
        return enriched
