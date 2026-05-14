"""Root-cause path ranking v0 reproducibility metrics.

These helpers compare deterministic pipeline outputs to curated references or
clean-run outputs. They do not assert paper-grade industrial ground truth.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any


def top_k_root_cause_accuracy(
    gold_targets: Iterable[Any],
    ranked_predictions: Iterable[Sequence[Any]],
    *,
    k: int = 5,
) -> float:
    """Return the share of cases whose gold root cause appears in top-k predictions."""
    if k <= 0:
        raise ValueError("k must be positive")
    gold = [_target_set(value) for value in gold_targets]
    predictions = [list(values)[:k] for values in ranked_predictions]
    if not gold:
        return 0.0
    hits = 0
    for expected, values in zip(gold, predictions, strict=False):
        predicted_ids = {_target_id(value) for value in values}
        if expected and expected & predicted_ids:
            hits += 1
    return hits / len(gold)


def mean_reciprocal_rank(
    gold_targets: Iterable[Any],
    ranked_predictions: Iterable[Sequence[Any]],
) -> float:
    """Return mean reciprocal rank for root-cause predictions."""
    gold = [_target_set(value) for value in gold_targets]
    predictions = [list(values) for values in ranked_predictions]
    if not gold:
        return 0.0
    reciprocal_sum = 0.0
    for expected, values in zip(gold, predictions, strict=False):
        for rank, value in enumerate(values, start=1):
            if _target_id(value) in expected:
                reciprocal_sum += 1 / rank
                break
    return reciprocal_sum / len(gold)


def path_hit_rate(
    gold_paths: Iterable[Any],
    ranked_paths: Iterable[Sequence[Any]],
    *,
    k: int = 5,
) -> float:
    """Return the share of gold path IDs or node paths found in top-k paths."""
    if k <= 0:
        raise ValueError("k must be positive")
    gold = [_path_signature(value) for value in gold_paths]
    predictions = [list(values)[:k] for values in ranked_paths]
    if not gold:
        return 0.0
    hits = 0
    for expected, values in zip(gold, predictions, strict=False):
        predicted = {_path_signature(value) for value in values}
        if expected is not None and expected in predicted:
            hits += 1
    return hits / len(gold)


def _target_set(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        return {value}
    if isinstance(value, dict):
        target = _target_id(value)
        return {target} if target is not None else set()
    if isinstance(value, Iterable):
        return {target for item in value if (target := _target_id(item)) is not None}
    return {str(value)}


def _target_id(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in (
            "candidate_id",
            "root_cause_candidate_id",
            "target_entity_id",
            "entity_id",
            "selected_entity_id",
            "root_cause_id",
        ):
            item = value.get(key)
            if isinstance(item, str):
                return item
    return str(value)


def _path_signature(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        path_id = value.get("path_id")
        if isinstance(path_id, str) and path_id:
            return path_id
        nodes = value.get("nodes")
        relations = value.get("relations")
        if isinstance(nodes, list) and isinstance(relations, list):
            return "|".join(str(item) for item in (*nodes, *relations))
    if isinstance(value, (list, tuple)):
        return "|".join(str(item) for item in value)
    return str(value)
