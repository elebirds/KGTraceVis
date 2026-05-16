"""Lightweight KG draft feedback capture."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_KG_DRAFT_PATH = Path("runs/kg_drafts.jsonl")
KGDraftAction = Literal["keep", "revise", "reject", "promote_later"]


class KGDraftRequest(BaseModel):
    """One operator note about a KG edge or generated candidate."""

    model_config = ConfigDict(extra="forbid")

    target_type: str = "kg_edge"
    target_id: str
    target_key: str | None = None
    draft_action: KGDraftAction
    proposed_relation: str | None = None
    proposed_evidence: str | None = None
    proposed_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    note: str | None = None
    source: str = "kgtracevis"
    metadata: dict[str, Any] = Field(default_factory=dict)


def record_kg_draft(
    request: KGDraftRequest,
    *,
    output_path: Path | None = None,
) -> dict[str, object]:
    """Append a draft feedback record."""
    path = output_path or DEFAULT_KG_DRAFT_PATH
    proposed_payload = {
        "relation": request.proposed_relation,
        "evidence": request.proposed_evidence,
        "confidence": request.proposed_confidence,
    }
    review_decision = {
        "action": request.draft_action,
        "target_type": request.target_type,
        "target_id": request.target_id,
        "target_key": request.target_key,
        "note": request.note,
        "proposed_payload": proposed_payload,
    }
    payload = {
        "draft_id": f"kgdraft_{uuid.uuid4().hex}",
        "recorded_at": datetime.now(UTC).isoformat(),
        **request.model_dump(mode="json"),
        "review_decision": review_decision,
        "claim_boundary": (
            "draft feedback is advisory and does not mutate generated KG artifacts"
        ),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
    return {"status": "recorded", "record": payload}
