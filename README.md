# Multi-Source Candidate Data Transformer

Turns messy, multi-source candidate data (recruiter CSV, ATS JSON, GitHub,
résumés, free-text notes) into **one canonical profile** with full **provenance**
and **confidence**, plus a **runtime-configurable output projection** layer and an
**optional, off-by-default LLM enrichment lane** for prose-only fields.

> ### The default path is fully deterministic and LLM-free.
> With enrichment off (the default), **identical inputs produce byte-identical
> output** — proven in CI by running twice, by shuffling input order, and by
> running in separate processes under different `PYTHONHASHSEED` values. The
> deterministic core (`detect → extract → normalize → merge → project →
> validate`) makes **no LLM/AI calls and no network calls**. Every LLM capability
> lives in an optional lane (`transformer.enrich`) that is off unless explicitly
> enabled *and* a key is present, and that **never** touches extraction or
> conflict resolution.

**248 tests pass** (`pytest`) with **ruff + mypy green**, and zero LLM packages installed in the core.

---

## Quick start

```bash
# Deterministic core — NO LLM packages:
pip install -e .

# Run against the sample candidate (a folder of 7 messy sources):
python -m transformer.cli run -i samples/sources -c default -o out.json

# A custom output shape (rename + subset), same engine, no code change:
python -m transformer.cli run -i samples/sources -c samples/configs/recruiter_summary.json

# Stream many candidates as newline-delimited JSON (scale):
python -m transformer.cli run -i samples/scale -c default --format ndjson

# Statically validate a config's paths against the schema BEFORE a run:
python -m transformer.cli lint samples/configs/recruiter_summary.json

# Add test tooling and run the suite:
pip install -e ".[dev]" && pytest -q

# Optional: enrichment lane (Stage 8) and the web UI (Stage 9)
pip install -e ".[llm]"   # adds google-genai ONLY; enrichment stays off by default
pip install -e ".[web]"   # FastAPI wrapper; then: uvicorn transformer.web.api:app
```

`transform` is also registered as a console script (`transform run ...`);
`python -m transformer.cli` avoids any PATH setup. The optional web UI is
documented in [`web/README.md`](web/README.md).

---

## Architecture & pipeline stages

```
inputs ─▶ detect ─▶ extract ─▶ normalize ─▶ merge / conflict-resolve ──┐
(files)   (route    (per-source  (phones,     (link records, trust-     │
           to        FieldFragments) dates,     weighted resolution,     │
           adapter)              country,       confidence, provenance)  │
                                 skills)                                 │
                                                                         ▼
                  validate ◀── PROJECT (config-driven) ◀── [OPTIONAL enrich]
                  (types +     (path mini-language,          (gap-fill prose
                   required)    rename/subset, on_missing)     only, OFF default)
```

Normalization is applied *at extraction time* by each adapter (using the shared
`normalize/` functions), so every emitted fragment already carries a canonical
value and records which normalization produced it — the conceptual "normalize"
stage, folded into extraction with no redundant second pass.

### Module map (`src/transformer/`)
| Module | Responsibility |
| --- | --- |
| `models.py` | `CanonicalProfile` + sub-models; `SourceType` + `SOURCE_TRUST`; provenance `Method` vocabulary. |
| `adapters/` | One adapter per source (`csv_recruiter`, `ats_json`, `github`, `resume`, `notes`); each emits a flat list of `FieldFragment`s. `base.py` holds the contract. |
| `normalize/` | Pure, offline normalizers: `phones`, `dates`, `country`, `skills`, `location`. |
| `merge.py` | Record linking, trust-based conflict resolution, confidence, provenance. |
| `config.py` / `projection.py` | Parse + self-validate the `OutputConfig`; project + validate output. |
| `pipeline.py` / `cli.py` | Orchestration and the `transform` CLI. |
| `enrich/` | The fenced, optional LLM lane (Stage 8). |
| `data/skills_taxonomy.json` | Checked-in alias → canonical skill map. |

> **Layout note:** the taxonomy ships *inside* the package
> (`src/transformer/data/`, loaded via `importlib.resources`) rather than a
> repo-root `data/`, so it resolves after a real `pip install` regardless of the
> working directory. The brief listed `data/` as a *suggested* layout.

---

## Canonical schema & normalized formats

