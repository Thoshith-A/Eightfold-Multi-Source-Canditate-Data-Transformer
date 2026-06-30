"""Build the per-candidate prose context the enricher extracts from.

The enricher must extract `headline`/`summary` from the candidate's *own* source
text (extract-or-null).  This module gathers that prose:

* it attributes each source to a profile by **identifier overlap** (shared
  email / candidate_id / phone / normalized name) — so in a multi-candidate run
  a résumé only feeds the person it actually belongs to;
* it recovers prose per source type (résumé DOCX/PDF text, notes text, the
  GitHub bio) — structured sources (CSV/ATS) contribute no prose.

Pure, offline, deterministic (sources are processed in their sorted order).
"""

from __future__ import annotations

import json

from transformer.adapters.base import FieldFragment, RawSource
from transformer.adapters.resume import read_text as read_resume_text
from transformer.merge import normalize_name
from transformer.models import CanonicalProfile


def _profile_identifiers(profile: CanonicalProfile) -> set[str]:
    ids: set[str] = set(profile.emails) | set(profile.phones)
    if profile.candidate_id:
        ids.add(profile.candidate_id)
    if profile.full_name:
        ids.add(normalize_name(profile.full_name))
    return ids


def _source_identifiers(fragments: list[FieldFragment]) -> set[str]:
    ids: set[str] = set()
    for frag in fragments:
        if not isinstance(frag.value, str):
            continue
        if frag.field_path in {"emails", "phones", "candidate_id"}:
            ids.add(frag.value)
        elif frag.field_path == "full_name":
            ids.add(normalize_name(frag.value))
    return ids


def _prose_text(raw: RawSource) -> str:
    """Recover plain prose from a source (empty for structured CSV/ATS)."""

    suffix = raw.path.suffix.lower()
    if suffix in {".txt", ".text", ".md"}:
        return raw.text or ""
    if suffix in {".pdf", ".docx", ".doc"}:
        return read_resume_text(raw)
    if suffix == ".json":
        # Only the GitHub fixture carries prose (the bio); ATS JSON is structured.
        try:
            doc = json.loads(raw.text or "")
        except (json.JSONDecodeError, ValueError):
            return ""
        if isinstance(doc, dict) and isinstance(doc.get("user"), dict):
            bio = doc["user"].get("bio")
            return bio if isinstance(bio, str) else ""
    return ""


def build_context(
    profile: CanonicalProfile, extractions: list[tuple[RawSource, list[FieldFragment]]]
) -> str:
    """Concatenate the prose of every source that belongs to ``profile``."""

    wanted = _profile_identifiers(profile)
    parts: list[str] = []
    for raw, fragments in extractions:
        if not (wanted & _source_identifiers(fragments)):
            continue  # this source belongs to a different candidate
        text = _prose_text(raw)
        if text and text.strip():
            label = fragments[0].source if fragments else raw.path.suffix.lstrip(".")
            parts.append(f"[source: {label}]\n{text.strip()}")
    return "\n\n".join(parts)


__all__ = ["build_context"]
