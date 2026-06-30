"""Tests for the optional enrichment lane — LLM client MOCKED, no network.

Covers every requirement from the brief:
  * disabled by default -> output byte-identical to the deterministic run
  * fills ONLY empty fields; never overwrites a deterministic value
  * schema/parse failure from the (mocked) client -> field stays null
  * client raises (network/quota/bad key) -> run does NOT crash; fields null
  * cache hit returns the stored response (reproducibility/replay) — offline, no key
  * LLM-derived value carries the low confidence + provenance method "llm_extraction"
  * cost guard: a candidate with no gaps triggers no call
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from transformer import pipeline
from transformer.config import OutputConfig
from transformer.enrich.base import LLM_CONFIDENCE, Enricher
from transformer.enrich.cache import ContentAddressedCache
from transformer.projection import project_and_validate

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "samples" / "sources"
CONFIGS = ROOT / "samples" / "configs"
EXPECTED = ROOT / "samples" / "expected"
COMMITTED_CACHE = ROOT / "samples" / "llm_cache"

MODEL = "gemini-2.5-flash"

_GOOD_RESPONSE = json.dumps({
    "headline": "Senior Software Engineer",
    "experience": [
        {"company": "Acme Corp", "summary": "Led platform reliability work and mentored junior engineers."},
        {"company": "Globex Inc", "summary": "Built internal tooling and data pipelines."},
    ],
})


# --- test doubles ---------------------------------------------------------- #
class FakeClient:
    """Returns a canned JSON string; records whether it was called."""

    def __init__(self, response: str) -> None:
        self.response = response
        self.calls = 0

    def complete_json(self, *, prompt, schema, model):
        self.calls += 1
        return self.response


class RaisingClient:
    """Simulates a network/quota/bad-key failure."""

    def complete_json(self, *, prompt, schema, model):
        raise RuntimeError("simulated network/quota error")


class NeverCallClient:
    """Fails the test if the model is ever actually called (proves cache hits)."""

    def complete_json(self, *, prompt, schema, model):  # pragma: no cover
        raise AssertionError("client must not be called (expected cache hit / no gaps)")


# --- fixtures -------------------------------------------------------------- #
@pytest.fixture
def extractions():
    return pipeline.collect_extractions(pipeline.iter_input_files([SOURCES]))


@pytest.fixture
def core_profiles(extractions):
    return pipeline.merge(pipeline._flatten(extractions))


# --------------------------------------------------------------------------- #
def test_disabled_by_default_is_byte_identical_to_deterministic() -> None:
    cfg = OutputConfig.from_file(CONFIGS / "default.json")
    produced = pipeline.render_json(pipeline.run([SOURCES], cfg, enricher=None))
    assert produced == (EXPECTED / "default.json").read_text(encoding="utf-8")


def test_fills_only_empty_never_overwrites(tmp_path, core_profiles, extractions) -> None:
    # Pre-set headline + the FIRST experience summary; leave the second empty.
    [profile] = core_profiles
    preset = profile.model_copy(deep=True)
    preset.headline = "Existing Headline"
    preset.experience[0].summary = "Existing summary — must be preserved"

    enricher = Enricher(FakeClient(_GOOD_RESPONSE), model=MODEL,
                        cache=ContentAddressedCache(tmp_path))
    [out] = enricher.enrich_profiles([preset], extractions)

    assert out.headline == "Existing Headline"                      # not overwritten
    assert out.experience[0].summary == "Existing summary — must be preserved"  # not overwritten
    assert out.experience[1].summary == "Built internal tooling and data pipelines."  # gap filled


def test_invalid_json_leaves_fields_null(tmp_path, core_profiles, extractions) -> None:
    enricher = Enricher(FakeClient("this is not valid json {{{"), model=MODEL,
                        cache=ContentAddressedCache(tmp_path))
    [out] = enricher.enrich_profiles(core_profiles, extractions)
    assert out.headline is None                # parse failure -> stays null
    assert all(e.summary is None for e in out.experience)
    assert enricher.report == []               # nothing recorded


def test_client_error_does_not_crash_and_leaves_null(tmp_path, core_profiles, extractions) -> None:
    enricher = Enricher(RaisingClient(), model=MODEL, cache=ContentAddressedCache(tmp_path))
    [out] = enricher.enrich_profiles(core_profiles, extractions)  # must not raise
    assert out.headline is None
    assert all(e.summary is None for e in out.experience)


def test_cache_hit_avoids_client_call(core_profiles, extractions) -> None:
    # Committed fixture + a client that explodes if called -> proves offline replay.
    enricher = Enricher(NeverCallClient(), model=MODEL,
                        cache=ContentAddressedCache(COMMITTED_CACHE))
    [out] = enricher.enrich_profiles(core_profiles, extractions)
    assert out.headline == "Senior Software Engineer"
    assert out.experience[0].summary  # filled from cache
    assert all(r.cache_hit for r in enricher.report)


def test_llm_value_low_confidence_and_provenance(tmp_path, core_profiles, extractions) -> None:
    enricher = Enricher(FakeClient(_GOOD_RESPONSE), model=MODEL,
                        cache=ContentAddressedCache(tmp_path))
    [out] = enricher.enrich_profiles(core_profiles, extractions)

    # Fixed low confidence, llm source + method on every filled field.
    assert enricher.report, "expected at least one filled field"
    for filled in enricher.report:
        assert filled.confidence == LLM_CONFIDENCE
        assert filled.method == "llm_extraction"
        assert filled.source == f"llm:{MODEL}"

    prov = {(p.field, p.source, p.method) for p in out.provenance}
    assert ("headline", f"llm:{MODEL}", "llm_extraction") in prov
    assert ("experience.summary", f"llm:{MODEL}", "llm_extraction") in prov


def test_no_gaps_triggers_no_call(tmp_path, core_profiles, extractions) -> None:
    [profile] = core_profiles
    full = profile.model_copy(deep=True)
    full.headline = "Already set"
    for exp in full.experience:
        exp.summary = "Already summarized"

    enricher = Enricher(NeverCallClient(), model=MODEL, cache=ContentAddressedCache(tmp_path))
    [out] = enricher.enrich_profiles([full], extractions)  # NeverCallClient must not fire
    assert out == full
    assert enricher.report == []


def test_enriched_gold_reproducible_from_committed_cache(core_profiles, extractions) -> None:
    # The committed enriched gold must be reproducible offline from the committed
    # cache fixture — no key, no network.
    enricher = Enricher(NeverCallClient(), model=MODEL,
                        cache=ContentAddressedCache(COMMITTED_CACHE))
    enriched = enricher.enrich_profiles(core_profiles, extractions)
    cfg = OutputConfig.from_file(CONFIGS / "enriched.json")
    produced = pipeline.render_json([project_and_validate(p, cfg) for p in enriched])
    assert produced == (EXPECTED / "enriched.json").read_text(encoding="utf-8")
