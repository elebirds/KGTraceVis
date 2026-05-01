"""Confidence assignment utilities for KG candidates."""

from __future__ import annotations

SOURCE_TYPE_CONFIDENCE = {
    "dataset_label": 0.9,
    "official_table": 0.9,
    "caption_mask_stats": 0.85,
    "manual_curation": 0.8,
    "manual": 0.8,
    "project_note": 0.78,
    "prior_project": 0.78,
    "thesis_text": 0.75,
    "wafer_thesis": 0.75,
    "example_seed": 0.7,
    "llm_extraction": 0.55,
    "common_industrial_heuristic": 0.45,
    "industrial_heuristic": 0.45,
}
DEFAULT_CONFIDENCE = 0.6


def assign_confidence(
    source_type: str | None,
    *,
    explicit_confidence: float | None = None,
) -> float:
    """Return deterministic confidence for a source type.

    Explicit confidence values are validated and preserved. Otherwise the
    source type is mapped to a conservative v0 confidence level.
    """
    if explicit_confidence is not None:
        return _validate_confidence(explicit_confidence)
    normalized = _normalize_source_type(source_type)
    return SOURCE_TYPE_CONFIDENCE.get(normalized, DEFAULT_CONFIDENCE)


def edge_weight(confidence: float) -> float:
    """Return the default KG edge weight for a confidence value."""
    return round(1.0 - _validate_confidence(confidence), 6)


def _normalize_source_type(source_type: str | None) -> str:
    if not source_type:
        return ""
    return "_".join(source_type.strip().lower().replace("-", "_").split())


def _validate_confidence(confidence: float) -> float:
    value = float(confidence)
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"confidence must be in [0, 1]: {confidence}")
    return value
