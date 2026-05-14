"""Reusable source-to-KG construction pipeline."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from kgtracevis.kg.graph import KGEdge, KGNode
from kgtracevis.kg_construction.draft import DraftKG, KGConstructionSource
from kgtracevis.kg_construction.export_kg_csv import export_kg_csv, validate_kg_csv_contract
from kgtracevis.kg_construction.extractors import ExtractorRegistry, default_extractor_registry
from kgtracevis.kg_construction.models import (
    KGConstructionBuildSummary,
    KGConstructionManifest,
    build_construction_manifest,
    build_construction_summary,
    build_kg_construction_run_id,
)
from kgtracevis.kg_construction.triple_cleaner import clean_candidate_nodes, clean_candidate_triples


@dataclass(frozen=True)
class KGConstructionResult:
    """Result of one source-to-KG construction run."""

    run_id: str
    sources: tuple[KGConstructionSource, ...]
    draft: DraftKG
    nodes: tuple[KGNode, ...]
    edges: tuple[KGEdge, ...]
    build_summary: KGConstructionBuildSummary
    summary: dict[str, object] = field(default_factory=dict)

    def export_csv(self, output_dir: str | Path) -> tuple[Path, Path]:
        """Export constructed KG rows as `nodes.csv` and `edges.csv`."""
        destination = Path(output_dir)
        nodes_path = destination / "nodes.csv"
        edges_path = destination / "edges.csv"
        export_kg_csv(self.nodes, self.edges, nodes_path=nodes_path, edges_path=edges_path)
        return nodes_path, edges_path

    def manifest(
        self,
        *,
        artifact_paths: dict[str, str | Path] | None = None,
    ) -> KGConstructionManifest:
        """Return a manifest DTO for the constructed candidate KG layer."""
        return build_construction_manifest(
            run_id=self.run_id,
            sources=self.sources,
            draft=self.draft,
            summary=self.build_summary,
            artifact_paths=artifact_paths,
        )

    def write_manifest(
        self,
        path: str | Path,
        *,
        artifact_paths: dict[str, str | Path] | None = None,
    ) -> Path:
        """Write a construction manifest JSON file and return its path."""
        manifest_path = Path(path)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(
                self.manifest(artifact_paths=artifact_paths).model_dump(mode="json"),
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return manifest_path


def run_kg_construction(
    sources: Iterable[KGConstructionSource],
    *,
    registry: ExtractorRegistry | None = None,
    existing_edges: Iterable[KGEdge] = (),
    allow_reviewed_overwrite: bool = False,
    run_id: str | None = None,
) -> KGConstructionResult:
    """Run registered extractors and return validated KG rows."""
    extractor_registry = registry or default_extractor_registry()
    source_rows = list(sources)
    drafts = [
        extractor_registry.extractor_for(source.source_type).extract(source)
        for source in source_rows
    ]
    draft = DraftKG.combine(drafts)
    nodes = tuple(
        clean_candidate_nodes(entity.to_candidate_entity() for entity in draft.entities)
    )
    edges = tuple(
        clean_candidate_triples(
            (relation.to_candidate_triple() for relation in draft.relations),
            existing_edges=existing_edges,
            allow_reviewed_overwrite=allow_reviewed_overwrite,
        )
    )
    validate_kg_csv_contract(nodes, edges)
    _validate_edge_endpoints(nodes, edges)
    resolved_run_id = run_id or build_kg_construction_run_id()
    build_summary = build_construction_summary(
        run_id=resolved_run_id,
        sources=source_rows,
        draft=draft,
        nodes=nodes,
        edges=edges,
    )
    return KGConstructionResult(
        run_id=resolved_run_id,
        sources=tuple(source_rows),
        draft=draft,
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
