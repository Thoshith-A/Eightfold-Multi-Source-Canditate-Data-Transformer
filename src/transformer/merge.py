"""Merge engine: link records, resolve conflicts, assign confidence, build provenance.

Input: a flat list of :class:`~transformer.adapters.base.FieldFragment` from every
source.  Output: one :class:`~transformer.models.CanonicalProfile` per distinct
candidate.  Everything here is deterministic — no randomness, every collection
sorted by a stable key before it is emitted.

Three phases:

1. **Group → records.** Fragments sharing ``(source, record_key)`` are one
   *record* (one candidate as seen by one source).

2. **Link records → candidates.**
   * *Strong* union-find over shared ``candidate_id`` / ``email`` / ``phone``.
     Records that share any of these are unambiguously the same person.
   * *Guarded name-attach.* Clusters that share a normalized full name are then
     merged **unless** they carry conflicting ``candidate_id``s (which proves
     they're different people).  This pulls in name-only sources (a bare GitHub
     profile, a sticky note with a new phone number) when it's safe, and refuses
     when it's ambiguous — an ATS must never fuse two different candidates.

3. **Resolve each candidate.** Per field, agreeing sources boost confidence;
   conflicting sources are resolved by **highest trust, then source name
   alphabetical**, the conflict is recorded (``merge_winner`` provenance) and
   confidence is lowered.  Every retained value gets provenance entries
   capturing its source(s) and method(s).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from transformer.adapters.base import FieldFragment
from transformer.models import (
    CanonicalProfile,
    Education,
    Experience,
    Links,
    Location,
    Method,
    ProvenanceEntry,
    Skill,
    SourceType,
    trust_for,
)

logger = logging.getLogger("transformer.merge")

# Known provenance source ids (the SourceType values) — used to flag fragments
# from an unrecognized source, which would silently get trust 0.
_KNOWN_SOURCES = {s.value for s in SourceType}

# --- Confidence model constants (documented; see _field_confidence) ---------
_AGREE_BOOST_PER = 0.05  # +0.05 per *extra* agreeing source
_AGREE_BOOST_CAP = 0.15  # ...capped, so corroboration helps but can't dominate
_CONF_CAP = 0.99         # we never claim absolute certainty
_CONFLICT_PENALTY = 0.7  # multiply confidence when sources disagreed

# Weights for the overall_confidence weighted mean: identity fields matter more
# than a single-source peripheral skill.
_IDENTITY_WEIGHT = 2.0
_EXPERIENCE_WEIGHT = 2.0
_DEFAULT_WEIGHT = 1.0
_IDENTITY_FIELDS = {"candidate_id", "full_name", "emails", "phones"}

_LEGAL_SUFFIXES = {
    "inc", "inc.", "corp", "corp.", "corporation", "llc", "ltd", "ltd.",
    "co", "co.", "gmbh", "plc", "company", "limited",
}


# --------------------------------------------------------------------------- #
# Normalization helpers used only for *matching* (never for display values)
# --------------------------------------------------------------------------- #
def normalize_name(name: str) -> str:
    """Match-key for a name: lowercased, punctuation-free, middle initials dropped.

    ``"John A. Smith"`` and ``"John Smith"`` both map to ``"john smith"`` so the
    two render as the same person during name-attach.
    """

    cleaned = re.sub(r"[.,]", " ", name.lower())
    tokens = [tok for tok in cleaned.split() if len(tok) > 1]
    return " ".join(tokens)


def normalize_company(company: str) -> str:
    """Match-key for a company: lowercased, punctuation/legal-suffix stripped.

    ``"Acme Corp"`` and ``"Acme"`` both map to ``"acme"`` so experience entries
    for the same employer group together.
    """

    cleaned = re.sub(r"[.,]", " ", company.lower())
    tokens = [tok for tok in cleaned.split() if tok not in _LEGAL_SUFFIXES]
    return " ".join(tokens) or cleaned.strip()


# --------------------------------------------------------------------------- #
# Records and linking
# --------------------------------------------------------------------------- #
@dataclass
class _Record:
    """All fragments one source contributed for one candidate, plus its ids."""

    source: str
    record_key: str
    fragments: list[FieldFragment] = field(default_factory=list)
    candidate_ids: set[str] = field(default_factory=set)
    emails: set[str] = field(default_factory=set)
    phones: set[str] = field(default_factory=set)
    names: set[str] = field(default_factory=set)


def _build_records(fragments: list[FieldFragment]) -> list[_Record]:
    """Group fragments by ``(source, record_key)`` and index their identifiers."""

    by_key: dict[tuple[str, str], _Record] = {}
    unknown_sources: set[str] = set()
    for frag in fragments:
        # Flag fragments from an unrecognized source: they'd silently get trust 0
        # (always losing conflicts) yet still join union lists / skills. Surface it.
        if frag.source not in _KNOWN_SOURCES and not frag.source.startswith("llm:"):
            unknown_sources.add(frag.source)
        key = (frag.source, frag.record_key)
        record = by_key.get(key)
        if record is None:
            record = _Record(source=frag.source, record_key=frag.record_key)
            by_key[key] = record
        record.fragments.append(frag)
        if frag.field_path == "candidate_id" and isinstance(frag.value, str):
            record.candidate_ids.add(frag.value)
        elif frag.field_path == "emails" and isinstance(frag.value, str):
            record.emails.add(frag.value)
        elif frag.field_path == "phones" and isinstance(frag.value, str):
            record.phones.add(frag.value)
        elif frag.field_path == "full_name" and isinstance(frag.value, str):
            record.names.add(normalize_name(frag.value))
    if unknown_sources:
        logger.warning(
            "fragments from unrecognized source(s) %s will be treated as trust 0",
            sorted(unknown_sources),
        )
    # Deterministic order: by source then record_key.
    return [by_key[k] for k in sorted(by_key)]


class _DSU:
    """Tiny union-find (disjoint set) over record indices."""

    def __init__(self, n: int) -> None:
        self._parent = list(range(n))

    def find(self, x: int) -> int:
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]
            x = self._parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            # Attach larger root index under smaller for a stable representative.
            lo, hi = sorted((ra, rb))
            self._parent[hi] = lo


def _link_records(records: list[_Record]) -> list[list[_Record]]:
    """Link records into candidate clusters (strong ids, then guarded name-attach)."""

    n = len(records)
    dsu = _DSU(n)

    # --- Phase A: strong identifiers (candidate_id / email / phone). ---------
    # Map each identifier value -> the first record index that owns it, and union
    # subsequent owners with it. O(total identifiers), no O(n^2) scan.
    for attr in ("candidate_ids", "emails", "phones"):
        owner: dict[str, int] = {}
        for idx, rec in enumerate(records):
            for value in getattr(rec, attr):
                if value in owner:
                    dsu.union(owner[value], idx)
                else:
                    owner[value] = idx

    # --- Phase B: guarded name-attach. ---------------------------------------
    # Group current clusters by each normalized name they contain. Within a name
    # group, union all clusters UNLESS they hold >=2 distinct candidate_ids
    # (which proves they're different people -> leave them apart).
    name_to_roots: dict[str, set[int]] = {}
    for idx, rec in enumerate(records):
        root = dsu.find(idx)
        for name in rec.names:
            name_to_roots.setdefault(name, set()).add(root)

    for name in sorted(name_to_roots):
        roots = name_to_roots[name]
        if len(roots) < 2:
            continue
        # Collect candidate_ids across every record in these clusters.
        ids: set[str] = set()
        for idx, rec in enumerate(records):
            if dsu.find(idx) in roots:
                ids |= rec.candidate_ids
        if len(ids) >= 2:
            continue  # ambiguous: conflicting candidate_ids -> do not merge by name
        roots_sorted = sorted(roots)
        for other in roots_sorted[1:]:
            dsu.union(roots_sorted[0], other)

    # Gather clusters, deterministically ordered.
    clusters: dict[int, list[_Record]] = {}
    for idx, rec in enumerate(records):
        clusters.setdefault(dsu.find(idx), []).append(rec)
    ordered = [clusters[root] for root in sorted(clusters)]

    # Safety signal: Phase A unions on a shared email/phone. A data-entry error
    # (e.g. the wrong email pasted onto two people) could fuse TWO DIFFERENT
    # candidates — the worst-case ATS mistake. If a cluster ends up holding more
    # than one distinct explicit candidate_id, that's almost certainly a bad
    # force-join; warn loudly so an operator can investigate. (We do not silently
    # split here — that would risk the opposite error — but we never hide it.)
    for cluster in ordered:
        cluster_ids = sorted({cid for rec in cluster for cid in rec.candidate_ids})
        if len(cluster_ids) > 1:
            logger.warning(
                "possible over-merge: one candidate cluster contains multiple distinct "
                "candidate_ids %s (joined by a shared email/phone — check for a data-entry error)",
                cluster_ids,
            )
    return ordered


# --------------------------------------------------------------------------- #
# Claims + scalar conflict resolution
# --------------------------------------------------------------------------- #
@dataclass
class _Claim:
    """One source's claim about a value (generic over field type)."""

    value: Any
    source: str
    raw_confidence: float
    method: str
    normalize_method: str | None = None


