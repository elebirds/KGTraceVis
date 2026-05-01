"""Entity linking v0 reproducibility metrics."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any


def entity_linking_accuracy(
    gold_entity_ids: Iterable[Any],
    predicted_entity_ids: Iterable[Any],
) -> float:
    """Return top-1 entity linking accuracy."""
    gold = [_entity_id(value) for value in gold_entity_ids]
    predicted = [_entity_id(value) for value in predicted_entity_ids]
    if not gold:
        return 0.0
    correct = sum(
        1
        for expected, actual in zip(gold, predicted, strict=False)
        if expected is not None and expected == actual
    )
    return correct / len(gold)


def top_k_linking_accuracy(
    gold_entity_ids: Iterable[Any],
    predicted_candidates: Iterable[Sequence[Any]],
    *,
    k: int = 5,
) -> float:
    """Return the share of gold entity IDs found in each top-k candidate list."""
    if k <= 0:
        raise ValueError("k must be positive")
    gold = [_entity_id(value) for value in gold_entity_ids]
    candidates = [list(values)[:k] for values in predicted_candidates]
    if not gold:
        return 0.0
    hits = 0
    for expected, values in zip(gold, candidates, strict=False):
        candidate_ids = {_entity_id(value) for value in values}
        if expected is not None and expected in candidate_ids:
            hits += 1
    return hits / len(gold)


def _entity_id(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("entity_id", "selected_entity_id", "suggested_entity_id", "target_entity_id"):
            item = value.get(key)
            if isinstance(item, str):
                return item
    return str(value)
