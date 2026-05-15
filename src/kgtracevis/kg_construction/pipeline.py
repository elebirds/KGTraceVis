"""Reusable source-to-KG construction pipeline."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from kgtracevis.kg.graph import KGEdge, KGNode
from kgtracevis.kg_construction.alignment import AlignmentResult, run_entity_alignment
from kgtracevis.kg_construction.audit_graph import SourceAuditGraph
from kgtracevis.kg_construction.draft import DraftKG, KGConstructionSource
from kgtracevis.kg_construction.export_kg_csv import export_kg_csv, validate_kg_csv_contract
from kgtracevis.kg_construction.extractors import (
    ExtractorRegistry,
    default_extractor_registry,
    extract_source_draft,
)
from kgtracevis.kg_construction.models import (
    KG_CONSTRUCTION_LAYER_ARTIFACT_KEYS,
    KGConstructionBuildSummary,
    KGConstructionManifest,
    KGConstructionReviewDecision,
    build_construction_manifest,
    build_construction_summary,
    build_kg_construction_run_id,
    draft_rows_from_draft,
    kg_construction_artifact_paths,
)
from kgtracevis.kg_construction.parsers import (
    ParsedSourceContent,
    parse_source_for_extraction,
)
from kgtracevis.kg_construction.profiles import RcaProfile, profile_for_scenario
from kgtracevis.kg_construction.publish import PublishManifest
from kgtracevis.kg_construction.rca_view import RcaReasoningView, build_rca_reasoning_view
from kgtracevis.kg_construction.review_queue import (
    ReviewQueueItem,
    build_review_queue,
    review_queue_payload,
)
from kgtracevis.kg_construction.semantic_projection import (
    SemanticLayerResult,
    project_semantic_layer,
)
from kgtracevis.kg_construction.sources import current_utc_iso


@dataclass(frozen=True)
class KGConstructionResult:
    """Result of one source-to-KG construction run."""

    run_id: str
    sources: tuple[KGConstructionSource, ...]
    parsed_sources: tuple[ParsedSourceContent, ...]
    draft: DraftKG
    aligned_draft: DraftKG
    alignment: AlignmentResult
    audit_graph: SourceAuditGraph
    semantic_layer: SemanticLayerResult
    rca_view: RcaReasoningView
    review_queue: tuple[ReviewQueueItem, ...]
    publish_manifest: PublishManifest
    nodes: tuple[KGNode, ...]
    edges: tuple[KGEdge, ...]
    build_summary: KGConstructionBuildSummary
    summary: dict[str, object] = field(default_factory=dict)

    def export_csv(self, output_dir: str | Path) -> tuple[Path, Path]:
        """Export constructed KG rows as `nodes.csv` and `edges.csv`."""
        artifact_paths = kg_construction_artifact_paths(output_dir)
        nodes_path = artifact_paths["nodes"]
        edges_path = artifact_paths["edges"]
        export_kg_csv(self.nodes, self.edges, nodes_path=nodes_path, edges_path=edges_path)
        return nodes_path, edges_path

    def manifest(
        self,
        *,
        artifact_paths: dict[str, str | Path] | None = None,
        review_decisions: tuple[KGConstructionReviewDecision, ...] = (),
    ) -> KGConstructionManifest:
        """Return a manifest DTO for the constructed candidate KG layer."""
        return build_construction_manifest(
            run_id=self.run_id,
            sources=self.sources,
            draft=self.draft,
            summary=self.build_summary,
            artifact_paths=artifact_paths,
            review_decisions=review_decisions,
        )

    def write_manifest(
        self,
        path: str | Path,
        *,
        artifact_paths: dict[str, str | Path] | None = None,
        review_decisions: tuple[KGConstructionReviewDecision, ...] = (),
    ) -> Path:
        """Write a construction manifest JSON file and return its path."""
        manifest_path = Path(path)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(
                self.manifest(
                    artifact_paths=artifact_paths,
                    review_decisions=review_decisions,
                ).model_dump(mode="json"),
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return manifest_path

    def write_layer_artifacts(self, output_dir: str | Path) -> dict[str, Path]:
        """Write layer manifests and review queue artifacts."""
        artifact_paths = kg_construction_artifact_paths(output_dir)
        artifact_paths["draft_manifest"].parent.mkdir(parents=True, exist_ok=True)
        _write_json(artifact_paths["draft_manifest"], self.draft_manifest())
        _write_json(artifact_paths["source_audit_graph_manifest"], self.audit_graph.manifest())
        _write_json(artifact_paths["semantic_layer_manifest"], self.semantic_layer.manifest)
        _write_json(artifact_paths["rca_view_manifest"], self.rca_view.manifest)
        _write_json(artifact_paths["publish_manifest"], self.publish_manifest.model_dump())
        _write_json(artifact_paths["review_queue"], review_queue_payload(self.review_queue))
        return {
            key: artifact_paths[key]
            for key in KG_CONSTRUCTION_LAYER_ARTIFACT_KEYS
        }

    def draft_manifest(self) -> dict[str, object]:
        """Return a JSON-friendly DraftKG manifest."""
        extractor_versions = {
            row.extractor_name: row.extractor_version
            for row in draft_rows_from_draft(self.draft)
        }
        return {
            "artifact_type": "draft_kg_manifest_v1",
            "run_id": self.run_id,
            "source_ids": [source.source_id for source in self.sources],
            "extractor_versions": extractor_versions,
            "draft_entity_count": len(self.draft.entities),
            "draft_relation_count": len(self.draft.relations),
            "aligned_entity_count": len(self.aligned_draft.entities),
            "aligned_relation_count": len(self.aligned_draft.relations),
        }


def run_kg_construction(
    sources: Iterable[KGConstructionSource],
    *,
    registry: ExtractorRegistry | None = None,
    existing_edges: Iterable[KGEdge] = (),
    allow_reviewed_overwrite: bool = False,
    run_id: str | None = None,
    profile: RcaProfile | None = None,
    review_decisions: tuple[KGConstructionReviewDecision, ...] = (),
) -> KGConstructionResult:
    """Run the RCA-oriented source-to-KG construction pipeline."""
    extractor_registry = registry or default_extractor_registry()
    source_rows = list(sources)
    extractors = [
        extractor_registry.extractor_for(source.source_type)
        for source in source_rows
    ]
    parsed_sources = [
        parse_source_for_extraction(source)
        for source in source_rows
    ]
    drafts = [
        extract_source_draft(extractor, source, parsed)
        for extractor, source, parsed in zip(
            extractors,
            source_rows,
            parsed_sources,
            strict=True,
        )
    ]
    draft = DraftKG.combine(drafts)
    resolved_run_id = run_id or build_kg_construction_run_id()
    resolved_profile = profile or profile_for_scenario(_primary_scenario(source_rows))
    alignment = run_entity_alignment(
        draft,
        resolved_profile,
        review_decisions=review_decisions,
    )
    audit_graph = SourceAuditGraph(
        sources=tuple(source_rows),
        draft=draft,
        alignment=alignment,
        parsed_sources=tuple(parsed_sources),
    )
    semantic_layer = project_semantic_layer(alignment.draft, resolved_profile)
    rca_view = build_rca_reasoning_view(
        semantic_layer.nodes,
        semantic_layer.edges,
        profile=resolved_profile,
        kg_build_id=resolved_run_id,
    )
    review_queue = build_review_queue(rca_view.edges, alignment=alignment)
    nodes = rca_view.nodes
    edges = tuple(
        _merge_with_existing_edges(
            rca_view.edges,
            existing_edges=existing_edges,
            allow_reviewed_overwrite=allow_reviewed_overwrite,
        )
    )
    validate_kg_csv_contract(nodes, edges)
    _validate_edge_endpoints(nodes, edges)
    extractor_versions = {
        extractor.name: extractor.version
        for extractor in extractors
    }
    review_policy = "auto candidates require review before trusted publication"
    publish_manifest_generated_at = current_utc_iso()
    build_summary = build_construction_summary(
        run_id=resolved_run_id,
        sources=source_rows,
        draft=draft,
        nodes=nodes,
        edges=edges,
        extractor_versions=extractor_versions,
        profile_version=resolved_profile.ontology,
        review_policy=review_policy,
    )
    return KGConstructionResult(
        run_id=resolved_run_id,
        sources=tuple(source_rows),
        parsed_sources=tuple(parsed_sources),
        draft=draft,
        aligned_draft=alignment.draft,
        alignment=alignment,
        audit_graph=audit_graph,
        semantic_layer=semantic_layer,
        rca_view=rca_view,
        review_queue=review_queue,
        publish_manifest=PublishManifest(
            kg_build_id=resolved_run_id,
            source_ids=tuple(source.source_id for source in source_rows),
            extractor_versions=extractor_versions,
            profile_version=resolved_profile.ontology,
            node_count=len(nodes),
            edge_count=len(edges),
            review_policy=review_policy,
            published_at=publish_manifest_generated_at,
        ),
        nodes=nodes,
        edges=edges,
        build_summary=build_summary,
        summary=build_summary.model_dump(mode="json"),
    )


def _validate_edge_endpoints(nodes: tuple[KGNode, ...], edges: tuple[KGEdge, ...]) -> None:
    node_ids = {node.id for node in nodes}
    for edge in edges:
        if edge.head not in node_ids:
            raise ValueError(f"edge head does not exist in constructed nodes: {edge.head}")
        if edge.tail not in node_ids:
            raise ValueError(f"edge tail does not exist in constructed nodes: {edge.tail}")


def _primary_scenario(sources: list[KGConstructionSource]) -> str:
    scenarios = [
        source.scenario
        for source in sources
        if source.scenario and source.scenario != "shared"
    ]
    return scenarios[0] if scenarios else "shared"


def _merge_with_existing_edges(
    edges: tuple[KGEdge, ...],
    *,
    existing_edges: Iterable[KGEdge],
    allow_reviewed_overwrite: bool,
) -> tuple[KGEdge, ...]:
    protected = {edge.edge_id: edge for edge in existing_edges}
    merged: dict[str, KGEdge] = {}
    for edge in edges:
        existing = protected.get(edge.edge_id)
        if existing is not None and existing != edge:
            if existing.review_status == "reviewed" and not allow_reviewed_overwrite:
                raise ValueError(f"refusing to overwrite reviewed edge {edge.edge_id}")
        prior = merged.get(edge.edge_id)
        if prior is None:
            merged[edge.edge_id] = edge
            continue
        if prior.review_status == "reviewed" and not allow_reviewed_overwrite:
            raise ValueError(f"refusing to overwrite reviewed edge {edge.edge_id}")
        if edge.review_status == "reviewed" or prior.review_status != "reviewed":
            merged[edge.edge_id] = edge
    return tuple(sorted(merged.values(), key=lambda item: item.edge_id))


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
