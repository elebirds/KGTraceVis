"""Append-only KG draft adjustment records for RootLens KG Studio."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from kgtracevis.kg_construction.models import (
    KGConstructionReviewAction,
    KGConstructionReviewDecision,
    review_decision_for_edge,
)

DEFAULT_KG_DRAFT_PATH = Path("runs/kg_studio_drafts/drafts.jsonl")
KGDraftAction = Literal["keep", "revise", "reject", "promote_later"]


class KGDraftRequest(BaseModel):
    """One non-mutating KG edge draft adjustment request."""

    model_config = ConfigDict(extra="forbid")

    target_type: Literal["edge"] = "edge"
    target_id: str
    target_key: str | None = None
    draft_action: KGDraftAction
    proposed_relation: str | None = None
    proposed_evidence: str | None = None
    proposed_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    note: str | None = None
    reviewer: str | None = None
    source: str = "rootlens-kg-studio"
    metadata: dict[str, Any] = Field(default_factory=dict)


class KGDraftRecord(BaseModel):
    """Persisted KG edge draft adjustment record."""

    model_config = ConfigDict(extra="forbid")

    draft_id: str
    created_at: str
    target_type: Literal["edge"]
    target_id: str
    target_key: str
    draft_action: KGDraftAction
    proposed_relation: str | None
    proposed_evidence: str | None
    proposed_confidence: float | None
    note: str | None
    reviewer: str | None
    source: str
    metadata: dict[str, Any]
    review_decision: KGConstructionReviewDecision


def record_kg_draft(
    request: KGDraftRequest,
    *,
    output_path: str | Path = DEFAULT_KG_DRAFT_PATH,
) -> dict[str, object]:
    """Append one KG draft adjustment record and return the persisted payload."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    target_key = request.target_key or f"{request.target_type}:{request.target_id}"
    review_decision = review_decision_for_edge(
        target_id=request.target_id,
        target_key=target_key,
        action=_review_action(request.draft_action),
        reviewer=request.reviewer,
        note=request.note,
        source=request.source,
        proposed_payload=_proposed_payload(request),
        metadata=request.metadata,
    )
    record = KGDraftRecord(
        draft_id=f"kgdraft_{uuid.uuid4().hex[:12]}",
        created_at=datetime.now(timezone.utc).isoformat(),
        target_type=request.target_type,
        target_id=request.target_id,
        target_key=target_key,
        draft_action=request.draft_action,
        proposed_relation=request.proposed_relation,
        proposed_evidence=request.proposed_evidence,
        proposed_confidence=request.proposed_confidence,
        note=request.note,
        reviewer=request.reviewer,
        source=request.source,
        metadata=request.metadata,
        review_decision=review_decision,
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record.model_dump(mode="json"), ensure_ascii=False) + "\n")
    return {"status": "recorded", "record": record.model_dump(mode="json")}


def _review_action(action: KGDraftAction) -> KGConstructionReviewAction:
    actions: dict[KGDraftAction, KGConstructionReviewAction] = {
        "keep": "keep",
        "revise": "revise",
        "reject": "reject",
        "promote_later": "promote_later",
    }
    return actions[action]


def _proposed_payload(request: KGDraftRequest) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if request.proposed_relation is not None:
        payload["relation"] = request.proposed_relation
    if request.proposed_evidence is not None:
        payload["evidence"] = request.proposed_evidence
    if request.proposed_confidence is not None:
        payload["confidence"] = request.proposed_confidence
    return payload
