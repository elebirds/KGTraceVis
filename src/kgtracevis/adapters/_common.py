"""Shared helpers for dataset record adapters."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any, cast

from kgtracevis.schema.evidence_schema import AdapterMetadata, EvidenceObservation, EvidenceSource

VALID_SOURCES = {"image", "time_series", "log", "multimodal", "unknown"}
REASONING_OUTPUT_KEYS = {
    "root_cause",
    "root_causes",
    "candidate_root_cause",
    "candidate_root_causes",
    "ranked_causes",
    "ranked_root_causes",
    "top_k_paths",
    "kg_analysis",
}


def merged_record(record: Mapping[str, Any] | None, overrides: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copied record with keyword overrides applied."""
    data = dict(record or {})
    data.update(overrides)
    return data


def text_value(value: Any, default: str = "unknown") -> str:
    """Return a non-empty text value, or a default for missing values."""
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def optional_text(value: Any) -> str | None:
    """Return stripped text for optional values."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def first_value(data: Mapping[str, Any], keys: Sequence[str], default: Any = None) -> Any:
    """Return the first present, non-None value for a list of aliases."""
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return default


def float_or_none(value: Any) -> float | None:
    """Return a float for numeric input, otherwise None."""
    if value is None or value == "":
        return None
    return float(value)


def text_list(value: Any) -> list[str]:
    """Normalize a scalar or sequence into a list of text values."""
    if value is None:
        return []
    if isinstance(value, str):
        items: Sequence[Any] = value.split(",") if "," in value else [value]
    elif isinstance(value, Sequence) and not isinstance(value, bytes):
        items = value
    else:
        items = [value]
    return [item for item in (optional_text(raw) for raw in items) if item is not None]


def float_dict(value: Any, *, keys: Sequence[str] | None = None) -> dict[str, float]:
    """Normalize a mapping or key-aligned sequence into float values."""
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return {str(key): float(raw_value) for key, raw_value in value.items()}
    if keys is not None and isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return {str(key): float(raw_value) for key, raw_value in zip(keys, value, strict=False)}
    return {}


def source_value(value: Any, default: EvidenceSource) -> EvidenceSource:
    """Return a valid evidence source literal."""
    source = text_value(value, default)
    if source in VALID_SOURCES:
        return cast(EvidenceSource, source)
    return default


def copied_extra(
    data: Mapping[str, Any],
    *,
    known_keys: set[str],
    required: Mapping[str, Any] | None = None,
    forbidden_keys: set[str] | None = None,
) -> dict[str, Any]:
    """Copy unknown record fields plus selected known metadata into raw extra."""
    blocked = REASONING_OUTPUT_KEYS if forbidden_keys is None else forbidden_keys
    extra: dict[str, Any] = {}
    raw_extra = data.get("extra")
    if isinstance(raw_extra, Mapping):
        extra.update(_copy_without_forbidden(raw_extra, blocked))
    for key, value in data.items():
        if key not in known_keys and key != "extra" and key not in blocked:
            extra[key] = _copy_without_forbidden(value, blocked)
    if required:
        for key, value in required.items():
            if value is not None and key not in blocked:
                extra[key] = _copy_without_forbidden(value, blocked)
    return extra


def adapter_metadata(
    name: str,
    *,
    version: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> AdapterMetadata:
    """Return the standard adapter metadata for observed-evidence adapters."""
    return AdapterMetadata(
        name=name,
        version=version,
        produces_root_cause=False,
        metadata=deepcopy(dict(metadata or {})),
    )


def make_observation(
    case_id: str,
    facet: str,
    name: str,
    *,
    display_name: str | None = None,
    value: Any | None = None,
    value_type: str | None = None,
    unit: str | None = None,
    direction: str | None = None,
    confidence: float | None = None,
    source_ref: str | None = None,
    raw_ref: str | None = None,
    time_window: dict[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
    occurrence: int = 1,
) -> EvidenceObservation:
    """Build a stable observation item from adapter output."""
    obs_id = _observation_id(case_id, facet, name, occurrence)
    return EvidenceObservation(
        obs_id=obs_id,
        facet=facet,
        name=name,
        display_name=display_name,
        value=deepcopy(value),
        value_type=value_type,
        unit=unit,
        direction=direction,
        confidence=confidence,
        source_ref=source_ref,
        raw_ref=raw_ref,
        time_window=deepcopy(time_window),
        metadata=deepcopy(dict(metadata or {})),
    )


def next_observation_occurrence(
    occurrences: dict[tuple[str, str], int],
    facet: str,
    name: str,
) -> int:
    """Return the next stable occurrence number for an observation facet/name."""
    key = (facet, name)
    occurrences[key] = occurrences.get(key, 0) + 1
    return occurrences[key]


def _observation_id(case_id: str, facet: str, name: str, occurrence: int) -> str:
    token = _stable_token(name) or "unknown"
    base = f"obs_{_stable_token(case_id) or 'case'}_{_stable_token(facet) or 'facet'}_{token}"
    if occurrence > 1:
        return f"{base}_{occurrence:02d}"
    return base


def _stable_token(value: str) -> str:
    return "_".join("".join(ch.lower() if ch.isalnum() else " " for ch in value).split())


def _copy_without_forbidden(value: Any, forbidden_keys: set[str]) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _copy_without_forbidden(nested, forbidden_keys)
            for key, nested in value.items()
            if str(key) not in forbidden_keys
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_copy_without_forbidden(item, forbidden_keys) for item in value]
    return deepcopy(value)
