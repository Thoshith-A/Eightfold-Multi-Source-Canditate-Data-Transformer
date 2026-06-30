"""OPTIONAL, off-by-default LLM enrichment lane.

This subpackage lives OUTSIDE the deterministic core by design.  It runs only
after merge, only fills fields the core left null/empty, never overwrites a
deterministic value, and never participates in conflict resolution.

Importing this package and its base orchestrator requires NO LLM SDK — only the
concrete Gemini client (`transformer.enrich.llm.GeminiClient`) lazily imports
``google-genai`` (the ``[llm]`` extra).  The core never imports this package on
the default path.
"""

from __future__ import annotations

from transformer.enrich.base import (
    LLM_CONFIDENCE,
    TEMPLATE_VERSION,
    EnrichedField,
    Enricher,
    EnrichmentResponse,
    LLMClient,
)
from transformer.enrich.cache import ContentAddressedCache

__all__ = [
    "Enricher",
    "EnrichedField",
    "EnrichmentResponse",
    "LLMClient",
    "ContentAddressedCache",
    "LLM_CONFIDENCE",
    "TEMPLATE_VERSION",
]
