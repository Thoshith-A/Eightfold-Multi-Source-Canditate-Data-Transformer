"""FastAPI app exposing the transformer over HTTP — a thin shell, no logic.

Endpoints:
  GET  /api/health    — liveness.
  GET  /api/configs   — the named sample configs (so the UI can offer them).
  POST /api/transform — upload sources + pick a config (+ optional enrich) ->
                        runs the SAME pipeline and returns the projected JSON
                        plus any enrichment audit report.

Every request ultimately calls :func:`transformer.pipeline.run`; this module
adds no extraction/merge/projection logic of its own. The built React frontend
(``web/frontend/dist``) is served at ``/`` when present.
"""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from transformer import pipeline
from transformer.config import OutputConfig, default_output_config

logger = logging.getLogger("transformer.web")

# Named configs the UI can pick from (the committed samples).
_REPO_ROOT = Path(__file__).resolve().parents[3]
_CONFIG_DIR = _REPO_ROOT / "samples" / "configs"
_FRONTEND_DIST = _REPO_ROOT / "web" / "frontend" / "dist"

app = FastAPI(title="Multi-Source Candidate Data Transformer", version="0.1.0")

# Dev convenience: the Vite dev server runs on a different port. Tighten/remove
# for production deployments.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _resolve_config(config: str) -> OutputConfig:
    """Resolve a config selector: 'default', a named sample, or inline JSON."""

    text = (config or "default").strip()
    if text == "default":
        return default_output_config()
    if text.startswith("{"):
        # Inline JSON config (validated by pydantic; bad keys rejected).
        return OutputConfig.from_obj(json.loads(text))
    path = _CONFIG_DIR / f"{text}.json"
    if not path.exists():
        raise HTTPException(status_code=400, detail=f"unknown config: {text!r}")
    return OutputConfig.from_file(path)


def _build_enricher(config: OutputConfig, *, force: bool):
    """Build the optional enricher, or return ``None`` (never crash the request)."""

    try:
        from transformer.enrich.llm import build_enricher_from_config
    except Exception:
        return None
    return build_enricher_from_config(config, force=force)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/configs")
def configs() -> dict[str, Any]:
    """Return the available named configs (name + parsed content) for the UI."""

    items = [{"name": "default", "config": default_output_config().model_dump(by_alias=True)}]
    if _CONFIG_DIR.exists():
        for path in sorted(_CONFIG_DIR.glob("*.json")):
            try:
                items.append({
                    "name": path.stem,
                    "config": OutputConfig.from_file(path).model_dump(by_alias=True),
                })
            except Exception as exc:  # a malformed sample config shouldn't 500 the list
                logger.warning("skipping unparseable config %s: %s", path, exc)
    return {"configs": items}


@app.post("/api/transform")
async def transform(
    files: list[UploadFile] = File(...),
    config: str = Form("default"),
    enrich: bool = Form(False),
) -> dict[str, Any]:
    """Run the pipeline over uploaded sources and return projected candidate(s)."""

    if not files:
        raise HTTPException(status_code=400, detail="no files uploaded")

    try:
        cfg = _resolve_config(config)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"invalid inline config JSON: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"config error: {exc}")

    # Persist uploads to an isolated temp dir, then run the SAME pipeline on them.
    with tempfile.TemporaryDirectory(prefix="transform_") as tmp:
        tmp_dir = Path(tmp)
        for upload in files:
            # Use only the basename to avoid path traversal from the filename.
            safe_name = Path(upload.filename or "source").name
            (tmp_dir / safe_name).write_bytes(await upload.read())

        want_enrich = enrich or (cfg.enrichment is not None and cfg.enrichment.enabled)
        enricher = _build_enricher(cfg, force=enrich) if want_enrich else None

        try:
            outputs = pipeline.run([str(tmp_dir)], cfg, enricher=enricher)
        except Exception as exc:  # projection/validation error -> clean 400
            raise HTTPException(status_code=400, detail=f"transform failed: {exc}")

        report = [vars(entry) for entry in getattr(enricher, "report", [])] if enricher else []

    return {
        "candidates": outputs,
        "count": len(outputs),
        "enriched": enricher is not None,
        "enrichment_report": report,
    }


@app.post("/api/transform/samples")
def transform_samples(config: str = Form("default"), enrich: bool = Form(False)) -> dict[str, Any]:
    """Run the pipeline over the committed sample sources (one-click demo)."""

    sources = _REPO_ROOT / "samples" / "sources"
    if not sources.exists():
        raise HTTPException(status_code=404, detail="bundled samples not found")
    try:
        cfg = _resolve_config(config)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"config error: {exc}")

    want_enrich = enrich or (cfg.enrichment is not None and cfg.enrichment.enabled)
    enricher = _build_enricher(cfg, force=enrich) if want_enrich else None
    try:
        outputs = pipeline.run([str(sources)], cfg, enricher=enricher)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"transform failed: {exc}")
    report = [vars(entry) for entry in getattr(enricher, "report", [])] if enricher else []
    return {
        "candidates": outputs,
        "count": len(outputs),
        "enriched": enricher is not None,
        "enrichment_report": report,
    }


# Serve the built frontend at "/" if it has been built (`npm run build`).
if _FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend")

