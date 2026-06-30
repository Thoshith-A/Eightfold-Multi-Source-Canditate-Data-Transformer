"""Candidate Data Transformer.

A deterministic pipeline that turns messy multi-source candidate data into one
canonical profile with full provenance and confidence, plus a runtime-configurable
output projection layer and an optional, off-by-default LLM enrichment lane.

The deterministic core (this package, minus :mod:`transformer.enrich`) has zero
LLM dependencies.  See the README for the architecture and the explicit
guarantee: with enrichment off (the default), identical inputs produce
byte-identical output.
"""

from __future__ import annotations

from transformer.models import (
    SOURCE_TRUST,
    CanonicalProfile,
    Education,
    Experience,
    Links,
    Location,
    ProvenanceEntry,
    Skill,
    SourceType,
    trust_for,
)

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "CanonicalProfile",
    "Education",
    "Experience",
    "Links",
    "Location",
    "ProvenanceEntry",
    "Skill",
    "SourceType",
    "SOURCE_TRUST",
    "trust_for",
]
