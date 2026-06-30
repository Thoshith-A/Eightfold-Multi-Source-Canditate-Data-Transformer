"""Graceful degradation: bad/missing/garbage input never crashes the run (constraint #2)."""

from __future__ import annotations

import os
from pathlib import Path

from transformer import pipeline
from transformer.adapters.base import RawSource
from transformer.models import SourceType

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "samples" / "sources"


def test_only_edge_files_yield_no_candidates() -> None:
    profiles = pipeline.build_profiles(
        [SOURCES / "empty_source.csv", SOURCES / "garbage_source.json"]
    )
    assert profiles == []


def test_nonexistent_input_is_skipped() -> None:
    assert pipeline.build_profiles([ROOT / "nope" / "missing.json"]) == []


def test_unknown_binary_file_is_skipped(tmp_path: Path) -> None:
    mystery = tmp_path / "mystery.bin"
    mystery.write_bytes(os.urandom(256))  # not any known source type
    assert pipeline.build_profiles([mystery]) == []


def test_corrupt_docx_does_not_crash(tmp_path: Path) -> None:
    # Right extension, garbage bytes -> resume adapter detects it, fails to read,
    # returns nothing. No exception escapes.
    broken = tmp_path / "broken.docx"
    broken.write_bytes(os.urandom(512))
    assert pipeline.build_profiles([broken]) == []


def test_pipeline_isolates_adapter_that_raises(monkeypatch) -> None:
    """Even if an adapter throws, the pipeline logs + skips it; the run survives."""

    class Boom:
        source_type = SourceType.NOTES

        def detect(self, raw: RawSource) -> bool:
            return True

        def extract(self, raw: RawSource):
            raise RuntimeError("simulated adapter failure")

    monkeypatch.setattr(pipeline, "detect_adapter", lambda raw: Boom())
    # The notes file is real and readable; the (patched) adapter explodes on extract.
    assert pipeline.build_profiles([SOURCES / "john_smith_notes.txt"]) == []


def test_good_source_survives_alongside_garbage() -> None:
    # A valid ATS file + a corrupt JSON -> the good data still comes through.
    profiles = pipeline.build_profiles(
        [SOURCES / "john_smith_ats.json", SOURCES / "garbage_source.json"]
    )
    assert len(profiles) == 1
    assert profiles[0].candidate_id == "cand-001"
    assert profiles[0].full_name == "John Smith"


def test_missing_fields_become_null_not_invented() -> None:
    # GitHub alone: no email, no headline, no years -> those stay null/empty,
    # never fabricated. candidate_id is derived deterministically from the name.
    [profile] = pipeline.build_profiles([SOURCES / "john_smith_github.json"])
    assert profile.full_name == "John Smith"
    assert profile.emails == []          # GitHub email was null -> stays empty
    assert profile.headline is None      # never invented
    assert profile.years_experience is None
    assert profile.candidate_id == "john_smith"  # derived from normalized name