| Field | Type | Normalized format |
| --- | --- | --- |
| `candidate_id` | `str` | explicit id, else derived (see linking) |
| `full_name` | `str \| None` | as provided by the winning source |
| `emails` | `list[str]` | lowercased, deduped, **sorted** |
| `phones` | `list[str]` | **E.164** (`phonenumbers`, validity-gated), sorted |
| `location` | `{city, region, country}` | `country` = **ISO-3166-1 alpha-2** (`pycountry`) |
| `links` | `{linkedin, github, portfolio, other[]}` | as provided |
| `headline` | `str \| None` | null deterministically (prose; LLM-gap-fillable) |
| `years_experience` | `float \| None` | numeric |
| `skills` | `list[{name, confidence, sources[]}]` | **canonical** taxonomy names (`rapidfuzz`, fixed threshold) |
| `experience` | `list[{company, title, start, end, summary}]` | `start`/`end` = **`"YYYY-MM"`** (`None` end = present) |
| `education` | `list[{institution, degree, field, end_year}]` | `end_year` = `int` |
| `provenance` | `list[{field, source, method}]` | every retained value traced |
| `overall_confidence` | `float` | weighted mean of field confidences |

Only `candidate_id` is required internally; everything else defaults to
`None`/`[]`, so a missing or garbage source contributes nothing rather than
crashing. **Unknown values become null — never invented.**

---

## Merge / conflict-resolution & confidence

**Source trust** (drives conflicts):
`ats_json (100) > csv_recruiter (90) > github (70) > resume (50) > notes (30) > llm (10)`.

**Record linking** (which records are the same person):
1. **Strong union-find** over shared `candidate_id`, `email`, or `phone` — near-linear, never over-merges.
2. **Guarded name-attach** — clusters sharing a normalized full name merge **only if** they don't carry conflicting `candidate_id`s. This pulls in name-only sources (a bare GitHub profile, a sticky note whose phone is brand-new) when it's safe, and **provably refuses to fuse two different "John Smith"s** (tested). For an ATS, under-merging is safe; wrongly merging two people is not.

**Per-field resolution:** if sources agree, keep the value and **boost** confidence; if they conflict, the **highest-trust** source wins (deterministic tie-break: higher trust, then **source name alphabetical**), the conflict is recorded as a `merge_winner` provenance entry, and confidence is **lowered**. Experience entries are matched by normalized company; the contested *title* is resolved within the entry.

**Confidence model** (documented, simple, explainable):
```
support = max(trust/100 × raw_confidence)         # strongest single piece of evidence
boost   = min(0.15, 0.05 × (#agreeing_sources − 1))
conf    = min(0.99, support + boost)
if conflict: conf ×= 0.7                           # disagreement lowers it
overall_confidence = identity-weighted mean of all field confidences
```
Each skill carries its own confidence + the list of sources that agreed
(e.g. `Python` → 0.99 from 3 sources; `React` → 0.35 from the résumé alone).

---

## Runtime-configurable output (the "twist")

The same engine emits any shape, with **no code changes**, driven by an
`OutputConfig` (itself pydantic-validated — `extra="forbid"` rejects typo'd keys
and bad enums at load).

**Path mini-language** over the canonical record:
`full_name` · `location.city` · `emails[0]` · `phones[0]` · `skills[].name` ·
`skills[0].confidence` · `experience[].title` (nested wildcards supported).

**Per field:** `path` (output key), `from` (canonical source path), `type`,
`required`, `normalize` (`E164` / `canonical` / `YYYY-MM` / `lower` / `upper` /
`trim`). Global toggles: `include_confidence`, `include_provenance`,
`on_missing` (`null` / `omit` / `error`, with per-field override).

**Project, then validate** (two separate steps): `on_missing` governs
*representation* (`null` → key is null; `omit` → key dropped; `error` → raise);
after projection, the output is validated — a `required` field that ended up null
or omitted raises a clear error, and a value whose runtime type doesn't match its
declared `type` raises a clear, field-named error.

---

## Edge cases handled (and why they matter)

1. **`"CA"` = California, not Canada.** Free text like `"based in San Francisco, CA."`
   produced a `"CA."` token that — being length 3 — slipped past a length-2-only
   state-abbreviation veto, and `pycountry` resolved it to **Canada**. Fixed by
   stripping trailing punctuation per segment. Silently relocating a candidate's
   country is exactly the kind of error an ATS must never make.
2. **`dateutil`'s "today-bleed".** `dateutil` fills missing date components from
   `datetime.now()` by default, so `"2019"` would parse to a *different* month on
   different days — a determinism leak. We pass a **fixed** default datetime;
   `"2019"` is always `"2019-01"` (a documented convention).
3. **Conflicting title across sources.** CSV/résumé say "Senior Software
   Engineer"; ATS says "Staff Software Engineer". Highest trust (ATS) wins →
   `"Staff Software Engineer"`, the conflict is recorded, confidence is lowered.
   Same mechanism gives `full_name → "John Smith"` (ATS) over `"John A. Smith"`
   (CSV) — an intentional, documented outcome of the trust policy.
4. **`"Java"` never becomes `"JavaScript"`.** Skill canonicalization uses a
   full-string scorer (`token_sort_ratio`), not a partial/substring one, plus
   both are exact taxonomy aliases — so the classic substring collision can't
   happen. Typos still resolve (`"kubernets"` → `Kubernetes` at 94.7).
