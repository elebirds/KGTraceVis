"""Correction and noise recovery v0 reproducibility metrics."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any


def correction_accuracy(gold_values: Iterable[Any], predicted_values: Iterable[Any]) -> float:
    """Return top-1 correction accuracy."""
    gold = [_normal_value(value) for value in gold_values]
    predicted = [_normal_value(value) for value in predicted_values]
    if not gold:
        return 0.0
    hits = sum(
        1
        for expected, actual in zip(gold, predicted, strict=False)
        if expected is not None and expected == actual
    )
    return hits / len(gold)


def top_k_correction_accuracy(
    gold_values: Iterable[Any],
    predicted_candidates: Iterable[Sequence[Any]],
    *,
    k: int = 5,
) -> float:
    """Return the share of gold corrections found in each top-k candidate list."""
    if k <= 0:
        raise ValueError("k must be positive")
    gold = [_normal_value(value) for value in gold_values]
    candidates = [list(values)[:k] for values in predicted_candidates]
    if not gold:
        return 0.0
    hits = 0
    for expected, values in zip(gold, candidates, strict=False):
        candidate_values = {_normal_value(value) for value in values}
        if expected is not None and expected in candidate_values:
            hits += 1
    return hits / len(gold)


def noise_recovery_rate(clean_values: Iterable[Any], recovered_values: Iterable[Any]) -> float:
    """Return the share of corrupted values recovered to their clean value."""
    return correction_accuracy(clean_values, recovered_values)


def _normal_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        for key in (
            "suggested_entity_id",
            "suggested_value",
            "suggested",
            "selected_entity_id",
            "entity_id",
            "value",
        ):
            item = value.get(key)
            if item is not None:
                return _normal_value(item)
        return None
    if isinstance(value, (list, tuple, set)):
        return "|".join(sorted(_normal_value(item) or "" for item in value))
    return " ".join(str(value).lower().replace("_", " ").split())
