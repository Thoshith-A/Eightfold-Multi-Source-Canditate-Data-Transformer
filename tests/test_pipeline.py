"""Tests for pipeline orchestration + gold-output comparison."""

from __future__ import annotations

from pathlib import Path

import pytest

from transformer import pipeline
from transformer.config import OutputConfig, default_output_config

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "samples" / "sources"
CONFIGS = ROOT / "samples" / "configs"
EXPECTED = ROOT / "samples" / "expected"


# --------------------------------------------------------------------------- #
# Input expansion
# --------------------------------------------------------------------------- #
def test_iter_input_files_expands_directory() -> None:
    files = pipeline.iter_input_files([SOURCES])
    names = {f.name for f in files}
    assert "john_smith_ats.json" in names
    assert "empty_source.csv" in names  # edge files included
    # Sorted + deduped.
    assert files == sorted(files, key=str)


def test_iter_input_files_skips_nonexistent() -> None:
    assert pipeline.iter_input_files([ROOT / "does" / "not" / "exist"]) == []


# --------------------------------------------------------------------------- #
# build_profiles
# --------------------------------------------------------------------------- #
def test_build_profiles_links_all_sources_into_one() -> None:
    profiles = pipeline.build_profiles([SOURCES])
    assert len(profiles) == 1
    assert profiles[0].candidate_id == "cand-001"
    assert profiles[0].full_name == "John Smith"


def test_empty_and_garbage_sources_do_not_crash() -> None:
    # Run on ONLY the two edge files -> no candidates, no exception.
    profiles = pipeline.build_profiles(
        [SOURCES / "empty_source.csv", SOURCES / "garbage_source.json"]
    )
    assert profiles == []


# --------------------------------------------------------------------------- #
# render_json shape
# --------------------------------------------------------------------------- #
def test_render_json_single_object_for_one_candidate() -> None:
    assert pipeline.render_json([{"a": 1}]).startswith("{")


def test_render_json_array_for_many() -> None:
    assert pipeline.render_json([{"a": 1}, {"b": 2}]).startswith("[")


# --------------------------------------------------------------------------- #
# Gold-output comparison (the committed deterministic expectations)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "config_file,gold_file",
    [
        ("default.json", "default.json"),
        ("recruiter_summary.json", "recruiter_summary.json"),
        ("compact_omit.json", "compact_omit.json"),
    ],
)
def test_output_matches_gold(config_file: str, gold_file: str) -> None:
    cfg = OutputConfig.from_file(CONFIGS / config_file)
    produced = pipeline.render_json(pipeline.run([SOURCES], cfg))
    expected = (EXPECTED / gold_file).read_text(encoding="utf-8")
    assert produced == expected


def test_default_flag_config_matches_default_file() -> None:
    # The --default config object and the committed default.json must agree.
    from_obj = pipeline.render_json(pipeline.run([SOURCES], default_output_config()))
    from_file = pipeline.render_json(
        pipeline.run([SOURCES], OutputConfig.from_file(CONFIGS / "default.json"))
    )
    assert from_obj == from_file


def test_compact_omit_drops_null_headline() -> None:
    cfg = OutputConfig.from_file(CONFIGS / "compact_omit.json")
    [out] = pipeline.run([SOURCES], cfg)
    assert "headline" not in out  # on_missing: omit dropped the null
    assert "city" in out and out["city"] == "San Francisco"
