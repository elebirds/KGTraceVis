"""Schema and inconsistency detection v0 reproducibility metrics."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pydantic import ValidationError

from kgtracevis.schema.evidence_schema import Evidence


def schema_validity_rate(records: Iterable[Any]) -> float:
    """Return the share of records that validate as unified evidence."""
    items = list(records)
    if not items:
        return 0.0
    valid = 0
    for item in items:
        try:
            if isinstance(item, Evidence):
                valid += 1
            elif isinstance(item, str):
                Evidence.model_validate_json(item)
                valid += 1
            else:
                Evidence.model_validate(item)
                valid += 1
        except (TypeError, ValueError, ValidationError):
            continue
    return valid / len(items)


def inconsistency_detection_precision_recall(
    expected_fields: Iterable[Iterable[str]],
    predicted_fields: Iterable[Iterable[str]],
) -> dict[str, float | int]:
    """Return field-level precision, recall, and F1 for v0 detection checks."""
    expected = [_normalize_fields(fields) for fields in expected_fields]
    predicted = [_normalize_fields(fields) for fields in predicted_fields]

    true_positive = 0
    false_positive = 0
    false_negative = 0
    case_count = max(len(expected), len(predicted))
    for index in range(case_count):
        expected_set = expected[index] if index < len(expected) else set()
        predicted_set = predicted[index] if index < len(predicted) else set()
        true_positive += len(expected_set & predicted_set)
        false_positive += len(predicted_set - expected_set)
        false_negative += len(expected_set - predicted_set)

    precision = _safe_divide(true_positive, true_positive + false_positive)
    recall = _safe_divide(true_positive, true_positive + false_negative)
    f1 = _safe_divide(2 * precision * recall, precision + recall)
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": true_positive,
        "fp": false_positive,
        "fn": false_negative,
    }


def _normalize_fields(fields: Iterable[str]) -> set[str]:
    return {_normalize_field(field) for field in fields}


def _normalize_field(field: str) -> str:
    if field.startswith("raw_evidence."):
        field = field.removeprefix("raw_evidence.")
    if field == "variables":
        return "variable"
    if field == "log_events":
        return "log_event"
    if field == "variable_contributions":
        return "variable"
    return field


def _safe_divide(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator
