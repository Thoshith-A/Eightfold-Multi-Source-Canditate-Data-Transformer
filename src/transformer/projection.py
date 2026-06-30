"""Projection engine: map a CanonicalProfile onto a config-defined output shape.

Two responsibilities, kept separate (mirroring "PROJECT ... then VALIDATE"):

* :func:`project` — resolve each field's source path through the *path
  mini-language*, optionally re-normalize, and apply the ``on_missing`` policy,
  producing the output dict.
* :func:`validate_output` — check the produced object against the config's
  declared types and ``required`` flags.

:func:`project_and_validate` runs both.

**Path mini-language** over the canonical record (a plain dict from
``model_dump()``):

* ``"full_name"``            — a top-level scalar
* ``"location.city"``        — a nested scalar
* ``"emails[0]"``            — an element of a list
* ``"skills[].name"``        — map over a list, pull a subfield -> a list
* ``"skills[]"`` / ``"skills"`` — the whole list

Anything that can't be resolved (absent key, out-of-range index) yields the
:data:`MISSING` sentinel, distinct from a legitimately-``None`` value; both are
treated as "missing" by the ``on_missing`` policy.
"""

from __future__ import annotations

import re
import types
import typing
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from transformer.config import FieldType, Normalize, OnMissing, OutputConfig
from transformer.models import CanonicalProfile
from transformer.normalize.dates import normalize_year_month
from transformer.normalize.phones import normalize_phone
from transformer.normalize.skills import canonicalize_skill


class ProjectionError(Exception):
    """Raised when projection cannot proceed (e.g. on_missing='error', bad path)."""


class ProjectionValidationError(ProjectionError):
    """Raised when the projected output violates declared types or required flags."""


class _Missing:
    """Sentinel for 'path did not resolve' — distinct from a real ``None`` value."""

    _instance: _Missing | None = None

    def __new__(cls) -> _Missing:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return "MISSING"


MISSING = _Missing()

# One dotted segment: a key, optionally followed by [N] (index) or [] (wildcard).
_SEGMENT_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(?:\[(\d+|)\])?$")


# --------------------------------------------------------------------------- #
# Path resolution
# --------------------------------------------------------------------------- #
def resolve_path(data: Any, path: str) -> Any:
    """Resolve a mini-language ``path`` against ``data``; return value or MISSING."""

    if not path:
        raise ProjectionError("empty path")
    return _resolve(data, path.split("."), 0)


def _resolve(current: Any, segments: list[str], index: int) -> Any:
    if index >= len(segments):
        return current

    match = _SEGMENT_RE.match(segments[index])
    if not match:
        raise ProjectionError(f"invalid path segment: {segments[index]!r}")
    key, bracket = match.group(1), match.group(2)

    if not isinstance(current, dict) or key not in current:
        return MISSING
    value = current[key]

    if bracket is None:
        # Plain key.
        return _resolve(value, segments, index + 1)

    if not isinstance(value, list):
        return MISSING

    if bracket == "":
        # Wildcard: apply the rest of the path to each element, collect present ones.
        results: list[Any] = []
        for item in value:
            resolved = _resolve(item, segments, index + 1)
            if resolved is not MISSING:
                results.append(resolved)
        return results

    # Indexed access [N].
    idx = int(bracket)
    if idx >= len(value):
        return MISSING
    return _resolve(value[idx], segments, index + 1)


# --------------------------------------------------------------------------- #
# Normalization (re-applied at projection time)
# --------------------------------------------------------------------------- #
def _normalize_scalar(value: Any, norm: Normalize) -> Any:
    text = str(value)
    if norm is Normalize.E164:
        return normalize_phone(text)
    if norm is Normalize.CANONICAL:
        return canonicalize_skill(text).name or None
    if norm is Normalize.YYYY_MM:
        return normalize_year_month(text)
    if norm is Normalize.LOWER:
        return text.lower()
    if norm is Normalize.UPPER:
        return text.upper()
    if norm is Normalize.TRIM:
        return text.strip()
    return value  # pragma: no cover - exhaustive above


