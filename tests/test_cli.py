"""Tests for the Typer CLI (via Click's CliRunner — no subprocess)."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from transformer.cli import app

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "samples" / "sources"
CONFIGS = ROOT / "samples" / "configs"

runner = CliRunner()


def test_run_default_to_file(tmp_path: Path) -> None:
    out = tmp_path / "out.json"
    result = runner.invoke(
        app, ["run", "-i", str(SOURCES), "--default", "-o", str(out)]
    )
    assert result.exit_code == 0, result.output
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["candidate_id"] == "cand-001"
    assert data["full_name"] == "John Smith"
    assert "provenance" in data


def test_run_custom_config_to_file(tmp_path: Path) -> None:
    out = tmp_path / "summary.json"
    result = runner.invoke(
        app,
        ["run", "-i", str(SOURCES), "-c", str(CONFIGS / "recruiter_summary.json"), "-o", str(out)],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["primary_email"] == "j.smith@workmail.com"
    assert data["phone"] == "+14155550132"


def test_run_bad_config_path_exits_cleanly() -> None:
    result = runner.invoke(app, ["run", "-i", str(SOURCES), "-c", "no_such_config.json"])
    assert result.exit_code == 1
    assert "config error" in result.output.lower()


def test_schema_command() -> None:
    result = runner.invoke(app, ["schema"])
    assert result.exit_code == 0
    assert "candidate_id" in result.output


def test_enrich_flag_without_lane_runs_deterministically(tmp_path: Path) -> None:
    # --enrich with the LLM lane not installed -> warn + identical deterministic output.
    plain = tmp_path / "plain.json"
    enriched = tmp_path / "enriched.json"
    runner.invoke(app, ["run", "-i", str(SOURCES), "--default", "-o", str(plain)])
    result = runner.invoke(app, ["run", "-i", str(SOURCES), "--default", "--enrich", "-o", str(enriched)])
    assert result.exit_code == 0
    assert plain.read_text(encoding="utf-8") == enriched.read_text(encoding="utf-8")
