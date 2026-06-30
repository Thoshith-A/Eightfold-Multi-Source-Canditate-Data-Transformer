"""Deterministic normalizers.

Pure functions that turn raw extracted values into canonical formats:
phones -> E.164, dates -> "YYYY-MM", country -> ISO-3166 alpha-2, skills ->
canonical taxonomy names.  No LLM, no network (except none here), no randomness.
Implemented in Stage 2.
"""
