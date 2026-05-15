"""Tests for review-controlled KG construction publish snapshots."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from kgtracevis.kg.graph import KGEdge, KGNode
from kgtracevis.kg_construction.models import review_decision_for_edge
from kgtracevis.kg_construction.publish import (
    append_review_decision,
    build_publish_snapshot,
    load_review_decisions,
    write_publish_snapshot,
)


def test_publish_snapshot_keeps_offline_document_causal_edge_pending_until_accept(
    tmp_path: Path,
) -> None:
    """High-risk document causal edges should publish only after review acceptance."""
    edge = _edge(
        source="toy_generic_document",
        relation="SUGGESTS_ROOT_CAUSE",
        relation_family="CAUSES",
        propagation_enabled=True,
        confidence=0.5,
    )

    pending = build_publish_snapshot(
        kg_build_id="kgbuild_publish_policy",
        nodes=_nodes(),
        edges=(edge,),
    )

    assert pending.edges == ()
    assert pending.report_payload()["disposition_counts"] == {"pending_review": 1}
    assert pending.report_items[0].reason == (
        "high-risk causal/propagation/document edge requires review"
    )

    decision_path = tmp_path / "review_decisions.jsonl"
    decision = review_decision_for_edge(
        target_id=edge.edge_id,
        target_key=edge.edge_id,
        action="accept",
        reviewer="unit-test",
        note="source-grounded fixture accepted",
    )
    append_review_decision(decision_path, decision)

    accepted = build_publish_snapshot(
        kg_build_id="kgbuild_publish_policy",
        nodes=_nodes(),
        edges=(edge,),
        review_decisions=load_review_decisions(decision_path),
    )

    assert len(accepted.edges) == 1
    assert accepted.edges[0].review_status == "reviewed"
    assert accepted.edges[0].accepted_count == 1
    assert accepted.edges[0].kg_build_id == "kgbuild_publish_policy"
    assert accepted.report_payload()["disposition_counts"] == {"accepted": 1}


def test_publish_snapshot_excludes_rejected_and_allows_low_risk_edges() -> None:
    """Publish policy should distinguish rejected, accepted, and low-risk edges."""
    rejected_edge = _edge(
        head="ReviewedEvent",
        relation="AFFECTS",
        tail="PublishedSignal",
        source="structured_unit",
        relation_family="AFFECTS",
        confidence=0.91,
    )
    low_risk_edge = _edge(
        head="PublishedPump",
        relation="OBSERVED_BY",
        tail="PublishedSignal",
        source="structured_unit",
        relation_family="OBSERVATION",
        confidence=0.88,
    )
    reject_decision = review_decision_for_edge(
        target_id=rejected_edge.edge_id,
        target_key=rejected_edge.edge_id,
        action="reject",
    )

    snapshot = build_publish_snapshot(
        kg_build_id="kgbuild_publish_mixed",
        nodes=_nodes(),
        edges=(rejected_edge, low_risk_edge),
        review_decisions=(reject_decision,),
    )

    assert [edge.edge_id for edge in snapshot.edges] == [low_risk_edge.edge_id]
    assert snapshot.report_payload()["disposition_counts"] == {
        "policy_allowed": 1,
        "rejected": 1,
    }


def test_write_publish_snapshot_exports_csv_and_report(tmp_path: Path) -> None:
    """Publish snapshots should write reproducible runtime CSVs and JSON report."""
    edge = _edge(
        source="structured_unit",
        relation="OBSERVED_BY",
        relation_family="OBSERVATION",
        confidence=0.91,
    )
    snapshot = build_publish_snapshot(
        kg_build_id="kgbuild_publish_files",
        nodes=_nodes(),
        edges=(edge,),
    )

    nodes_path, edges_path, report_path = write_publish_snapshot(
        snapshot,
        nodes_path=tmp_path / "published_nodes.csv",
        edges_path=tmp_path / "published_edges.csv",
        report_path=tmp_path / "publish_report.json",
    )

    edge_rows = _read_csv_rows(edges_path)
    report = json.loads(report_path.read_text())
    assert nodes_path.is_file()
    assert edge_rows[0]["kg_build_id"] == "kgbuild_publish_files"
    assert edge_rows[0]["review_status"] == "auto"
    assert report["artifact_type"] == "kg_publish_report_v1"
    assert report["disposition_counts"] == {"policy_allowed": 1}


def _nodes() -> tuple[KGNode, ...]:
    return (
        KGNode(
            id="ReviewedEvent",
            name="Reviewed event",
            label="Event",
            scenario="shared",
            aliases=(),
        ),
        KGNode(
            id="ReviewedCause",
            name="Reviewed cause",
            label="RootCause",
            scenario="shared",
            aliases=(),
        ),
        KGNode(
            id="PublishedPump",
            name="Published pump",
            label="Equipment",
            scenario="shared",
            aliases=(),
        ),
        KGNode(
            id="PublishedSignal",
            name="Published signal",
            label="Variable",
            scenario="shared",
            aliases=(),
        ),
    )


def _edge(
    *,
    head: str = "ReviewedEvent",
    relation: str,
    tail: str = "ReviewedCause",
    source: str,
    relation_family: str,
    confidence: float,
    propagation_enabled: bool = False,
) -> KGEdge:
    return KGEdge(
        head=head,
        relation=relation,
        tail=tail,
        scenario="shared",
        source=source,
        evidence="source-grounded edge evidence",
        confidence=confidence,
        weight=1.0 - confidence,
        review_status="auto",
        feedback_count=0,
        accepted_count=0,
        rejected_count=0,
        relation_family=relation_family,
        propagation_enabled=propagation_enabled,
    )


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))
