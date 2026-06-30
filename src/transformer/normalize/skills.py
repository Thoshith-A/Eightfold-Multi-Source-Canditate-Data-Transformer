"""Skill canonicalization -> canonical taxonomy names.

Two-step, fully deterministic:

1. **Exact alias** — lowercased lookup in the checked-in taxonomy
   (``data/skills_taxonomy.json``).  ``"js"``, ``"reactjs"``, ``"ReactJS"`` all
   land here.  This is also what keeps near-collisions correct: ``"java"`` and
   ``"javascript"`` are *both* exact aliases, so fuzzy matching never gets a
   chance to confuse them.
2. **Fuzzy fallback** — if no exact alias, compare against every alias with
   ``rapidfuzz``'s ``token_sort_ratio`` (a full-string Levenshtein-style scorer,
   chosen over partial/WRatio precisely because partial scorers would match a
   substring like ``"java"`` inside ``"javascript"``).  Accept the best match
   only if it clears a **fixed** threshold (:data:`FUZZY_THRESHOLD`).  Ties break
   deterministically: higher score, then alphabetically-first canonical.
3. **Passthrough** — still no match: keep the original string, flagged as
   non-canonical so the merge layer can assign it lower confidence.  We never
   drop or invent a skill.

Everything here is pure and offline; ``rapidfuzz`` is deterministic C code.
"""

from __future__ import annotations

import functools
import json
import re
from dataclasses import dataclass
from importlib import resources

from rapidfuzz import fuzz

# Fixed (never per-run) acceptance threshold for fuzzy matches, on rapidfuzz's
# 0..100 scale. 90 is high enough that only genuine typos/spelling variants pass
# ("kubernets" -> Kubernetes) while distinct skills stay distinct.
FUZZY_THRESHOLD = 90.0


@dataclass(frozen=True)
class SkillCanon:
    """Result of canonicalizing one raw skill string.

    * ``name``      — canonical name if matched, else the cleaned original.
    * ``canonical`` — whether it resolved to a taxonomy entry.
    * ``method``    — ``"exact_alias"`` | ``"fuzzy_match"`` | ``"passthrough"`` |
                      ``"empty"`` (fine-grained reason; the merge layer records
                      the coarser ``skill_canonicalize`` provenance method).
    * ``score``     — match score 0..100 (100 for exact, best ratio otherwise).
    """

    name: str
    canonical: bool
    method: str
    score: float


@functools.lru_cache(maxsize=1)
def _load_taxonomy() -> tuple[dict[str, str], tuple[str, ...]]:
    """Load and invert the taxonomy, once, cached.

    Returns ``(alias_to_canonical, sorted_alias_keys)``.  The canonical name is
    auto-registered as an alias of itself.  On the (developer-error) case of an
    alias mapping to two canonicals, we keep the alphabetically-first canonical
    deterministically rather than crash — a bad checked-in taxonomy must never
    take down a production run.
    """

    with resources.files("transformer.data").joinpath("skills_taxonomy.json").open(
        "r", encoding="utf-8"
    ) as fh:
        doc = json.load(fh)

    raw: dict[str, list[str]] = doc.get("skills", {})
    alias_to_canonical: dict[str, str] = {}
    for canonical, aliases in raw.items():
        # The canonical name is always a valid alias of itself.
        for alias in [canonical, *aliases]:
            key = alias.strip().lower()
            if not key:
                continue
            existing = alias_to_canonical.get(key)
            if existing is None or canonical < existing:
                alias_to_canonical[key] = canonical

    # Sorted for deterministic iteration during fuzzy matching.
    sorted_keys = tuple(sorted(alias_to_canonical))
    return alias_to_canonical, sorted_keys


def canonicalize_skill(raw: str | None) -> SkillCanon:
    """Canonicalize one raw skill string (see module docstring for the policy)."""

    if raw is None:
        return SkillCanon(name="", canonical=False, method="empty", score=0.0)
    cleaned = raw.strip()
    if not cleaned:
        return SkillCanon(name="", canonical=False, method="empty", score=0.0)

    alias_to_canonical, alias_keys = _load_taxonomy()
    key = cleaned.lower()

    # 1) Exact alias.
    exact = alias_to_canonical.get(key)
    if exact is not None:
        return SkillCanon(name=exact, canonical=True, method="exact_alias", score=100.0)

    # 2) Fuzzy fallback with deterministic tie-break.
    best_alias: str | None = None
    best_score = -1.0
    for alias in alias_keys:  # alias_keys is sorted -> stable iteration
        score = fuzz.token_sort_ratio(key, alias)
        if score > best_score or (
            score == best_score
            and best_alias is not None
            and alias_to_canonical[alias] < alias_to_canonical[best_alias]
        ):
            best_score = score
            best_alias = alias

    if best_alias is not None and best_score >= FUZZY_THRESHOLD:
        return SkillCanon(
            name=alias_to_canonical[best_alias],
            canonical=True,
            method="fuzzy_match",
            score=float(best_score),
        )

    # 3) Passthrough: keep the original, flagged non-canonical (lower confidence).
    return SkillCanon(
        name=cleaned,
        canonical=False,
        method="passthrough",
        score=float(max(best_score, 0.0)),
    )


# Minimum alias length considered when scanning *free text*. Short aliases
# ("go", "js", "c#") are too collision-prone to safely match inside prose, so
# they're only honored in structured contexts (skills columns / sections), never
# scanned out of sentences.
_MIN_SCAN_LEN = 3


def scan_skills_in_text(text: str | None) -> list[SkillCanon]:
    """Find canonical skills *explicitly mentioned* in free text (notes/prose).

    Conservative by design — it only matches taxonomy aliases that are at least
    :data:`_MIN_SCAN_LEN` chars and made of word characters/spaces, using word
    boundaries, so it never fabricates a skill from an incidental substring
    ("Go" the verb, "C" the article-ish token).  Results are de-duplicated by
    canonical name and returned sorted, for determinism.
    """

    if not text:
        return []

    alias_to_canonical, alias_keys = _load_taxonomy()
    lowered = text.lower()

    found: dict[str, SkillCanon] = {}
    for alias in alias_keys:
        if len(alias) < _MIN_SCAN_LEN:
            continue
        # Only word-char/space aliases are safe for boundary matching; aliases
        # like "c++"/"node.js" carry punctuation and are skipped here.
        if not all(ch.isalnum() or ch.isspace() for ch in alias):
            continue
        if re.search(rf"\b{re.escape(alias)}\b", lowered):
            canonical = alias_to_canonical[alias]
            # Keep one entry per canonical (first by sorted alias order).
            found.setdefault(
                canonical,
                SkillCanon(name=canonical, canonical=True, method="text_scan", score=100.0),
            )

    return [found[name] for name in sorted(found)]