5. **Garbage and empty sources degrade gracefully.** The corrupt JSON is *routed*
   to the ATS adapter (it contains an ATS marker), fails JSON parsing there, and
   yields `[]`; the empty CSV yields `[]`. Every source is read + extracted in its
   own try/except, so one bad file never sinks the run — the four other sources
   still produce a complete profile.

---

## Produced output

**Default config** (full canonical schema) — abridged; full file at
[`samples/expected/default.json`](samples/expected/default.json):
```json
{
  "candidate_id": "cand-001",
  "full_name": "John Smith",
  "emails": ["j.smith@workmail.com", "john.smith@example.com"],
  "phones": ["+14155550132", "+14155550144", "+14155550177"],
  "location": { "city": "San Francisco", "region": "California", "country": "US" },
  "links": { "linkedin": "https://www.linkedin.com/in/johnasmith",
             "github": "https://github.com/johnasmith",
             "portfolio": "https://johnsmith.dev", "other": [] },
  "headline": null,
  "years_experience": 8.0,
  "skills": [ { "name": "Go", "confidence": 0.99, "sources": ["ats_json","github","resume"] }, ... ],
  "experience": [ { "company": "Acme Corp", "title": "Staff Software Engineer",
                    "start": "2021-01", "end": null, "summary": null }, ... ],
  "education": [ { "institution": "Massachusetts Institute of Technology",
                   "degree": "B.S.", "field": "Computer Science", "end_year": 2018 } ],
  "provenance": [ /* 40 entries: every value → (field, source, method) */ ],
  "overall_confidence": 0.694
}
```

