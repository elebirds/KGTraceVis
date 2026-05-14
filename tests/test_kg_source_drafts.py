"""Tests for source-to-KG candidate draft generation."""

from __future__ import annotations

from fastapi.testclient import TestClient

from kgtracevis.service.api import app
from kgtracevis.service.kg_source_drafts import (
    KGSourceDraftRequest,
    generate_source_kg_draft,
)


def test_generate_source_kg_draft_from_structured_lines() -> None:
    """Structured source rows become reviewable candidate KG edges."""
    response = generate_source_kg_draft(
        KGSourceDraftRequest(
            source_id="unit_source",
            source_text=(
                "# comment\n"
                "ScratchDefect,SUGGESTS_PLAUSIBLE_MECHANISM,MechanicalContact,mvtec,"
                "Scratch source wording\n"
            ),
        )
    )

    assert response.provider == "heuristic"
    assert len(response.candidate_edges) == 1
    edge = response.candidate_edges[0]
    assert edge.edge_id == "ScratchDefect|SUGGESTS_PLAUSIBLE_MECHANISM|MechanicalContact|mvtec"
    assert edge.source == "unit_source"
    assert edge.evidence == "Scratch source wording"
    assert edge.review_status == "auto"
    assert edge.weight == 0.45


def test_generate_source_kg_draft_uses_default_scenario() -> None:
    """Three-column lines use the request-level default scenario."""
    response = generate_source_kg_draft(
        KGSourceDraftRequest(
            source_text="LocPattern,HAS_LOCATION,LocalLocation",
            default_scenario="wafer",
        )
    )

    assert response.candidate_edges[0].scenario == "wafer"


def test_source_kg_draft_api_preserves_candidate_edge_contract() -> None:
    """The API endpoint keeps the existing source-draft response shape."""
    client = TestClient(app)

    response = client.post(
        "/api/kg/source-draft",
        json={
            "source_id": "unit_source",
            "source_text": "ScratchDefect,SUGGESTS_PLAUSIBLE_MECHANISM,MechanicalContact",
            "default_scenario": "mvtec",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "heuristic"
    assert payload["candidate_edges"][0] == {
        "edge_id": "ScratchDefect|SUGGESTS_PLAUSIBLE_MECHANISM|MechanicalContact|mvtec",
        "head": "ScratchDefect",
        "relation": "SUGGESTS_PLAUSIBLE_MECHANISM",
        "tail": "MechanicalContact",
        "scenario": "mvtec",
        "source": "unit_source",
        "evidence": "ScratchDefect,SUGGESTS_PLAUSIBLE_MECHANISM,MechanicalContact",
        "confidence": 0.55,
        "weight": 0.45,
        "review_status": "auto",
        "feedback_count": 0,
        "accepted_count": 0,
        "rejected_count": 0,
    }
