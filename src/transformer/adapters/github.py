"""GitHub adapter (UNSTRUCTURED-ish public profile).

GitHub's public API gives us a self-reported but real signal: display name,
company, location string, portfolio link, and — most usefully — the languages
across a user's repos, which map cleanly onto canonical skills.

**Determinism + offline:** the graded/default path reads a *recorded fixture*
(a committed JSON snapshot of the API responses), so tests and demos never touch
the network and are byte-stable.  :func:`fetch_github` shows the real
``httpx``-based call used to *produce* such a fixture; it is never invoked on the
default path.

We deliberately do **not** map the GitHub ``bio`` to ``headline``: ``headline``
is a prose-synthesis field we leave null in the deterministic run (it's exactly
the kind of fuzzy field the optional enrichment lane exists to fill).
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from transformer.adapters.base import FieldFragment, RawSource, clean_email
from transformer.models import Method, SourceType
from transformer.normalize.location import parse_location_string
from transformer.normalize.skills import canonicalize_skill

_GITHUB_API = "https://api.github.com"


class GithubAdapter:
    """Adapter for a recorded GitHub profile fixture (``{user, repos, languages}``)."""

    source_type: ClassVar[SourceType] = SourceType.GITHUB

    def detect(self, raw: RawSource) -> bool:
        if raw.path.suffix.lower() != ".json":
            return False
        text = raw.text or ""
        # Distinctive shape of our fixture; mutually exclusive with the ATS markers.
        return '"user"' in text and '"repos"' in text

    def extract(self, raw: RawSource) -> list[FieldFragment]:
        if not raw.text:
            return []
        try:
            doc = json.loads(raw.text)
        except (json.JSONDecodeError, ValueError):
            return []
        if not isinstance(doc, dict):
            return []

        # Narrow with typed locals (so the types are provable, not just safe).
        raw_user, raw_repos, raw_langs = doc.get("user"), doc.get("repos"), doc.get("languages")
        user: dict[str, Any] = raw_user if isinstance(raw_user, dict) else {}
        repos: list[Any] = raw_repos if isinstance(raw_repos, list) else []
        languages: dict[str, Any] = raw_langs if isinstance(raw_langs, dict) else {}

        login = user.get("login") if isinstance(user.get("login"), str) else None
        record_key = login or raw.path.stem

        fragments: list[FieldFragment] = []

        def add(field_path: str, value: object, conf: float, normalize: str | None = None) -> None:
            fragments.append(
                FieldFragment(
                    field_path=field_path,
                    value=value,
                    source=self.source_type.value,
                    method=Method.GITHUB_API,
                    raw_confidence=conf,
                    record_key=record_key,
                    normalize_method=normalize,
                )
            )

        name = user.get("name")
        if isinstance(name, str) and name.strip():
            add("full_name", name.strip(), 0.8)

        email = clean_email(user.get("email") if isinstance(user.get("email"), str) else None)
        if email:
            add("emails", email, 0.8)

        html_url = user.get("html_url")
        if isinstance(html_url, str) and html_url.strip():
            add("links.github", html_url.strip(), 0.95)

        blog = user.get("blog")
        if isinstance(blog, str) and blog.strip():
            add("links.portfolio", blog.strip(), 0.7)

        # Location string -> city / region / country.
        loc = parse_location_string(user.get("location") if isinstance(user.get("location"), str) else None)
        if loc.city:
            add("location.city", loc.city, 0.7)
        if loc.region:
            add("location.region", loc.region, 0.7)
        if loc.country:
            add("location.country", loc.country, 0.75, normalize=Method.COUNTRY_NORMALIZE)

        # Company -> a light experience entry (reinforces the role's company;
        # GitHub often prefixes it with "@").
        company = user.get("company")
        if isinstance(company, str) and company.strip():
            add(
                "experience",
                {
                    "company": company.strip().lstrip("@"),
                    "title": None,
                    "start": None,
                    "end": None,
                    "summary": None,
                },
                0.5,
            )

        # Skills from languages: union of the aggregated language map and any
        # per-repo language, canonicalized and de-duplicated (sorted for stability).
        lang_names: set[str] = set()
        for key in languages:
            if isinstance(key, str):
                lang_names.add(key)
        for repo in repos:
            if isinstance(repo, dict) and isinstance(repo.get("language"), str):
                lang_names.add(repo["language"])
        for lang in sorted(lang_names):
            canon = canonicalize_skill(lang)
            if canon.name:
                add(
                    "skills",
                    canon.name,
                    0.75 if canon.canonical else 0.5,
                    normalize=Method.SKILL_CANONICALIZE,
                )

        return fragments


def fetch_github(username: str, token: str | None = None) -> dict[str, Any]:  # pragma: no cover
    """Build a fixture-shaped dict from the live GitHub API (used to *record*
    fixtures; never called on the default deterministic path).

    Optional ``token`` raises the unauthenticated rate limit but is not required.
    Imports ``httpx`` lazily so importing this module has no network-stack cost.
    """

    import httpx

    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    with httpx.Client(base_url=_GITHUB_API, headers=headers, timeout=10.0) as client:
        user = client.get(f"/users/{username}").raise_for_status().json()
        repos = client.get(f"/users/{username}/repos", params={"per_page": 100}).raise_for_status().json()
        languages: dict[str, int] = {}
        for repo in repos:
            lang = repo.get("language")
            if lang:
                languages[lang] = languages.get(lang, 0) + 1

    return {"user": user, "repos": repos, "languages": languages}
