# mypy: ignore-errors
"""Reusable signal helpers for RCA ranking and anchor profiling."""

# ruff: noqa

from __future__ import annotations

import math


VARIABLE_ROLE_CONTRIBUTION_WEIGHT = {
    "actuator": 0.35,
    "sensor": 1.0,
    "other": 0.75,
}


def contribution_weight(entity_id: str, graph: dict[str, object]) -> float:
    node = graph["nodes"].get(entity_id, {})
    if str(node.get("entity_type", "")) != "Variable":
        return 1.0
    role = str(node.get("variable_role", "")).strip() or "other"
    return VARIABLE_ROLE_CONTRIBUTION_WEIGHT.get(role, VARIABLE_ROLE_CONTRIBUTION_WEIGHT["other"])


def weighted_contributions(
    contributions: dict[str, float],
    graph: dict[str, object],
) -> dict[str, float]:
    return {
        entity_id: round(float(value) * contribution_weight(entity_id, graph), 8)
        for entity_id, value in contributions.items()
    }


def dense_cosine_similarity(left: list[float], right: list[float]) -> float:
    dot_product = sum(left_value * right_value for left_value, right_value in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm <= 0 or right_norm <= 0:
        return 0.0
    return dot_product / (left_norm * right_norm)


def sparse_cosine_similarity(
    left: dict[str, float],
    right: dict[str, float],
) -> float:
    key_space = set(left) | set(right)
    if not key_space:
        return 0.0
    dot_product = sum(float(left.get(key, 0.0)) * float(right.get(key, 0.0)) for key in key_space)
    left_norm = math.sqrt(sum(float(value) * float(value) for value in left.values()))
    right_norm = math.sqrt(sum(float(value) * float(value) for value in right.values()))
    if left_norm <= 0 or right_norm <= 0:
        return 0.0
    return dot_product / (left_norm * right_norm)


def sparse_signature_coverage(
    observed: dict[str, float],
    signature: dict[str, float],
) -> float:
    denominator = sum(abs(float(value)) for value in signature.values())
    if denominator <= 0:
        return 0.0
    matched = 0.0
    for feature_id, signature_value in signature.items():
        observed_value = float(observed.get(feature_id, 0.0))
        signed_signature_value = float(signature_value)
        if observed_value == 0.0 or signed_signature_value == 0.0:
            continue
        if (observed_value > 0.0) != (signed_signature_value > 0.0):
            continue
        matched += min(abs(observed_value), abs(signed_signature_value))
    return matched / denominator
