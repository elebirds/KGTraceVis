"""Tests for RCA-KG construction review queue prioritization."""

from __future__ import annotations

from kgtracevis.kg.graph import KGEdge
from kgtracevis.kg_construction.review_queue import build_review_queue


def test_review_queue_prioritizes_rca_score_and_derived_edge_provenance() -> None:
    """High-impact and derived propagation edges should be surfaced first."""
    derived = _edge(
        "PumpA",
        "OBSERVED_BY",
        "PressureSignal",
        source="semantic_projection:component_observation_bridge",
        propagation_enabled=True,
        rca_score=0.76,
        confidence=0.7,
    )
    high_score = _edge(
        "SealWear",
        "AFFECTS",
        "PressureSignal",
        source="manual",
        propagation_enabled=True,
        rca_score=0.9,
        confidence=0.95,
    )
    support = _edge(
        "PumpA",
        "PART_OF",
        "ProcessUnit",
        source="manual",
        propagation_enabled=False,
        rca_score=0.95,
        confidence=0.95,
    )

    queue = build_review_queue((support, high_score, derived))

    assert [item.target_key for item in queue] == [
        "PumpA|OBSERVED_BY|PressureSignal|shared",
        "SealWear|AFFECTS|PressureSignal|shared",
    ]
    assert queue[0].priority == 92
    assert queue[0].reason == "derived propagation edge needs provenance review"
    assert "rca_score=0.76" in queue[0].graph_impact
    assert queue[0].recommended_action == "inspect_source_edges_then_accept_or_reject"
    assert queue[1].priority == 90
    assert queue[1].reason == "high-impact propagation edge affects RCA ranking"
    assert queue[1].recommended_action == "verify_direction_and_score_then_accept_or_reject"


def _edge(
    head: str,
    relation: str,
    tail: str,
    *,
    source: str,
    propagation_enabled: bool,
    rca_score: float,
    confidence: float,
) -> KGEdge:
    return KGEdge(
        head=head,
        relation=relation,
        tail=tail,
        scenario="shared",
        source=source,
        evidence=f"{head} {relation} {tail}",
        confidence=confidence,
        weight=1.0 - confidence,
        review_status="auto",
        feedback_count=0,
        accepted_count=0,
        rejected_count=0,
        relation_family="OBSERVATION" if relation == "OBSERVED_BY" else "AFFECTS",
        propagation_enabled=propagation_enabled,
        rca_score=rca_score,
    )
