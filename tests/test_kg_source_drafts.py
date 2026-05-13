"""Tests for source-to-KG candidate draft generation."""

from __future__ import annotations

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