@dataclass
class _Resolution:
    value: Any
    supporters: list[_Claim]  # claims that carried the winning value
    conflict: bool
    winner_source: str


def _resolve(claims: list[_Claim]) -> _Resolution | None:
    """Pick the winning value: highest trust, then source name alphabetical.

    Returns ``None`` if there are no claims.  ``conflict`` is True when more than
    one *distinct* value was offered.
    """

    if not claims:
        return None

    # Distinct values, compared by a stable string key (handles dicts/None too).
    distinct: list[Any] = []
    for claim in claims:
        if claim.value not in distinct:
            distinct.append(claim.value)

    winner_value: Any = None
    winner_trust = -1
    winner_source = ""
    for value in distinct:
        supporters = [c for c in claims if c.value == value]
        top_trust = max(trust_for(c.source) for c in supporters)
        top_source = min(c.source for c in supporters if trust_for(c.source) == top_trust)
        if top_trust > winner_trust or (top_trust == winner_trust and top_source < winner_source):
            winner_trust = top_trust
            winner_value = value
            winner_source = top_source

    supporters = [c for c in claims if c.value == winner_value]
    return _Resolution(
        value=winner_value,
        supporters=supporters,
        conflict=len(distinct) > 1,
        winner_source=winner_source,
    )


def _trust_norm(source: str) -> float:
    """Trust on a 0..1 scale (ATS 1.0, CSV 0.9, GitHub 0.7, résumé 0.5, notes 0.3)."""

    return trust_for(source) / 100.0


