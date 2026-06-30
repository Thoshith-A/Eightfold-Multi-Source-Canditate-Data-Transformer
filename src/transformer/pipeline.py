"""Pipeline orchestration: detect → extract → merge → [enrich] → project → validate.

This wires the deterministic core together.  The whole core is LLM-free; the
optional enrichment lane (Stage 8) is injected as an ``enricher`` object and is
``None`` on the default path, so with enrichment off the behavior here is
exactly stages 1–5 composed — byte-identical to the pre-enrichment build.

Robustness (constraint #2): every source is read and extracted inside its own
try/except.  A file that can't be read, isn't recognized, or whose adapter
raises is logged and skipped — the run continues with the remaining sources.

Scale (constraint #3): files are processed iteratively; fragments (small dicts)
accumulate, and linking is near-linear union-find — no O(n²) over candidates.
For very large corpora you would shard by candidate folder and call :func:`run`
per shard; the engine itself is unchanged.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from transformer.adapters import detect_adapter
from transformer.adapters.base import FieldFragment, RawSource
from transformer.config import OutputConfig
from transformer.merge import merge
from transformer.models import CanonicalProfile
from transformer.projection import project_and_validate

logger = logging.getLogger("transformer.pipeline")

# What an adapter produced for one source file: the raw source + its fragments.
# The enrichment lane needs both — fragments to attribute a source to a candidate,
# and the RawSource to recover that source's prose text.
SourceExtraction = tuple[RawSource, list[FieldFragment]]


@runtime_checkable
class Enricher(Protocol):
    """Seam for the optional enrichment lane (implemented in Stage 8).

    The core never imports the enrichment package; an object satisfying this
    protocol is *injected* into :func:`run`.  When ``None`` (the default), the
    pipeline is fully deterministic and LLM-free.
    """

    def enrich_profiles(
        self, profiles: list[CanonicalProfile], extractions: list[SourceExtraction]
    ) -> list[CanonicalProfile]:
        ...


def iter_input_files(inputs: list[str | Path]) -> list[Path]:
    """Expand inputs (files and/or directories) into a sorted, de-duplicated file list.

    Directories are walked recursively.  Sorting by path string makes the
    extraction order deterministic regardless of filesystem enumeration order.
    """

    files: list[Path] = []
    for item in inputs:
        path = Path(item)
        if path.is_dir():
            files.extend(p for p in path.rglob("*") if p.is_file())
        elif path.is_file():
            files.append(path)
        else:
            logger.warning("input path does not exist, skipping: %s", path)

    seen: set[Path] = set()
    unique: list[Path] = []
    for f in files:
        resolved = f.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(f)
    unique.sort(key=str)
    return unique


def collect_extractions(files: list[Path]) -> list[SourceExtraction]:
    """Read + extract every file in isolation; never let one bad source crash the run.

    Returns one ``(RawSource, fragments)`` per readable file (fragments may be
    empty for an undetected/garbage/empty source — that's the graceful path).
    """

    extractions: list[SourceExtraction] = []
    for path in files:
        try:
            raw = RawSource.load(path)
        except Exception as exc:  # unreadable file / permission error / etc.
            logger.warning("could not read %s: %s", path, exc)
            continue

        adapter = detect_adapter(raw)
        if adapter is None:
            logger.warning("no adapter detected for %s; skipping", path)
            extractions.append((raw, []))
            continue
        try:
            fragments = adapter.extract(raw)
        except Exception as exc:  # adapter blew up on malformed content
            logger.warning(
                "adapter '%s' failed on %s: %s; skipping",
                adapter.source_type.value, path, exc,
            )
            extractions.append((raw, []))
            continue
        logger.info("%s -> %d fragments (%s)", path.name, len(fragments), adapter.source_type.value)
        extractions.append((raw, fragments))

    return extractions


def _flatten(extractions: list[SourceExtraction]) -> list[FieldFragment]:
    return [frag for _raw, frags in extractions for frag in frags]


def build_profiles(inputs: list[str | Path]) -> list[CanonicalProfile]:
    """Deterministic core: inputs -> merged canonical profiles (no projection, no LLM)."""

    extractions = collect_extractions(iter_input_files(inputs))
    return merge(_flatten(extractions))


def run(
    inputs: list[str | Path],
    config: OutputConfig,
    *,
    enricher: Enricher | None = None,
) -> list[dict[str, Any]]:
    """Full pipeline: build profiles, optionally enrich, then project + validate each.

    Returns one projected, schema-valid output dict per candidate (sorted by
    candidate_id via the merge stage).  ``enricher`` is injected only when the
    optional lane is enabled; with ``None`` the result is fully deterministic.
    """

    extractions = collect_extractions(iter_input_files(inputs))
    profiles = merge(_flatten(extractions))

    if enricher is not None:
        # Optional, off-by-default lane; gap-fill only (see transformer.enrich).
        profiles = enricher.enrich_profiles(profiles, extractions)

    return [project_and_validate(profile, config) for profile in profiles]


def render_json(outputs: list[dict[str, Any]]) -> str:
    """Serialize pipeline output deterministically.

    Emits a single object when there is exactly one candidate (the common case:
    one person across several sources) and a JSON array when there are several.
    ``ensure_ascii=False`` keeps names/locations human-readable; a trailing
    newline makes the files diff-friendly.
    """

    payload: Any = outputs[0] if len(outputs) == 1 else outputs
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def render_ndjson(outputs: list[dict[str, Any]]) -> str:
    """Serialize as newline-delimited JSON: one compact object per candidate.

    The standard shape for streaming/ingesting many candidates at scale — each
    line is independently parseable and diff-able. Keys are sorted so each line
    is byte-stable; line *k* parses equal to element *k* of :func:`render_json`'s
    array form. Candidates are already in candidate_id order from merge.
    """

    return "".join(
        json.dumps(item, sort_keys=True, ensure_ascii=False) + "\n" for item in outputs
    )
