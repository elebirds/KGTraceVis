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
    reviewer: str | None = None
    source: str = "kgtracevis"
    metadata: dict[str, Any] = Field(default_factory=dict)


class KGDraftRecord(BaseModel):
    """Persisted KG draft feedback record."""

    model_config = ConfigDict(extra="forbid")

    draft_id: str
    recorded_at: str
    target_type: str
    target_id: str
    target_key: str | None = None
    draft_action: KGDraftAction
    proposed_relation: str | None = None
    proposed_evidence: str | None = None
    proposed_confidence: float | None = None
    note: str | None = None
    reviewer: str | None = None
    source: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    review_decision: dict[str, Any] = Field(default_factory=dict)


class KGDraftListRequest(BaseModel):
    """Read-side filters for append-only KG draft records."""

    model_config = ConfigDict(extra="forbid")

    target_type: Literal["edge", "kg_edge"] | None = None
    target_id: str | None = None
    target_key: str | None = None
    reviewer: str | None = None
    source: str | None = None
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=500)


class KGDraftListResponse(BaseModel):
    """Paginated list response for KG draft history."""

    model_config = ConfigDict(extra="forbid")

    records: list[KGDraftRecord] = Field(default_factory=list)
    total_count: int
    returned_count: int
    offset: int
    limit: int
    claim_boundary: str = (
        "draft feedback is advisory and does not mutate generated KG artifacts"
    )


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


def list_kg_drafts(
    request: KGDraftListRequest | None = None,
    *,
    input_path: Path | None = None,
) -> KGDraftListResponse:
    """Return append-only KG draft feedback records."""
    active_request = request or KGDraftListRequest()
    path = input_path or DEFAULT_KG_DRAFT_PATH
    records = [
        KGDraftRecord.model_validate(record)
        for record in _read_jsonl_records(path)
        if _draft_matches(record, active_request)
    ]
    total_count = len(records)
    page = records[active_request.offset : active_request.offset + active_request.limit]
    return KGDraftListResponse(
        records=page,
        total_count=total_count,
        returned_count=len(page),
        offset=active_request.offset,
        limit=active_request.limit,
    )


def _draft_matches(record: dict[str, Any], request: KGDraftListRequest) -> bool:
    return (
        (request.target_type is None or record.get("target_type") == request.target_type)
        and (request.target_id is None or record.get("target_id") == request.target_id)
        and (request.target_key is None or record.get("target_key") == request.target_key)
        and (request.reviewer is None or record.get("reviewer") == request.reviewer)
        and (request.source is None or record.get("source") == request.source)
    )


def _read_jsonl_records(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"JSONL record must be an object: {path}")
        records.append(dict(payload))
    records.sort(key=lambda item: str(item.get("recorded_at") or ""), reverse=True)
    return records
