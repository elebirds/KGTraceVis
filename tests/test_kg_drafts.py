"""Tests for append-only KG Studio draft adjustment records."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from kgtracevis.service.kg_drafts import KGDraftRequest, record_kg_draft


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


def test_kg_draft_rejects_invalid_confidence() -> None:
    """Draft confidence remains a bounded candidate score."""
    with pytest.raises(ValidationError):
        KGDraftRequest(
            target_id="edge-a",
            draft_action="revise",
            proposed_confidence=1.5,
        )