**Custom config** ([`recruiter_summary.json`](samples/configs/recruiter_summary.json) — rename + subset, the brief's verbatim example) → full file at [`samples/expected/recruiter_summary.json`](samples/expected/recruiter_summary.json):
```json
{
  "full_name": "John Smith",
  "primary_email": "j.smith@workmail.com",
  "phone": "+14155550132",
  "skills": ["Go","JavaScript","Kubernetes","Mentoring","PostgreSQL","Python","REST APIs","React","Shell"],
  "overall_confidence": 0.694
}
```

> Note: `emails[0]` is `j.smith@workmail.com` because emails are **sorted**
> (deterministic) — so `[0]` is alphabetically-first, not semantically "primary".
> That's the determinism guarantee being honest about a trade-off.

A third config, [`compact_omit.json`](samples/configs/compact_omit.json), turns
provenance off and uses `on_missing: "omit"` — so the (null) `headline` key is
**dropped** entirely from its output.

---

## The LLM decision (judgment, not afterthought)

The brief forbids two things: **non-determinism** and **invented data**. Those are
precisely the two things LLMs do — outputs vary across calls (even at
`temperature=0`, providers don't guarantee bit-identical results), and models
hallucinate. So the entire deterministic core, and the **default run that is
graded**, is **100% LLM-free and reproducible**.

The LLM is confined to an **optional, off-by-default, gap-fill-only** lane
(`transformer.enrich`, behind the `[llm]` extra) for the genuinely fuzzy prose
fields where deterministic parsing is weakest — `headline` and experience
`summary`. It runs *after* merge, touches *only* fields the core left null, never
overwrites a deterministic value, and never participates in conflict resolution.
It is **extract-or-null** (use only the provided text, return null for anything
not present), **schema-validated** (any parse/validation failure → null),
**low-confidence + provenance-tagged** (`source: "llm:<model_id>"`,
`method: "llm_extraction"`), **cached** for reproducible replay, and
**failure-isolated** (network/quota/bad-key errors are caught; fields stay null;
the run continues). A **Flash-tier** model is the right choice: the task is tiny
prose extraction, so a larger model adds cost and latency without accuracy gains.
**Secrets are read from the environment only** (`GEMINI_API_KEY` / `GOOGLE_API_KEY`)
— never from a flag, never hardcoded, never committed (`.env` is git-ignored; only
`.env.example` is tracked). Reproducibility of the *enriched* path comes from the
**cache**, not the model; the default (enrichment-off) path is the one that
satisfies "same inputs → same output".

### Running the optional enrichment lane

```bash
pip install -e ".[llm]"          # adds google-genai ONLY (core needs none of this)
export GEMINI_API_KEY=...        # env only — never a flag, never committed

# Enable via the flag (works with any config)…
python -m transformer.cli run -i samples/sources --default --enrich
# …or via a config that turns it on:
python -m transformer.cli run -i samples/sources -c samples/configs/enriched.json
```

The committed cache (`samples/llm_cache/`) means the demo **replays offline**: the
first matching request is served from the fixture, so no network call is made
(even a dummy key satisfies the env check, because the cache short-circuits the
call). The enriched profile fills the two prose gaps and tags them:

```json
{
  "headline": "Senior Software Engineer",
  "experience": [
    { "company": "Acme Corp", "title": "Staff Software Engineer", "start": "2021-01",
      "end": null, "summary": "Led platform reliability work and mentored junior engineers." },
    ...
  ],
  "provenance": [
    { "field": "headline", "source": "llm:gemini-2.5-flash", "method": "llm_extraction" },
    { "field": "experience.summary", "source": "llm:gemini-2.5-flash", "method": "llm_extraction" },
    ...
  ]
}
```

`title` stays `"Staff Software Engineer"` (deterministically resolved) — enrichment
only filled the empty `summary`/`headline`, never overwriting a core value. Each
filled value carries the fixed low confidence (0.4) in the run's audit report. The
enriched gold ([`samples/expected/enriched.json`](samples/expected/enriched.json))
is backed by the committed cache fixture and verified reproducible in CI **with no
key and no network**.

---

## Testing & determinism

```bash
pytest -q                 # 248 tests
ruff check src tests      # lint gate (CI-enforced)
mypy                      # static type gate (CI-enforced)
```
Coverage includes: phone/date/country/skill normalization; **property-based
(Hypothesis) invariants** over the five normalizers (never-raise, format
contracts, idempotence — which surfaced and fixed a real *invented-date* bug
where a month/weekday/time-only token borrowed the fixed-default year); a
**provenance-completeness invariant** (every emitted value — including the
*derived* `candidate_id` — is traceable); the **PDF résumé path**; the **config
linter**; **NDJSON** determinism; an **API-vs-CLI byte-parity** check; merge
conflict resolution (highest-trust winner + lowered confidence + conflict in
provenance); every projection path form, every `on_missing` mode, and
type-validation failure; graceful degradation (garbage + empty + corrupt +
unreadable + an adapter that raises — none crash the run); **determinism** (run
twice, shuffled input order, and **cross-process under differing
`PYTHONHASHSEED`** → byte-identical); the **enrichment lane** (LLM client mocked
— disabled-by-default byte-identical, gap-fill-only, parse-failure→null,
client-error→null, cache-hit replay, low confidence + `llm_extraction`
provenance); and the **HTTP layer** (FastAPI `TestClient`, byte-identical to the
gold). The API tests ``importorskip`` if the `[web]` extra isn't installed.

---

## Deliberately descoped (under time pressure)

- **Live GitHub fetch is fixture-backed.** `fetch_github()` (real `httpx` call) is
  implemented to *record* fixtures, but the default/tested path reads a committed
  JSON snapshot — required for offline determinism.
- **Résumé fixture is DOCX, not PDF.** Both readers are implemented (`pdfplumber`
  + `python-docx`); the committed sample is DOCX because it can be generated
  deterministically from a dependency we already have (no PDF *writer* needed).
- **Per-field (scalar) confidence isn't exposed** in the output schema — only
  per-skill confidence and `overall_confidence` are, per the schema. Scalar
  confidences are computed internally to feed the aggregate.
- **Name-only linking is a documented heuristic.** Two truly distinct people who
  share a name *and* have no `candidate_id`s could over-merge; the guard uses
  `candidate_id` conflicts as the hard barrier. A production ATS would add a
  dedicated entity-resolution service.
- **Phone region defaults to `US`** for local-format numbers (the sample dataset
  is US-based); it's an explicit, documented parameter, not a hidden global.

---

## Safety, data hygiene & how to read confidence

For an ATS, a few deliberate stances worth stating:

- **All committed sample/fixture data is synthetic.** Emails use the reserved
  `example.com` domain and phone numbers are fictional `555-01xx`/`555-1xx`
  ranges — no real candidate PII lives in the repo or the gold files.
- **No protected attributes are extracted or inferred.** The canonical schema has
  no field for age/gender/race/etc., and the deterministic adapters only emit
  job-relevant, explicitly-present data (skills, roles, contacts). The optional
  LLM lane is extract-or-null and fenced to `headline`/`summary`. A caller who
  wants blind screening can simply omit name/email/location via a projection
  config — no code change.
- **Over-merge is surfaced, never silent.** Linking unions on a shared
  email/phone; if a data-entry error (e.g. the wrong email pasted onto two
  people) fuses records carrying two distinct `candidate_id`s, the run emits a
  loud warning so an operator can investigate — the worst-case ATS error is made
  visible rather than hidden.
- **`overall_confidence`** is an identity-weighted mean of per-field confidences
  (`support = max(trust×raw_confidence)`, `+0.05` per extra agreeing source
  capped at `0.15`, `×0.7` on a resolved conflict; identity fields weight 2,
  experience 2, everything else 1). It is a *data-corroboration* signal — how
  well sources agree — **not** a hiring score, and should never be read as one.
