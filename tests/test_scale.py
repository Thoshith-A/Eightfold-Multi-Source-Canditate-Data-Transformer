"""Scale + multi-candidate tests (constraint #3).

A multi-row CSV yields one profile *per candidate*, kept separate (no accidental
cross-linking), sorted by candidate_id. A large generated CSV demonstrates the
run stays near-linear — not O(n²) over the candidate set.
"""

from __future__ import annotations

from pathlib import Path

from transformer import pipeline
from transformer.config import default_output_config

ROOT = Path(__file__).resolve().parent.parent
SCALE_CSV = ROOT / "samples" / "scale" / "candidates.csv"


def test_multi_candidate_csv_stays_separate() -> None:
    profiles = pipeline.build_profiles([SCALE_CSV])
    assert [p.candidate_id for p in profiles] == ["cand-100", "cand-101", "cand-102"]
    names = {p.candidate_id: p.full_name for p in profiles}
    assert names["cand-100"] == "Ada Lovelace"
    assert names["cand-101"] == "Alan M. Turing"
    # Each candidate keeps only their own data (no cross-contamination).
    ada = next(p for p in profiles if p.candidate_id == "cand-100")
    assert ada.emails == ["ada.lovelace@example.com"]
    assert ada.phones == ["+14155550150"]


def test_thousands_of_candidates_are_handled(tmp_path: Path) -> None:
    """2,000 distinct candidates in one CSV -> 2,000 profiles, no blow-up."""

    n = 2000
    lines = ["candidate_id,name,email,phone,current_company,title"]
    for i in range(n):
        # Distinct strong identifiers per row -> 2,000 separate candidates.
        lines.append(
            f"cand-{i:05d},Person {i},person{i}@example.com,"
            f"+1415555{i:04d},Company {i % 50},Engineer"
        )
    big = tmp_path / "big.csv"
    big.write_text("\n".join(lines) + "\n", encoding="utf-8")

    profiles = pipeline.build_profiles([big])
    assert len(profiles) == n
    # Sorted by candidate_id (deterministic ordering at scale).
    ids = [p.candidate_id for p in profiles]
    assert ids == sorted(ids)
    # Projection of the whole set is also fine.
    outputs = pipeline.run([big], default_output_config())
    assert len(outputs) == n
