"""Schemas for human-in-the-loop feedback."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

FeedbackType = Literal["correction", "path", "entity_linking", "kg_edge"]
FeedbackDecision = Literal["accept", "reject", "edit", "skip"]


class HumanFeedback(BaseModel):
    """Stable feedback record that can be attached to UI actions later."""

    feedback_id: str
    feedback_type: FeedbackType
    case_id: str | None = None
    target_id: str | None = None
    decision: FeedbackDecision
    user_comment: str = ""
    reviewer_role: str | None = None
    timestamp: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
