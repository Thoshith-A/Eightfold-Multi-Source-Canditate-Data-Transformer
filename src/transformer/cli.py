"""``transform`` command-line interface (Typer).

Commands:
  transform run     — detect → extract → merge → [enrich] → project → validate
  transform schema  — print the canonical profile JSON schema

The CLI is a thin shell over :mod:`transformer.pipeline`; it holds no transform
logic of its own (the same functions back the optional FastAPI layer).
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import typer

from transformer import pipeline
from transformer.config import OutputConfig, default_output_config
from transformer.models import CanonicalProfile

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Multi-source candidate data transformer (deterministic core).",
)


def _load_config(config: str, default_flag: bool) -> OutputConfig:
    """Resolve the ``--config`` value: the literal 'default'/``--default`` flag,
    or a path to a config JSON file."""

    if default_flag or config.strip().lower() == "default":
        return default_output_config()
    return OutputConfig.from_file(config)


def _maybe_build_enricher(config: OutputConfig, *, force: bool):
    """Build the optional enrichment lane, or return ``None`` (never crash).

    The core never imports the enrichment package. We import it lazily here only
    when enrichment is actually wanted; if the ``[llm]`` extra isn't installed,
    or no API key is in the environment, we log a warning and run deterministically.
    """

    try:
        from transformer.enrich.llm import build_enricher_from_config
    except Exception:
        typer.secho(
            "enrichment requested, but the optional LLM lane is unavailable "
            "(install with 'pip install -e \".[llm]\"'); running deterministically.",
            fg=typer.colors.YELLOW, err=True,
        )
        return None
    return build_enricher_from_config(config, force=force)


@app.command()
def run(
    inputs: list[Path] = typer.Option(
        ..., "--inputs", "-i",
        help="Source file(s) or folder(s). Repeat --inputs or pass a directory.",
    ),
    config: str = typer.Option(
        "default", "--config", "-c",
        help="Path to a config JSON, or 'default' for the full canonical schema.",
    ),
    out: Path | None = typer.Option(
        None, "--out", "-o", help="Write JSON here (default: stdout)."
    ),
    default: bool = typer.Option(
        False, "--default", help="Force the default full-schema config."
    ),
    enrich: bool = typer.Option(
        False, "--enrich/--no-enrich",
        help="Enable the optional LLM enrichment lane (off by default; key from env only).",
    ),
    output_format: str = typer.Option(
        "json", "--format", "-f",
        help="Output shape: 'json' (object/array) or 'ndjson' (one object per line, for scale).",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging to stderr."),
) -> None:
    """Transform candidate sources into config-shaped, schema-valid JSON."""

    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    try:
        cfg = _load_config(config, default)
    except Exception as exc:
        typer.secho(f"config error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    # Enrichment is wanted if the --enrich flag is set OR the config enabled it.
    want_enrich = enrich or (cfg.enrichment is not None and cfg.enrichment.enabled)
    enricher = _maybe_build_enricher(cfg, force=enrich) if want_enrich else None

    try:
        outputs = pipeline.run([str(p) for p in inputs], cfg, enricher=enricher)
    except Exception as exc:
        # Bad config/projection (e.g. required field missing) is a clear user error.
        typer.secho(f"pipeline error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    fmt = output_format.strip().lower()
    if fmt == "ndjson":
        text = pipeline.render_ndjson(outputs)
    elif fmt == "json":
        text = pipeline.render_json(outputs)
    else:
        typer.secho(f"unknown --format {output_format!r} (use 'json' or 'ndjson')",
                    fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    if out is not None:
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8")
        except OSError as exc:
            typer.secho(f"could not write {out}: {exc}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
        typer.secho(
            f"wrote {out} ({len(outputs)} candidate(s))", fg=typer.colors.GREEN, err=True
        )
    else:
        sys.stdout.write(text)


@app.command()
def schema() -> None:
    """Print the canonical profile JSON schema (the internal source of truth)."""

    typer.echo(json.dumps(CanonicalProfile.model_json_schema(), indent=2))


@app.command()
def lint(
    config_path: Path = typer.Argument(..., help="Path to an output-config JSON to validate."),
) -> None:
    """Statically validate a config's source paths/types against the canonical schema.

    Catches mistyped paths (e.g. 'location.citi') that would otherwise silently
    resolve to null/omitted at run time. Exit 1 if any error is found.
    """

    from transformer.projection import lint_config

    try:
        cfg = OutputConfig.from_file(config_path)
    except Exception as exc:
        typer.secho(f"config error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    issues = lint_config(cfg)
    if not issues:
        typer.secho(f"OK: {config_path} — {len(cfg.fields)} field(s), no issues", fg=typer.colors.GREEN, err=True)
        raise typer.Exit(code=0)

    for issue in issues:
        color = typer.colors.RED if issue.severity == "error" else typer.colors.YELLOW
        typer.secho(
            f"{issue.severity.upper()} {issue.path!r} (from {issue.source_path!r}): {issue.message}",
            fg=color, err=True,
        )
    errors = sum(1 for i in issues if i.severity == "error")
    raise typer.Exit(code=1 if errors else 0)


if __name__ == "__main__":  # pragma: no cover
    app()
