"""Versioned publish manifest and review-controlled snapshot helpers."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Literal

from kgtracevis.kg.graph import KGEdge, KGNode
from kgtracevis.kg_construction.export_kg_csv import export_kg_csv
from kgtracevis.kg_construction.models import KGConstructionReviewDecision
from kgtracevis.kg_construction.sources import current_utc_iso


@dataclass(frozen=True)
class PublishManifest:
    """Versioned manifest prepared before runtime KG publication."""

    kg_build_id: str
    source_ids: tuple[str, ...]
    extractor_versions: dict[str, str]
    profile_version: str
    node_count: int
    edge_count: int
    review_policy: str
    published_at: str = ""

    def model_dump(self) -> dict[str, object]:
        """Return a JSON-friendly manifest payload."""
        return {
            "artifact_type": "kg_publish_manifest_v1",
            "kg_build_id": self.kg_build_id,
            "source_ids": list(self.source_ids),
            "extractor_versions": dict(self.extractor_versions),
            "profile_version": self.profile_version,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "review_policy": self.review_policy,
            "published_at": self.published_at or current_utc_iso(),
        }


PublishDisposition = Literal[
    "accepted",
    "rejected",
    "policy_allowed",
    "pending_review",
    "skipped",
]


@dataclass(frozen=True)
class PublishReportItem:
    """One publish decision for a candidate KG edge."""

    target_key: str
    disposition: PublishDisposition
    reason: str
    source: str
    relation: str
    relation_family: str
    review_status: str
    confidence: float


@dataclass(frozen=True)
class PublishSnapshot:
    """Review-controlled candidate KG snapshot ready for runtime publication."""

    kg_build_id: str
    nodes: tuple[KGNode, ...]
    edges: tuple[KGEdge, ...]
    report_items: tuple[PublishReportItem, ...]
    created_at: str
    review_policy: str

    def report_payload(self) -> dict[str, Any]:
        """Return JSON-friendly publish report payload."""
        counts = Counter(item.disposition for item in self.report_items)
        return {
            "artifact_type": "kg_publish_report_v1",
            "kg_build_id": self.kg_build_id,
            "created_at": self.created_at,
            "review_policy": self.review_policy,
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
            "disposition_counts": dict(sorted(counts.items())),
            "items": [asdict(item) for item in self.report_items],
        }


def append_review_decision(
    path: str | Path,
    decision: KGConstructionReviewDecision,
) -> Path:
    """Append one review decision to a JSONL decision log."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(decision.model_dump(mode="json"), sort_keys=True))
        handle.write("\n")
    return output_path


def load_review_decisions(path: str | Path) -> tuple[KGConstructionReviewDecision, ...]:
    """Load append-only review decisions from JSONL."""
    decision_path = Path(path)
    if not decision_path.exists():
        return ()
    decisions: list[KGConstructionReviewDecision] = []
    with decision_path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                decisions.append(KGConstructionReviewDecision.model_validate(payload))
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"invalid review decision JSONL at {decision_path}:{line_number}"
                ) from exc
    return tuple(decisions)


def build_publish_snapshot(
    *,
    kg_build_id: str,
    nodes: Sequence[KGNode],
    edges: Sequence[KGEdge],
    review_decisions: Sequence[KGConstructionReviewDecision] = (),
    review_policy: str = "accepted or low-risk policy-allowed edges only",
) -> PublishSnapshot:
    """Apply review decisions and policy to candidate KG rows."""
    latest_decisions = _latest_edge_decisions(review_decisions)
    published_edges: list[KGEdge] = []
    report_items: list[PublishReportItem] = []
    for edge in sorted(edges, key=lambda item: item.edge_id):
        decision = latest_decisions.get(edge.edge_id)
        disposition, reason, publish_edge = _publish_decision_for_edge(edge, decision)
        if publish_edge is not None:
            published_edges.append(replace(publish_edge, kg_build_id=kg_build_id))
        report_review_status = _report_review_status(
            edge,
            decision=decision,
            publish_edge=publish_edge,
        )
        report_items.append(
            PublishReportItem(
                target_key=edge.edge_id,
                disposition=disposition,
                reason=reason,
                source=edge.source,
                relation=edge.relation,
                relation_family=edge.relation_family,
                review_status=report_review_status,
                confidence=edge.confidence,
            )
        )
    node_ids = {edge.head for edge in published_edges} | {edge.tail for edge in published_edges}
    published_nodes = tuple(
        sorted((node for node in nodes if node.id in node_ids), key=lambda node: node.id)
    )
    return PublishSnapshot(
        kg_build_id=kg_build_id,
        nodes=published_nodes,
        edges=tuple(published_edges),
        report_items=tuple(report_items),
        created_at=current_utc_iso(),
        review_policy=review_policy,
    )


