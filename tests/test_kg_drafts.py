"""Tests for append-only KG Studio draft adjustment records."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from kgtracevis.service.kg_drafts import KGDraftListRequest, KGDraftRequest, list_kg_drafts, record_kg_draft


def test_record_kg_draft_writes_append_only_jsonl(tmp_path: Path) -> None:
    """Draft records persist without mutating KG CSV files."""
    draft_path = tmp_path / "drafts.jsonl"
    request = KGDraftRequest(
        target_id="ScratchDefect|HAS_PLAUSIBLE_CAUSE|MechanicalContact|mvtec",
        target_key="edge:ScratchDefect|HAS_PLAUSIBLE_CAUSE|MechanicalContact|mvtec",
        draft_action="revise",
        proposed_relation="SUGGESTS_PLAUSIBLE_MECHANISM",
        proposed_evidence="Prefer weaker wording for paper demo.",
        proposed_confidence=0.51,
        note="Keep as candidate, not verified RCA.",
    )

    response = record_kg_draft(request, output_path=draft_path)

    assert response["status"] == "recorded"
    rows = [json.loads(line) for line in draft_path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["draft_action"] == "revise"
    assert rows[0]["target_key"] == request.target_key
    assert rows[0]["draft_id"].startswith("kgdraft_")
    assert rows[0]["review_decision"]["action"] == "revise"
    assert rows[0]["review_decision"]["proposed_payload"]["relation"] == (
        "SUGGESTS_PLAUSIBLE_MECHANISM"
    )


def test_kg_draft_rejects_invalid_confidence() -> None:
    """Draft confidence remains a bounded candidate score."""
    with pytest.raises(ValidationError):
        KGDraftRequest(
            target_id="edge-a",
            draft_action="revise",
            proposed_confidence=1.5,
        )


def test_list_kg_drafts_returns_filtered_append_only_history(tmp_path: Path) -> None:
    """Draft history should be queryable without mutating existing records."""
    draft_path = tmp_path / "drafts.jsonl"
    record_kg_draft(
        KGDraftRequest(
            target_id="edge-a",
            target_key="edge:edge-a",
            draft_action="revise",
            reviewer="alice",
            source="kg-studio",
        ),
        output_path=draft_path,
    )
    record_kg_draft(
        KGDraftRequest(
            target_id="edge-b",
            target_key="edge:edge-b",
            draft_action="reject",
            reviewer="bob",
            source="kg-studio",
        ),
        output_path=draft_path,
    )

    response = list_kg_drafts(
        KGDraftListRequest(target_key="edge:edge-a", offset=0, limit=10),
        input_path=draft_path,
    )

    assert response.total_count == 1
    assert response.returned_count == 1
    assert response.records[0].target_key == "edge:edge-a"
    assert response.records[0].reviewer == "alice"
    assert response.claim_boundary.startswith("KG draft records are append-only")