def _field_confidence(supporters: list[_Claim], conflict: bool) -> float:
    """Per-field confidence from the supporting claims.

    ``support`` = strongest single piece of evidence (trust x raw_confidence).
    Corroboration from additional distinct sources adds a small, capped boost.
    A resolved conflict multiplies the result down. Result clamped to [0, _CONF_CAP].
    """

    if not supporters:
        return 0.0
    support = max(_trust_norm(c.source) * c.raw_confidence for c in supporters)
    agree = len({c.source for c in supporters})
    boost = min(_AGREE_BOOST_CAP, _AGREE_BOOST_PER * (agree - 1))
    conf = min(_CONF_CAP, support + boost)
    if conflict:
        conf *= _CONFLICT_PENALTY
    return round(max(0.0, min(1.0, conf)), 4)


# --------------------------------------------------------------------------- #
# Provenance + overall-confidence accumulator
# --------------------------------------------------------------------------- #
class _Builder:
    """Accumulates provenance entries and field confidences while merging."""

    def __init__(self) -> None:
        self._prov: set[tuple[str, str, str]] = set()
        self._confidences: list[tuple[float, float]] = []  # (weight, confidence)

    def provenance_for(self, field_path: str, supporters: list[_Claim], conflict: bool) -> None:
        """Record extraction + normalization methods for every supporting source,
        plus a ``merge_winner`` marker when a conflict was resolved."""

        for claim in supporters:
            self._prov.add((field_path, claim.source, claim.method))
            if claim.normalize_method:
                self._prov.add((field_path, claim.source, claim.normalize_method))
        if conflict and supporters:
            winner = min(
                (c for c in supporters if trust_for(c.source) ==
                 max(trust_for(s.source) for s in supporters)),
                key=lambda c: c.source,
            )
            self._prov.add((field_path, winner.source, Method.MERGE_WINNER))

    def add_confidence(self, field_path: str, confidence: float) -> None:
        weight = _IDENTITY_WEIGHT if field_path in _IDENTITY_FIELDS else (
            _EXPERIENCE_WEIGHT if field_path == "experience" else _DEFAULT_WEIGHT
        )
        self._confidences.append((weight, confidence))

    def provenance(self) -> list[ProvenanceEntry]:
        return [
            ProvenanceEntry(field=f, source=s, method=m)
            for (f, s, m) in sorted(self._prov)
        ]

    def overall_confidence(self) -> float:
        if not self._confidences:
            return 0.0
        total_w = sum(w for w, _ in self._confidences)
        weighted = sum(w * c for w, c in self._confidences)
        return round(weighted / total_w, 4) if total_w else 0.0


# --------------------------------------------------------------------------- #
# Field-type mergers
# --------------------------------------------------------------------------- #
def _claims_for(fragments: list[FieldFragment], field_path: str) -> list[_Claim]:
    return [
        _Claim(f.value, f.source, f.raw_confidence, f.method, f.normalize_method)
        for f in fragments
        if f.field_path == field_path
    ]


