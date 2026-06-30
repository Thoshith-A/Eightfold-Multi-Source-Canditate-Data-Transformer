"""Per-source adapters.

Each adapter implements the :class:`~transformer.adapters.base.Adapter` protocol
(``detect`` + ``extract``) and turns one kind of input into a flat list of
:class:`~transformer.adapters.base.FieldFragment` objects.

:data:`ALL_ADAPTERS` is the detection order the pipeline walks; :func:`detect_adapter`
returns the first adapter that claims an input (or ``None`` -> the pipeline logs
it as an undetectable source and skips it, never crashing).
"""

from __future__ import annotations

from transformer.adapters.ats_json import AtsJsonAdapter
from transformer.adapters.base import Adapter, FieldFragment, RawSource
from transformer.adapters.csv_recruiter import CsvRecruiterAdapter
from transformer.adapters.github import GithubAdapter
from transformer.adapters.notes import NotesAdapter
from transformer.adapters.resume import ResumeAdapter

# Order matters only where detection could overlap; each detect() is specific
# enough that ordering is mostly cosmetic. CSV first (cheap extension check),
# then the two JSON shapes (distinguished by content markers), then binary
# résumés, then the catch-all-ish text notes.
ALL_ADAPTERS: list[Adapter] = [
    CsvRecruiterAdapter(),
    AtsJsonAdapter(),
    GithubAdapter(),
    ResumeAdapter(),
    NotesAdapter(),
]


def detect_adapter(raw: RawSource) -> Adapter | None:
    """Return the first adapter whose ``detect`` claims ``raw``, else ``None``.

    ``detect`` implementations are required not to raise, but we guard anyway so
    a misbehaving adapter can never break source routing.
    """

    for adapter in ALL_ADAPTERS:
        try:
            if adapter.detect(raw):
                return adapter
        except Exception:
            continue
    return None


__all__ = [
    "Adapter",
    "FieldFragment",
    "RawSource",
    "AtsJsonAdapter",
    "CsvRecruiterAdapter",
    "GithubAdapter",
    "NotesAdapter",
    "ResumeAdapter",
    "ALL_ADAPTERS",
    "detect_adapter",
]