def apply_normalize(value: Any, norm: Normalize | None) -> Any:
    """Apply a normalization to a scalar or (element-wise) to a list."""

    if norm is None or value is MISSING or value is None:
        return value
    if isinstance(value, list):
        # Normalize each element; drop ones that fail to normalize (e.g. an
        # invalid phone), since a null inside a typed list is noise.
        out = []
        for item in value:
            result = _normalize_scalar(item, norm)
            if result is not None:
                out.append(result)
        return out
    return _normalize_scalar(value, norm)


# --------------------------------------------------------------------------- #
# Type checking
# --------------------------------------------------------------------------- #
def _matches_type(value: Any, ftype: FieldType) -> bool:
    if ftype is FieldType.ANY:
        return True
    if ftype is FieldType.STRING:
        return isinstance(value, str)
    if ftype is FieldType.STRING_ARRAY:
        return isinstance(value, list) and all(isinstance(x, str) for x in value)
    if ftype is FieldType.NUMBER:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if ftype is FieldType.INTEGER:
        return isinstance(value, int) and not isinstance(value, bool)
    if ftype is FieldType.BOOLEAN:
        return isinstance(value, bool)
    if ftype is FieldType.OBJECT:
        return isinstance(value, dict)
    if ftype is FieldType.OBJECT_ARRAY:
        return isinstance(value, list) and all(isinstance(x, dict) for x in value)
    return False  # pragma: no cover


# --------------------------------------------------------------------------- #
# Project + validate
# --------------------------------------------------------------------------- #
def project(profile: CanonicalProfile, config: OutputConfig) -> dict[str, Any]:
    """Project a profile onto the config's output shape (no validation yet).

    Raises :class:`ProjectionError` immediately for a field whose effective
    ``on_missing`` is ``error`` and whose value is missing.
    """

    data = profile.model_dump()
    out: dict[str, Any] = {}

    for spec in config.fields:
        raw = resolve_path(data, spec.source_path)
        value = apply_normalize(raw, spec.normalize)

        if value is MISSING or value is None:
            effective = spec.on_missing or config.on_missing
            if effective is OnMissing.ERROR:
                raise ProjectionError(
                    f"field {spec.path!r} (from {spec.source_path!r}) is missing "
                    f"and on_missing='error'"
                )
            if effective is OnMissing.OMIT:
                continue  # drop the key entirely
            out[spec.path] = None  # OnMissing.NULL
        else:
            out[spec.path] = value

    # Reserved keys, added only when toggled on (after user fields).
    if config.include_confidence:
        out["overall_confidence"] = data.get("overall_confidence")
    if config.include_provenance:
        out["provenance"] = data.get("provenance")

    return out


def validate_output(output: dict[str, Any], config: OutputConfig) -> None:
    """Validate a projected object against declared ``required`` flags and types.

    Raises :class:`ProjectionValidationError` with a clear, field-named message.
    """

    for spec in config.fields:
        present = spec.path in output and output[spec.path] is not None
        if spec.required and not present:
            raise ProjectionValidationError(
                f"required field {spec.path!r} is missing or null"
            )
        if present and not _matches_type(output[spec.path], spec.type):
            actual = type(output[spec.path]).__name__
            raise ProjectionValidationError(
                f"field {spec.path!r} expected type {spec.type.value!r} "
                f"but got {actual}: {output[spec.path]!r}"
            )


def project_and_validate(profile: CanonicalProfile, config: OutputConfig) -> dict[str, Any]:
    """Project then validate; return the validated output object."""

    output = project(profile, config)
    validate_output(output, config)
    return output


# --------------------------------------------------------------------------- #
# Static config linting (transform lint) — catch bad source paths BEFORE a run
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class LintIssue:
    """One problem found by :func:`lint_config`."""

    severity: str  # "error" (unresolvable path) | "warning" (type mismatch)
    path: str  # the output key (FieldSpec.path)
    source_path: str
    message: str