def _merge_scalar(
    fragments: list[FieldFragment], field_path: str, builder: _Builder
) -> Any:
    """Resolve a single-valued field; record provenance + confidence."""

    resolution = _resolve(_claims_for(fragments, field_path))
    if resolution is None:
        return None
    builder.provenance_for(field_path, resolution.supporters, resolution.conflict)
    builder.add_confidence(field_path, _field_confidence(resolution.supporters, resolution.conflict))
    return resolution.value


def _merge_string_list(
    fragments: list[FieldFragment], field_path: str, builder: _Builder
) -> list[str]:
    """Union a list field (emails/phones): all distinct values, sorted."""

    claims = _claims_for(fragments, field_path)
    if not claims:
        return []
    values = sorted({c.value for c in claims if isinstance(c.value, str)})
    # Provenance: every source that contributed any value (no conflict concept).
    builder.provenance_for(field_path, claims, conflict=False)
    builder.add_confidence(field_path, _field_confidence(claims, conflict=False))
    return values


def _merge_skills(fragments: list[FieldFragment], builder: _Builder) -> list[Skill]:
    """Aggregate canonical skills; confidence reflects #agreeing sources."""

    claims = _claims_for(fragments, "skills")
    by_name: dict[str, list[_Claim]] = {}
    for claim in claims:
        if isinstance(claim.value, str) and claim.value:
            by_name.setdefault(claim.value, []).append(claim)

    skills: list[Skill] = []
    for name in sorted(by_name):
        supporters = by_name[name]
        sources = sorted({c.source for c in supporters})
        confidence = _field_confidence(supporters, conflict=False)
        skills.append(Skill(name=name, confidence=confidence, sources=sources))
        builder.add_confidence("skills", confidence)
        # One provenance entry per contributing source for this skill.
        for source in sources:
            builder._prov.add(("skills", source, Method.SKILL_CANONICALIZE))
    return skills


def _merge_experience(fragments: list[FieldFragment], builder: _Builder) -> list[Experience]:
    """Group experience by normalized company; resolve title/dates by trust."""

    exp_frags = [f for f in fragments if f.field_path == "experience" and isinstance(f.value, dict)]
    groups: dict[str, list[FieldFragment]] = {}
    for frag in exp_frags:
        company = frag.value.get("company") or ""
        groups.setdefault(normalize_company(company) if company else frag.record_key, []).append(frag)

    entries: list[Experience] = []
    for key in sorted(groups):
        group = groups[key]

        def claims_of(subfield: str, group: list[FieldFragment] = group) -> list[_Claim]:
            return [
                _Claim(f.value.get(subfield), f.source, f.raw_confidence, f.method, f.normalize_method)
                for f in group
                if f.value.get(subfield)
            ]

        company_res = _resolve(claims_of("company"))
        title_res = _resolve(claims_of("title"))
        start_res = _resolve(claims_of("start"))
        end_res = _resolve(claims_of("end"))

        title_conflict = bool(title_res and title_res.conflict)
        # Confidence over the whole entry's fragments; lowered if title conflicted.
        entry_supporters = [
            _Claim(None, f.source, f.raw_confidence, f.method, f.normalize_method) for f in group
        ]
        confidence = _field_confidence(entry_supporters, conflict=title_conflict)
        builder.add_confidence("experience", confidence)

        # Provenance: contributing sources at the entry level + a winner marker
        # on the title when it was contested.
        for f in group:
            builder._prov.add(("experience", f.source, f.method))
            if f.normalize_method:
                builder._prov.add(("experience", f.source, f.normalize_method))
        if title_conflict and title_res:
            builder._prov.add(("experience.title", title_res.winner_source, Method.MERGE_WINNER))

        entries.append(
            Experience(
                company=company_res.value if company_res else None,
                title=title_res.value if title_res else None,
                start=start_res.value if start_res else None,
                end=end_res.value if end_res else None,
                summary=None,  # prose; left null deterministically (enrichment may fill)
            )
        )

    # Most recent first (None start sorts last), then company for stability.
    entries.sort(key=lambda e: (e.start or "", e.company or ""), reverse=True)
    return entries


