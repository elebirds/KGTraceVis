"""DTOs for source-to-KG construction runs and review workflow state."""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from kgtracevis.kg.graph import KGEdge, KGNode
from kgtracevis.kg_construction.confidence_assigner import edge_weight
from kgtracevis.kg_construction.draft import (
    DraftEntity,
    DraftKG,
    DraftRelation,
    KGConstructionSource,
    draft_status_to_review_status,
)

KGConstructionRunStatus = Literal["draft", "built", "reviewed", "published", "failed"]
KGConstructionDraftRowType = Literal["entity", "relation"]
KGConstructionReviewAction = Literal[
    "keep",
    "accept",
    "reject",
    "revise",
    "promote_later",
    "publish",
]

KG_CONSTRUCTION_ARTIFACT_FILENAMES: dict[str, str] = {
    "source_library_manifest": "source_library_manifest.json",
    "nodes": "nodes.csv",
    "edges": "edges.csv",
    "published_nodes": "published_nodes.csv",
    "published_edges": "published_edges.csv",
    "kg_construction_diff": "kg_construction_diff.json",
    "draft_manifest": "draft_manifest.json",
    "profile_manifest": "profile_manifest.json",
    "alignment_manifest": "entity_alignment_manifest.json",
    "source_audit_graph_manifest": "source_audit_graph_manifest.json",
    "semantic_layer_manifest": "semantic_layer_manifest.json",
    "rca_view_manifest": "rca_view_manifest.json",
    "review_queue": "review_queue.json",
    "review_decisions": "review_decisions.jsonl",
    "publish_manifest": "publish_manifest.json",
    "publish_report": "publish_report.json",
    "summary": "kg_construction_summary.json",
    "manifest": "kg_construction_manifest.json",
}
KG_CONSTRUCTION_LAYER_ARTIFACT_KEYS: tuple[str, ...] = (
    "draft_manifest",
    "profile_manifest",
    "alignment_manifest",
    "source_audit_graph_manifest",
    "semantic_layer_manifest",
    "rca_view_manifest",
    "review_queue",
    "publish_manifest",
)
KG_CONSTRUCTION_REQUIRED_ARTIFACT_KEYS: tuple[str, ...] = tuple(
    KG_CONSTRUCTION_ARTIFACT_FILENAMES
)


