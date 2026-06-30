"""Tests for NDJSON output mode (--format ndjson) — scale-friendly streaming shape."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from transformer import pipeline
from transformer.cli import app
from transformer.config import default_output_config

ROOT = Path(__file__).resolve().parent.parent
SCALE_CSV = ROOT / "samples" / "scale" / "candidates.csv"
SOURCES = ROOT / "samples" / "sources"

runner = CliRunner()


def test_ndjson_one_object_per_candidate_in_order() -> None:
    outputs = pipeline.run([SCALE_CSV], default_output_config())
    text = pipeline.render_ndjson(outputs)
    lines = text.splitlines()
    assert len(lines) == len(outputs) == 3
    parsed = [json.loads(ln) for ln in lines]
    # Content parity with the array form, in candidate_id order.
    assert parsed == outputs
    assert [p["candidate_id"] for p in parsed] == ["cand-100", "cand-101", "cand-102"]


def test_ndjson_single_candidate_is_one_line() -> None:
    outputs = pipeline.run([SOURCES], default_output_config())
    text = pipeline.render_ndjson(outputs)
    assert text.count("\n") == 1
    assert text.endswith("\n")


def test_ndjson_is_deterministic_and_order_independent() -> None:
    cfg = default_output_config()
    files = pipeline.iter_input_files([SCALE_CSV])
    a = pipeline.render_ndjson(pipeline.run(files, cfg))
    b = pipeline.render_ndjson(pipeline.run(list(reversed(files)), cfg))
    assert a == b == pipeline.render_ndjson(pipeline.run([SCALE_CSV], cfg))


def test_cli_format_ndjson(tmp_path: Path) -> None:
    out = tmp_path / "out.ndjson"
    result = runner.invoke(app, ["run", "-i", str(SCALE_CSV), "--default", "-f", "ndjson", "-o", str(out)])
    assert result.exit_code == 0
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert all(json.loads(ln)["candidate_id"].startswith("cand-1") for ln in lines)


def test_cli_unknown_format_errors() -> None:
    result = runner.invoke(app, ["run", "-i", str(SOURCES), "--default", "-f", "yaml"])
    assert result.exit_code == 1
    assert "unknown --format" in result.output