def _unwrap_optional(annotation: Any) -> Any:
    """Strip ``X | None`` / ``Optional[X]`` down to ``X``."""

    origin = typing.get_origin(annotation)
    if origin is typing.Union or origin is types.UnionType:
        non_none = [a for a in typing.get_args(annotation) if a is not type(None)]
        if len(non_none) == 1:
            return non_none[0]
    return annotation


def _is_list(annotation: Any) -> bool:
    return typing.get_origin(annotation) is list


def _list_item(annotation: Any) -> Any:
    args = typing.get_args(annotation)
    return args[0] if args else Any


def _is_model(annotation: Any) -> bool:
    return isinstance(annotation, type) and issubclass(annotation, BaseModel)


def _scalar_kind(annotation: Any) -> str:
    # bool must be checked before int (bool subclasses int).
    if annotation is str:
        return "string"
    if annotation is bool:
        return "boolean"
    if annotation is int:
        return "integer"
    if annotation is float:
        return "number"
    return "unknown"


def _resolve_kind(source_path: str) -> tuple[str | None, str | None]:
    """Walk a path against the CanonicalProfile model tree.

    Returns ``(result_kind, None)`` on success — where ``result_kind`` is one of
    ``string|integer|number|boolean|object|string[]|object[]|unknown`` — or
    ``(None, error_message)`` if the path can't resolve against the schema.
    """

    segments = source_path.split(".")
    current: Any = CanonicalProfile
    used_wildcard = False

    for segment in segments:
        match = _SEGMENT_RE.match(segment)
        if not match:
            return None, f"invalid path segment {segment!r}"
        key, bracket = match.group(1), match.group(2)

        if not _is_model(current):
            return None, f"cannot access field {key!r}: the preceding segment is not an object"
        fields = current.model_fields
        if key not in fields:
            return None, f"unknown field {key!r} on {current.__name__}"

        annotation = _unwrap_optional(fields[key].annotation)
        if bracket is None:
            current = annotation
        else:
            if not _is_list(annotation):
                return None, f"field {key!r} is not a list; '[]' / '[index]' is invalid here"
            current = _unwrap_optional(_list_item(annotation))
            if bracket == "":
                used_wildcard = True

    if used_wildcard:
        element, is_list_result = current, True
    elif _is_list(current):
        element, is_list_result = _unwrap_optional(_list_item(current)), True
    else:
        element, is_list_result = current, False

    elem_kind = "object" if _is_model(element) else _scalar_kind(element)
    if is_list_result:
        return ("object[]" if elem_kind == "object" else f"{elem_kind}[]"), None
    return elem_kind, None


def _type_compatible(declared: FieldType, resolved_kind: str) -> bool:
    if declared is FieldType.ANY or resolved_kind == "unknown" or resolved_kind.startswith("unknown"):
        return True
    if declared.value == resolved_kind:
        return True
    # An int leaf satisfies a declared NUMBER (int is a number).
    return declared is FieldType.NUMBER and resolved_kind == "integer"


def lint_config(config: OutputConfig) -> list[LintIssue]:
    """Statically check every field's ``source_path`` against the canonical schema.

    Catches the silent footgun where a mistyped path (``location.citi``,
    ``experience[].titel``) resolves to MISSING and is quietly nulled/omitted —
    which, for an ATS, means silently dropping a field that feeds a hiring
    decision. Also flags declared-type mismatches (e.g. calling the ``phones``
    list a ``string``). Read-only; never touches the transform path. Issues are
    returned sorted for byte-stable output.
    """

    issues: list[LintIssue] = []
    for spec in config.fields:
        resolved_kind, error = _resolve_kind(spec.source_path)
        if error is not None:
            issues.append(LintIssue("error", spec.path, spec.source_path, error))
            continue
        assert resolved_kind is not None
        if not _type_compatible(spec.type, resolved_kind):
            issues.append(LintIssue(
                "warning", spec.path, spec.source_path,
                f"declared type {spec.type.value!r} but path resolves to {resolved_kind!r}",
            ))
    return sorted(issues, key=lambda i: (i.severity, i.path, i.source_path, i.message))
