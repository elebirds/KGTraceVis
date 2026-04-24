"""Lightweight confidence update helpers for reviewed KG evidence."""

from __future__ import annotations


def update_confidence(confidence: float, decision: str) -> float:
    """Apply a small deterministic confidence update from human feedback."""
    if decision == "accept":
        return min(1.0, confidence + 0.03)
    if decision == "reject":
        return max(0.0, confidence - 0.05)
    return confidence
