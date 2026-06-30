"""Determinism: identical inputs -> byte-identical output (enrichment OFF).

This is constraint #1. We prove it three ways:
  * same inputs, run twice in-process -> equal;
  * input file order shuffled -> equal (sorting makes order irrelevant);
  * run in two *separate processes* with different PYTHONHASHSEED -> byte-identical
    stdout (guards against any accidental reliance on set/dict iteration order).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from transformer import pipeline
from transformer.config import OutputConfig

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "samples" / "sources"
CONFIGS = ROOT / "samples" / "configs"

_ALL_CONFIGS = ["default.json", "recruiter_summary.json", "compact_omit.json"]


@pytest.mark.parametrize("config_file", _ALL_CONFIGS)
def test_run_twice_is_byte_identical(config_file: str) -> None:
    cfg = OutputConfig.from_file(CONFIGS / config_file)
    first = pipeline.render_json(pipeline.run([SOURCES], cfg))
    second = pipeline.render_json(pipeline.run([SOURCES], cfg))
    assert first == second


def test_build_profiles_twice_equal() -> None:
    assert pipeline.build_profiles([SOURCES]) == pipeline.build_profiles([SOURCES])


def test_input_file_order_does_not_matter() -> None:
    files = pipeline.iter_input_files([SOURCES])
    cfg = OutputConfig.from_file(CONFIGS / "default.json")
    forward = pipeline.render_json(pipeline.run(files, cfg))
    reverse = pipeline.render_json(pipeline.run(list(reversed(files)), cfg))
    assert forward == reverse


def test_cross_process_hashseed_independence() -> None:
    """Two processes, different PYTHONHASHSEED -> identical bytes on stdout."""

    def run_with_seed(seed: str) -> str:
        env = dict(os.environ, PYTHONHASHSEED=seed)
        proc = subprocess.run(
            [sys.executable, "-m", "transformer.cli", "run", "-i", str(SOURCES), "--default"],
            cwd=str(ROOT), env=env, capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stderr
        return proc.stdout

    assert run_with_seed("0") == run_with_seed("13499")
