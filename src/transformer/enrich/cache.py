"""Content-addressed cache for LLM responses — the source of enriched-path replay.

The key is a SHA-256 over ``(model_id, template_version, input_text, schema)``.
Same inputs → same key → the stored response is returned with **no network
call**.  Committing cache fixtures (``samples/llm_cache/``) is what makes tests
and demo replays of the *enriched* path reproducible offline.

Honest determinism note: the provider does NOT guarantee bit-identical outputs
across live calls even at temperature 0 — so reproducibility of the enriched
path comes from THIS cache, not from the model. The default (enrichment-off)
path is the one that satisfies "same inputs → same output" without a cache.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

logger = logging.getLogger("transformer.enrich.cache")


class ContentAddressedCache:
    """Tiny on-disk cache: ``<cache_dir>/<sha256>.json`` -> stored response text."""

    def __init__(self, cache_dir: str | Path) -> None:
        self.cache_dir = Path(cache_dir)

    @staticmethod
    def key(*, model: str, template_version: str, input_text: str, schema: str) -> str:
        """Stable SHA-256 over the four components the brief specifies.

        A NUL separator prevents ambiguity between adjacent components.
        """

        digest = hashlib.sha256()
        for part in (model, template_version, input_text, schema):
            digest.update(part.encode("utf-8"))
            digest.update(b"\x00")
        return digest.hexdigest()

    def get(self, key: str) -> str | None:
        """Return the cached response text for ``key``, or ``None`` on a miss."""

        path = self.cache_dir / f"{key}.json"
        if not path.exists():
            return None
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:  # unreadable cache entry -> treat as a miss
            logger.warning("cache read failed for %s: %s", key, exc)
            return None

    def put(self, key: str, value: str) -> None:
        """Store ``value`` under ``key``. A cache-write failure is non-fatal."""

        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            (self.cache_dir / f"{key}.json").write_text(value, encoding="utf-8")
        except OSError as exc:
            logger.warning("cache write failed for %s: %s (continuing)", key, exc)