def _merge_education(fragments: list[FieldFragment], builder: _Builder) -> list[Education]:
    """Group education by (normalized institution, end_year); resolve fields by trust."""

    edu_frags = [f for f in fragments if f.field_path == "education" and isinstance(f.value, dict)]
    groups: dict[tuple[str, Any], list[FieldFragment]] = {}
    for frag in edu_frags:
        inst = frag.value.get("institution") or ""
        groups.setdefault((normalize_company(inst), frag.value.get("end_year")), []).append(frag)

    entries: list[Education] = []
    for key in sorted(groups, key=lambda k: (k[0], k[1] or 0)):
        group = groups[key]

        def claims_of(subfield: str, group: list[FieldFragment] = group) -> list[_Claim]:
            return [
                _Claim(f.value.get(subfield), f.source, f.raw_confidence, f.method, f.normalize_method)
                for f in group
                if f.value.get(subfield) is not None
            ]

        inst_res = _resolve(claims_of("institution"))
        degree_res = _resolve(claims_of("degree"))
        field_res = _resolve(claims_of("field"))
        year_res = _resolve(claims_of("end_year"))

        confidence = _field_confidence(
            [_Claim(None, f.source, f.raw_confidence, f.method, f.normalize_method) for f in group],
            conflict=False,
        )
        builder.add_confidence("education", confidence)
        for f in group:
            builder._prov.add(("education", f.source, f.method))

        entries.append(
            Education(
                institution=inst_res.value if inst_res else None,
                degree=degree_res.value if degree_res else None,
                field=field_res.value if field_res else None,
                end_year=year_res.value if year_res else None,
            )
        )

    entries.sort(key=lambda e: (e.end_year or 0, e.institution or ""), reverse=True)
    return entries


# --------------------------------------------------------------------------- #
# Per-candidate assembly + public entry point
# --------------------------------------------------------------------------- #
def _derive_candidate_id(fragments: list[FieldFragment], builder: _Builder) -> str:
    """Resolve candidate_id, or derive a deterministic one from the best identifier."""

    explicit = _merge_scalar(fragments, "candidate_id", builder)
    if isinstance(explicit, str) and explicit:
        return explicit

    # No explicit id: derive one deterministically from the strongest available
    # identifier. Constraint #4: this derived identity must ALSO be traceable, so
    # we record a provenance entry marking it as a merge-layer derivation.
    def _trace_derived() -> None:
        builder._prov.add(("candidate_id", "merge", Method.DERIVED_ID))

    emails = sorted({f.value for f in fragments if f.field_path == "emails" and isinstance(f.value, str)})
    if emails:
        _trace_derived()
        return emails[0]
    names = sorted({f.value for f in fragments if f.field_path == "full_name" and isinstance(f.value, str)})
    if names:
        _trace_derived()
        return normalize_name(names[0]).replace(" ", "_") or names[0]
    keys = sorted({f.record_key for f in fragments if f.record_key})
    if keys:
        _trace_derived()
        return keys[0]
    return "unknown"


def _merge_one(fragments: list[FieldFragment]) -> CanonicalProfile:
    """Merge one candidate's fragments into a CanonicalProfile."""

    builder = _Builder()

    candidate_id = _derive_candidate_id(fragments, builder)
    full_name = _merge_scalar(fragments, "full_name", builder)
    emails = _merge_string_list(fragments, "emails", builder)
    phones = _merge_string_list(fragments, "phones", builder)

    location = Location(
        city=_merge_scalar(fragments, "location.city", builder),
        region=_merge_scalar(fragments, "location.region", builder),
        country=_merge_scalar(fragments, "location.country", builder),
    )
    links = Links(
        linkedin=_merge_scalar(fragments, "links.linkedin", builder),
        github=_merge_scalar(fragments, "links.github", builder),
        portfolio=_merge_scalar(fragments, "links.portfolio", builder),
        other=_merge_string_list(fragments, "links.other", builder),
    )
    headline = _merge_scalar(fragments, "headline", builder)
    years_experience = _merge_scalar(fragments, "years_experience", builder)

    skills = _merge_skills(fragments, builder)
    experience = _merge_experience(fragments, builder)
    education = _merge_education(fragments, builder)

    return CanonicalProfile(
        candidate_id=candidate_id,
        full_name=full_name,
        emails=emails,
        phones=phones,
        location=location,
        links=links,
        headline=headline,
        years_experience=years_experience,
        skills=skills,
        experience=experience,
        education=education,
        provenance=builder.provenance(),
        overall_confidence=builder.overall_confidence(),
    )


def merge(fragments: list[FieldFragment]) -> list[CanonicalProfile]:
    """Merge all fragments into one CanonicalProfile per linked candidate.

    Profiles are returned sorted by ``candidate_id`` for byte-stable output.
    """

    if not fragments:
        return []
    records = _build_records(fragments)
    clusters = _link_records(records)

    profiles: list[CanonicalProfile] = []
    for cluster in clusters:
        cluster_fragments: list[FieldFragment] = []
        for record in cluster:
            cluster_fragments.extend(record.fragments)
        profiles.append(_merge_one(cluster_fragments))

    profiles.sort(key=lambda p: p.candidate_id)
    return profiles