def write_publish_snapshot(
    snapshot: PublishSnapshot,
    *,
    nodes_path: str | Path,
    edges_path: str | Path,
    report_path: str | Path,
) -> tuple[Path, Path, Path]:
    """Write published node/edge CSVs and a publish report."""
    resolved_nodes_path = Path(nodes_path)
    resolved_edges_path = Path(edges_path)
    resolved_report_path = Path(report_path)
    export_kg_csv(
        snapshot.nodes,
        snapshot.edges,
        nodes_path=resolved_nodes_path,
        edges_path=resolved_edges_path,
    )
    resolved_report_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_report_path.write_text(
        json.dumps(snapshot.report_payload(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return resolved_nodes_path, resolved_edges_path, resolved_report_path


def _latest_edge_decisions(
    review_decisions: Sequence[KGConstructionReviewDecision],
) -> dict[str, KGConstructionReviewDecision]:
    latest: dict[str, KGConstructionReviewDecision] = {}
    for decision in review_decisions:
        if decision.target_type != "edge":
            continue
        latest[decision.target_key] = decision
    return latest


def _publish_decision_for_edge(
    edge: KGEdge,
    decision: KGConstructionReviewDecision | None,
) -> tuple[PublishDisposition, str, KGEdge | None]:
    if decision is not None:
        if decision.action == "accept":
            return (
                "accepted",
                "human accepted candidate edge",
                replace(
                    edge,
                    review_status="reviewed",
                    feedback_count=max(edge.feedback_count, 1),
                    accepted_count=max(edge.accepted_count, 1),
                ),
            )
        if decision.action == "reject":
            return "rejected", "human rejected candidate edge", None
        return "pending_review", f"review action {decision.action} does not publish", None
    if edge.review_status == "reviewed":
        return "accepted", "edge already reviewed", edge
    if edge.review_status == "rejected":
        return "rejected", "candidate edge is rejected", None
    if _is_policy_allowed(edge):
        return (
            "policy_allowed",
            "low-risk structured/support edge allowed by publish policy",
            edge,
        )
    return "pending_review", _pending_reason(edge), None


def _report_review_status(
    edge: KGEdge,
    *,
    decision: KGConstructionReviewDecision | None,
    publish_edge: KGEdge | None,
) -> str:
    if publish_edge is not None:
        return publish_edge.review_status
    if decision is not None and decision.action == "reject":
        return "rejected"
    return edge.review_status


def _is_policy_allowed(edge: KGEdge) -> bool:
    if edge.review_status != "auto":
        return False
    if _is_high_risk(edge):
        return False
    return edge.confidence >= 0.85 or (
        edge.relation in {"OBSERVED_BY", "ALIGNS_TO"}
        and edge.confidence >= 0.8
    )


def _is_high_risk(edge: KGEdge) -> bool:
    if edge.relation in {"CAUSES", "SUGGESTS_ROOT_CAUSE", "HAS_PLAUSIBLE_CAUSE"}:
        return True
    if edge.relation_family in {"CAUSES", "FAULT_SOURCE"}:
        return True
    if edge.propagation_enabled:
        return True
    source = edge.source.lower()
    return "llm" in source or "document" in source


def _pending_reason(edge: KGEdge) -> str:
    if _is_high_risk(edge):
        return "high-risk causal/propagation/document edge requires review"
    return "candidate edge does not meet automatic publish policy"