class KGConstructionRunRecord(BaseModel):
    """Stable run-level DTO for one source-to-KG construction execution."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    created_at: str
    status: KGConstructionRunStatus = "built"
    source_ids: list[str] = Field(default_factory=list)
    scenario_counts: dict[str, int] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class KGConstructionDraftRow(BaseModel):
    """Flat reviewable draft row emitted by construction extractors."""

    model_config = ConfigDict(extra="forbid")

    row_type: KGConstructionDraftRowType
    draft_id: str
    source_id: str
    extractor_name: str
    extractor_version: str
    scenario: str
    status: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: str
    kg_payload: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def target_key(self) -> str:
        """Return the stable review target key for this draft row."""
        return f"{self.row_type}:{self.draft_id}"


class KGConstructionReviewDecision(BaseModel):
    """One non-mutating review decision for a draft row or KG edge."""

    model_config = ConfigDict(extra="forbid")

    decision_id: str
    created_at: str
    target_type: str
    target_id: str
    target_key: str
    action: KGConstructionReviewAction
    reviewer: str | None = None
    note: str | None = None
    source: str = "kg-construction-review"
    proposed_payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class KGConstructionBuildSummary(BaseModel):
    """Counts and trust-status summary for a constructed KG candidate layer."""

    model_config = ConfigDict(extra="forbid")

    artifact_type: str = "source_to_kg_construction_result_v1"
    run_id: str
    kg_build_id: str = ""
    source_count: int
    source_ids: list[str]
    extractor_versions: dict[str, str] = Field(default_factory=dict)
    profile_version: str = ""
    review_policy: str = ""
    draft_entity_count: int
    draft_relation_count: int
    node_count: int
    edge_count: int
    node_labels: dict[str, int] = Field(default_factory=dict)
    edge_relations: dict[str, int] = Field(default_factory=dict)
    scenarios: dict[str, int] = Field(default_factory=dict)
    review_status_counts: dict[str, int] = Field(default_factory=dict)


class KGConstructionManifest(BaseModel):
    """Manifest connecting construction inputs, draft rows, KG rows, and artifacts."""

    model_config = ConfigDict(extra="forbid")

    artifact_type: str = "source_to_kg_construction_manifest_v1"
    run: KGConstructionRunRecord
    summary: KGConstructionBuildSummary
    sources: list[dict[str, Any]]
    artifacts: dict[str, str] = Field(default_factory=dict)
    draft_rows: list[KGConstructionDraftRow] = Field(default_factory=list)
    review_decisions: list[KGConstructionReviewDecision] = Field(default_factory=list)
    material_library: dict[str, Any] = Field(default_factory=dict)


def build_kg_construction_run_id() -> str:
    """Return a stable-format construction run ID."""
    return f"kgbuild_{uuid.uuid4().hex[:12]}"


def build_review_decision_id() -> str:
    """Return a stable-format construction review decision ID."""
    return f"kgreview_{uuid.uuid4().hex[:12]}"


def current_utc_iso() -> str:
    """Return the current UTC timestamp in JSON-friendly ISO format."""
    return datetime.now(timezone.utc).isoformat()


def draft_rows_from_draft(draft: DraftKG) -> list[KGConstructionDraftRow]:
    """Flatten draft entities and relations into reviewable rows."""
    rows: list[KGConstructionDraftRow] = []
    rows.extend(_draft_entity_row(entity) for entity in draft.entities)
    rows.extend(_draft_relation_row(relation) for relation in draft.relations)
    return rows


def build_construction_summary(
    *,
    run_id: str,
    sources: Sequence[KGConstructionSource],
    draft: DraftKG,
    nodes: Sequence[KGNode],
    edges: Sequence[KGEdge],
    extractor_versions: Mapping[str, str] | None = None,
    profile_version: str = "",
    review_policy: str = "",
) -> KGConstructionBuildSummary:
    """Build a typed summary for a source-to-KG construction result."""
    node_labels = Counter(node.label for node in nodes)
    edge_relations = Counter(edge.relation for edge in edges)
    scenarios = Counter([*(node.scenario for node in nodes), *(edge.scenario for edge in edges)])
    review_statuses = Counter(edge.review_status for edge in edges)
    return KGConstructionBuildSummary(
        run_id=run_id,
        kg_build_id=run_id,
        source_count=len(sources),
        source_ids=[source.source_id for source in sources],
        extractor_versions=dict(sorted((extractor_versions or {}).items())),
        profile_version=profile_version,
        review_policy=review_policy,
        draft_entity_count=len(draft.entities),
        draft_relation_count=len(draft.relations),
        node_count=len(nodes),
        edge_count=len(edges),
        node_labels=dict(sorted(node_labels.items())),
        edge_relations=dict(sorted(edge_relations.items())),
        scenarios=dict(sorted(scenarios.items())),
        review_status_counts=dict(sorted(review_statuses.items())),
    )


def build_construction_manifest(
    *,
    run_id: str,
    sources: Sequence[KGConstructionSource],
    draft: DraftKG,
    summary: KGConstructionBuildSummary,
    artifact_paths: Mapping[str, str | Path] | None = None,
    review_decisions: Sequence[KGConstructionReviewDecision] = (),
) -> KGConstructionManifest:
    """Build a JSON-serializable manifest for a construction run."""
    return KGConstructionManifest(
        run=KGConstructionRunRecord(
            run_id=run_id,
            created_at=current_utc_iso(),
            status="built",
            source_ids=[source.source_id for source in sources],
            scenario_counts=summary.scenarios,
        ),
        summary=summary,
        sources=[_source_payload(source) for source in sources],
        artifacts=normalize_construction_artifacts(artifact_paths),
        draft_rows=draft_rows_from_draft(draft),
        review_decisions=list(review_decisions),
    )


def kg_construction_artifact_paths(output_dir: str | Path) -> dict[str, Path]:
    """Return all required construction artifact paths for an output directory."""
    destination = Path(output_dir)
    return {
        key: destination / filename
        for key, filename in KG_CONSTRUCTION_ARTIFACT_FILENAMES.items()
    }


def normalize_construction_artifacts(
    artifact_paths: Mapping[str, str | Path] | None,
) -> dict[str, str]:
    """Return a stable JSON artifact map with known construction outputs first."""
    if not artifact_paths:
        return {}
    payload: dict[str, str] = {}
    for key in KG_CONSTRUCTION_REQUIRED_ARTIFACT_KEYS:
        path = artifact_paths.get(key)
        if path is not None and str(path):
            payload[key] = str(path)
    for key in sorted(set(artifact_paths) - set(KG_CONSTRUCTION_REQUIRED_ARTIFACT_KEYS)):
        path = artifact_paths[key]
        if str(path):
            payload[key] = str(path)
    return payload


def construction_output_path_payload(
    *,
    output_dir: str | Path,
    artifact_paths: Mapping[str, str | Path],
) -> dict[str, str]:
    """Return the summary `output` payload for a construction build."""
    return {
        "output_dir": str(output_dir),
        **normalize_construction_artifacts(artifact_paths),
    }


def review_decision_for_edge(
    *,
    target_id: str,
    target_key: str,
    action: KGConstructionReviewAction,
    reviewer: str | None = None,
    note: str | None = None,
    source: str = "kg-construction-review",
    proposed_payload: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> KGConstructionReviewDecision:
    """Create a construction review decision for a KG edge target."""
    return KGConstructionReviewDecision(
        decision_id=build_review_decision_id(),
        created_at=current_utc_iso(),
        target_type="edge",
        target_id=target_id,
        target_key=target_key,
        action=action,
        reviewer=reviewer,
        note=note,
        source=source,
        proposed_payload=_jsonable(dict(proposed_payload or {})),
        metadata=_jsonable(dict(metadata or {})),
    )


def review_decision_for_item(
    *,
    target_type: str,
    target_id: str,
    target_key: str,
    action: KGConstructionReviewAction,
    reviewer: str | None = None,
    note: str | None = None,
    source: str = "kg-construction-review",
    proposed_payload: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> KGConstructionReviewDecision:
    """Create a construction review decision for any review queue target."""
    return KGConstructionReviewDecision(
        decision_id=build_review_decision_id(),
        created_at=current_utc_iso(),
        target_type=target_type,
        target_id=target_id,
        target_key=target_key,
        action=action,
        reviewer=reviewer,
        note=note,
        source=source,
        proposed_payload=_jsonable(dict(proposed_payload or {})),
        metadata=_jsonable(dict(metadata or {})),
    )


def _draft_entity_row(entity: DraftEntity) -> KGConstructionDraftRow:
    evidence = entity.evidence or entity.evidence_span or entity.draft_id
    return KGConstructionDraftRow(
        row_type="entity",
        draft_id=entity.draft_id,
        source_id=entity.source_id,
        extractor_name=entity.extractor_name,
        extractor_version=entity.extractor_version,
        scenario=entity.scenario,
        status=entity.status,
        confidence=entity.confidence,
        evidence=evidence,
        kg_payload={
            "id": entity.canonical_id or entity.entity_id_suggestion,
            "entity_id_suggestion": entity.entity_id_suggestion,
            "canonical_id": entity.canonical_id,
            "name": entity.name,
            "label": entity.label,
            "scenario": entity.scenario,
            "aliases": list(entity.aliases),
            "description": entity.description,
        },
        metadata=_jsonable(entity.metadata),
    )


def _draft_relation_row(relation: DraftRelation) -> KGConstructionDraftRow:
    evidence = relation.evidence or relation.evidence_span or relation.draft_id
    return KGConstructionDraftRow(
        row_type="relation",
        draft_id=relation.draft_id,
        source_id=relation.source_id,
        extractor_name=relation.extractor_name,
        extractor_version=relation.extractor_version,
        scenario=relation.scenario,
        status=relation.status,
        confidence=relation.confidence,
        evidence=evidence,
        kg_payload={
            "head": relation.head,
            "relation": relation.relation,
            "tail": relation.tail,
            "scenario": relation.scenario,
            "source": relation.source_id,
            "evidence": evidence,
            "confidence": relation.confidence,
            "weight": edge_weight(relation.confidence),
            "review_status": draft_status_to_review_status(relation.status),
            "relation_family": relation.metadata.get("relation_family", ""),
            "propagation_enabled": relation.metadata.get("propagation_enabled", False),
            "propagation_direction": relation.metadata.get("propagation_direction", ""),
            "propagation_priority": relation.metadata.get("propagation_priority", ""),
            "attenuation": relation.metadata.get("attenuation", ""),
            "edge_weight": relation.metadata.get("edge_weight", ""),
            "task_view": relation.metadata.get("task_view", ""),
            "external_edge_id": relation.metadata.get("external_edge_id", ""),
            "kg_build_id": relation.metadata.get("kg_build_id", ""),
        },
        metadata=_jsonable(relation.metadata),
    )


def _source_payload(source: KGConstructionSource) -> dict[str, Any]:
    return {
        "source_id": source.source_id,
        "source_type": source.source_type,
        "scenario": source.scenario,
        "path": str(source.path) if source.path is not None else None,
        "has_text": source.text is not None,
        "metadata": _jsonable(source.metadata),
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value
