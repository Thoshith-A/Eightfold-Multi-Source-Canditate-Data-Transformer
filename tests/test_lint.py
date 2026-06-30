"""Tests for the static config linter (transform lint)."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from transformer.cli import app
from transformer.config import OutputConfig
from transformer.projection import lint_config

ROOT = Path(__file__).resolve().parent.parent
CONFIGS = ROOT / "samples" / "configs"

runner = CliRunner()


def test_all_sample_configs_lint_clean() -> None:
    for name in ("default", "recruiter_summary", "compact_omit", "enriched"):
        cfg = OutputConfig.from_file(CONFIGS / f"{name}.json")
        assert lint_config(cfg) == [], f"{name} should lint clean"


def test_unknown_field_path_is_an_error() -> None:
    cfg = OutputConfig.from_obj({"fields": [{"path": "city", "from": "location.citi", "type": "string"}]})
    issues = lint_config(cfg)
    assert len(issues) == 1
    assert issues[0].severity == "error"
    assert "citi" in issues[0].message


def test_unknown_wildcard_subfield_is_an_error() -> None:
    cfg = OutputConfig.from_obj({"fields": [{"path": "t", "from": "experience[].titel", "type": "string[]"}]})
    issues = lint_config(cfg)
    assert issues and issues[0].severity == "error"
    assert "titel" in issues[0].message


def test_type_mismatch_is_a_warning() -> None:
    # phones is a list[str]; declaring it 'string' is a (non-fatal) mismatch.
    cfg = OutputConfig.from_obj({"fields": [{"path": "phones", "type": "string"}]})
    issues = lint_config(cfg)
    assert len(issues) == 1
    assert issues[0].severity == "warning"
    assert "string[]" in issues[0].message


def test_indexing_a_scalar_is_an_error() -> None:
    cfg = OutputConfig.from_obj({"fields": [{"path": "x", "from": "full_name[0]", "type": "string"}]})
    issues = lint_config(cfg)
    assert issues and issues[0].severity == "error"


def test_cli_lint_clean_exits_zero(tmp_path: Path) -> None:
    result = runner.invoke(app, ["lint", str(CONFIGS / "default.json")])
    assert result.exit_code == 0


def test_cli_lint_bad_config_exits_one(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text('{"fields": [{"path": "city", "from": "loction.city", "type": "string"}]}', encoding="utf-8")
    result = runner.invoke(app, ["lint", str(bad)])
    assert result.exit_code == 1
    assert "ERROR" in result.output


def test_cli_lint_is_byte_stable(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text('{"fields": [{"path": "a", "from": "location.citi", "type": "string"},'
                   ' {"path": "b", "from": "experience[].titel", "type": "string[]"}]}', encoding="utf-8")
    first = runner.invoke(app, ["lint", str(bad)]).output
    second = runner.invoke(app, ["lint", str(bad)]).output
    assert first == second
