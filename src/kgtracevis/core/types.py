"""Common type aliases for KGTraceVis."""

from __future__ import annotations

from typing import Literal

Scenario = Literal["mvtec", "tep", "wafer", "shared"]
ReviewStatus = Literal["auto", "reviewed", "rejected"]
FeedbackDecision = Literal["accept", "reject", "edit", "skip"]
