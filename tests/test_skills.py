"""Unit tests for skill canonicalization (alias map + fixed-threshold fuzzy)."""

from __future__ import annotations

import pytest

from transformer.normalize.skills import FUZZY_THRESHOLD, canonicalize_skill


@pytest.mark.parametrize(
    "raw,expected",
    [
        # The exact cases called out in the brief.
        ("js", "JavaScript"),
        ("reactjs", "React"),
        ("ReactJS", "React"),
        # Casing / punctuation variants.
        ("JavaScript", "JavaScript"),
        ("react.js", "React"),
        ("NODE.JS", "Node.js"),
        ("k8s", "Kubernetes"),
        ("c++", "C++"),
        ("C#", "C#"),
        ("postgres", "PostgreSQL"),
    ],
)
def test_exact_alias_canonicalization(raw: str, expected: str) -> None:
    result = canonicalize_skill(raw)
    assert result.name == expected
    assert result.canonical is True
    assert result.method == "exact_alias"
    assert result.score == 100.0


def test_java_and_javascript_do_not_collide() -> None:
    # The classic trap: a substring scorer would fold "Java" into "JavaScript".
    assert canonicalize_skill("java").name == "Java"
    assert canonicalize_skill("Java").name == "Java"
    assert canonicalize_skill("javascript").name == "JavaScript"


@pytest.mark.parametrize(
    "typo,expected",
    [
        ("kubernets", "Kubernetes"),
        ("pythonn", "Python"),
        ("postgresql ", "PostgreSQL"),  # trailing space, still exact after strip
    ],
)
def test_fuzzy_matches_typos(typo: str, expected: str) -> None:
    result = canonicalize_skill(typo)
    assert result.name == expected
    assert result.canonical is True
    assert result.method in {"exact_alias", "fuzzy_match"}
    assert result.score >= FUZZY_THRESHOLD


def test_unknown_skill_passthrough() -> None:
    result = canonicalize_skill("Quantum Basket Weaving")
    assert result.name == "Quantum Basket Weaving"  # preserved, not invented away
    assert result.canonical is False
    assert result.method == "passthrough"


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_empty_skill(raw: str | None) -> None:
    result = canonicalize_skill(raw)
    assert result.canonical is False
    assert result.method == "empty"


def test_determinism() -> None:
    a = canonicalize_skill("reactjs")
    b = canonicalize_skill("reactjs")
    assert a == b
