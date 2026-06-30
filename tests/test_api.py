"""Tests for the optional FastAPI layer (skipped if the [web] extra isn't installed).

The API is a thin wrapper over the same pipeline, so these tests focus on the
HTTP contract: routing, file upload, config selection, error handling — and that
the endpoint output matches the deterministic gold (same engine, byte-identical).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")  # the [web] extra is optional

from fastapi.testclient import TestClient  # noqa: E402

from transformer.web.api import app  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "samples" / "sources"
EXPECTED = ROOT / "samples" / "expected"

client = TestClient(app)


def test_health() -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_configs_lists_named_configs() -> None:
    resp = client.get("/api/configs")
    assert resp.status_code == 200
    names = {c["name"] for c in resp.json()["configs"]}
    assert {"default", "recruiter_summary", "compact_omit"} <= names


def test_transform_samples_matches_gold() -> None:
    resp = client.post("/api/transform/samples", data={"config": "default", "enrich": "false"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1 and body["enriched"] is False
    # Same engine -> same bytes as the committed deterministic gold (single object).
    gold = json.loads((EXPECTED / "default.json").read_text(encoding="utf-8"))
    assert body["candidates"][0] == gold


def test_transform_uploaded_files() -> None:
    files = []
    for name in ("john_smith_ats.json", "john_smith_recruiter.csv"):
        files.append(("files", (name, (SOURCES / name).read_bytes(), "application/octet-stream")))
    resp = client.post("/api/transform", files=files, data={"config": "recruiter_summary"})
    assert resp.status_code == 200
    candidate = resp.json()["candidates"][0]
    assert candidate["full_name"] == "John Smith"
    assert candidate["primary_email"]  # projected via emails[0]


def test_unknown_config_returns_400() -> None:
    resp = client.post("/api/transform/samples", data={"config": "does_not_exist"})
    assert resp.status_code == 400
    assert "unknown config" in resp.json()["detail"]


def test_transform_with_no_files_is_rejected() -> None:
    resp = client.post("/api/transform", data={"config": "default"})
    # FastAPI validation (422) for the missing required file field is acceptable.
    assert resp.status_code in (400, 422)


def test_api_matches_cli_pipeline_byte_for_byte() -> None:
    # The web layer must return exactly what the deterministic pipeline produces
    # (same engine, no logic in the UI layer). Compare the API's candidate object
    # to a direct pipeline.run on the same sources + config.
    from transformer import pipeline
    from transformer.config import default_output_config

    api_body = client.post("/api/transform/samples", data={"config": "default"}).json()
    direct = pipeline.run([str(SOURCES)], default_output_config())
    assert api_body["candidates"] == direct

