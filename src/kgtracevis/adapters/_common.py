"""Shared helpers for dataset record adapters."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any, cast

from kgtracevis.schema.evidence_schema import EvidenceSource

VALID_SOURCES = {"image", "time_series", "log", "multimodal", "unknown"}


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
) -> dict[str, Any]:
    """Copy unknown record fields plus selected known metadata into raw extra."""
    extra: dict[str, Any] = {}
    raw_extra = data.get("extra")
    if isinstance(raw_extra, Mapping):
        extra.update(deepcopy(dict(raw_extra)))
    for key, value in data.items():
        if key not in known_keys and key != "extra":
            extra[key] = deepcopy(value)
    if required:
        for key, value in required.items():
            if value is not None:
                extra[key] = deepcopy(value)
    return extra
