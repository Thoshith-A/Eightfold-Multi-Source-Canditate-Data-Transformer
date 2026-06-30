"""Gemini implementation of the LLM client + the enricher factory.

This is the ONLY module that talks to a provider SDK, and it does so behind the
provider-agnostic :class:`~transformer.enrich.base.LLMClient` interface, so the
enricher itself is testable with any fake/mock client.

Secrets: the API key is read from the ENVIRONMENT ONLY
(``GEMINI_API_KEY`` then ``GOOGLE_API_KEY``) — never from a CLI flag, never
hardcoded, never committed.  If enrichment is requested but no key is present,
:func:`build_enricher_from_config` logs a warning and returns ``None`` so the run
proceeds deterministically.

``google-genai`` is imported lazily *inside* :class:`GeminiClient` so that merely
importing this module (which the CLI does when ``--enrich`` is passed) does not
require the optional ``[llm]`` extra to be installed.
"""

from __future__ import annotations

import logging
import os

from pydantic import BaseModel

from transformer.config import EnrichmentConfig, OutputConfig
from transformer.enrich.base import Enricher
from transformer.enrich.cache import ContentAddressedCache

logger = logging.getLogger("transformer.enrich.llm")

# Cache directory for enriched-path replay. Defaults to the committed fixtures
# dir so the demo replays offline; override with LLM_CACHE_DIR.
DEFAULT_CACHE_DIR = os.environ.get("LLM_CACHE_DIR", "samples/llm_cache")

# Env var names checked, in order. GEMINI_API_KEY wins if both are set.
_API_KEY_VARS = ("GEMINI_API_KEY", "GOOGLE_API_KEY")


def _read_api_key() -> str | None:
    for var in _API_KEY_VARS:
        value = os.environ.get(var)
        if value:
            return value
    return None


class GeminiClient:
    """Calls Gemini via the unified Google Gen AI SDK (`from google import genai`).

    Pinned for determinism as far as the provider allows: ``temperature=0`` and
    ``top_k=1`` (greedy).  Note (and the README states this): even at temperature
    0, providers do NOT guarantee bit-identical outputs across calls — the cache,
    not the model, is what makes the enriched path reproducible.
    """

    def __init__(self, api_key: str, *, temperature: float = 0.0, top_k: int = 1) -> None:
        # Lazy import: importing this module must not require the [llm] extra.
        from google import genai

        self._genai = genai
        self._client = genai.Client(api_key=api_key)
        self._temperature = temperature
        self._top_k = top_k

    def complete_json(self, *, prompt: str, schema: type[BaseModel], model: str) -> str:
        from google.genai import types

        config = types.GenerateContentConfig(
            temperature=self._temperature,
            top_k=self._top_k,
            response_mime_type="application/json",
            response_schema=schema,  # the SDK constrains output to this pydantic schema
        )
        response = self._client.models.generate_content(
            model=model, contents=prompt, config=config
        )
        return response.text or ""


def build_enricher_from_config(config: OutputConfig, *, force: bool = False) -> Enricher | None:
    """Build an :class:`Enricher`, or return ``None`` to run deterministically.

    Returns ``None`` (logging a clear reason) when:
      * enrichment isn't enabled (no ``--enrich`` and no ``enrichment.enabled``);
      * no API key is present in the environment;
      * the ``[llm]`` extra / Gemini client can't be initialized.

    ``force=True`` is set by the CLI's ``--enrich`` flag, which enables the lane
    even if the chosen config has no ``enrichment`` block (using sane defaults).
    """

    settings: EnrichmentConfig | None = config.enrichment
    enabled = force or (settings is not None and settings.enabled)
    if not enabled:
        return None
    if settings is None:
        settings = EnrichmentConfig(enabled=True)  # defaults: gemini flash, headline+summary

    api_key = _read_api_key()
    if not api_key:
        logger.warning(
            "enrichment enabled but no %s in environment; running deterministically "
            "(prose fields stay null).",
            " / ".join(_API_KEY_VARS),
        )
        return None

    try:
        client = GeminiClient(api_key)
    except Exception as exc:  # [llm] extra not installed, or client init failed
        logger.warning(
            "could not initialize the Gemini client (%s); running deterministically. "
            "Install the optional lane with: pip install -e \".[llm]\".",
            exc,
        )
        return None

    return Enricher(
        client,
        model=settings.model,
        cache=ContentAddressedCache(DEFAULT_CACHE_DIR),
        fields=tuple(settings.fields),
    )
