"""Read-only KG Studio payload helpers for the RootLens dashboard."""

from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from kgtracevis.kg.graph import REQUIRED_EDGE_COLUMNS, REQUIRED_NODE_COLUMNS

DEFAULT_SOURCE_REGISTRY_PATH = Path("data/kg/source_registry.csv")
DEFAULT_SOURCE_DOCS_DIR = Path("docs/sources")
DEFAULT_CANDIDATE_KG_DIRS = (
    Path("runs/paper_case_kg"),
    Path("runs/end_to_end_interpretability_audit/candidate_kg"),
    Path("runs/source_kg_build/runtime"),
    Path("runs/source_kg_build"),
)
GRAPH_PREVIEW_EDGE_LIMIT = 80


@dataclass(frozen=True)
class _CandidateArtifacts:
    candidate_dir: Path
    nodes_path: Path
    edges_path: Path
    summary_path: Path | None
    manifest_path: Path | None


class KGStudioSource(BaseModel):
    """One source registry row for dashboard display."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    title: str
    source_type: str
    path_or_url: str
    used_for: str
    notes: str


class KGStudioSourceDocument(BaseModel):
    """One local source note document."""

    model_config = ConfigDict(extra="forbid")

    path: str
    title: str
    line_count: int


class KGStudioGraphNode(BaseModel):
    """One node in the bounded candidate KG preview."""

    model_config = ConfigDict(extra="forbid")

    node_id: str
    label: str
    node_type: str
    scenario: str
    description: str = ""


class KGStudioGraphEdge(BaseModel):
    """One edge in the bounded candidate KG preview."""

    model_config = ConfigDict(extra="forbid")

    edge_id: str
    target_key: str
    head: str
    relation: str
    tail: str
    scenario: str
    source: str
    evidence: str
    confidence: float | None
    weight: float | None
    review_status: str


class KGStudioReviewTarget(BaseModel):
    """One reviewable KG Studio target."""

    model_config = ConfigDict(extra="forbid")

    target_type: str
    target_id: str
    target_key: str
    label: str
    source: str
    confidence: float | None
    review_status: str


class KGStudioPayload(BaseModel):
    """Read-only KG Studio bootstrap payload."""

    model_config = ConfigDict(extra="forbid")

    status: str
    claim_boundary: str
    candidate_dir: str | None
    nodes_path: str | None
    edges_path: str | None
    summary_path: str | None = None
    manifest_path: str | None = None
    source_registry_path: str
    node_count: int
    edge_count: int
    scenario_counts: dict[str, int] = Field(default_factory=dict)
    review_status_counts: dict[str, int] = Field(default_factory=dict)
    source_counts: dict[str, int] = Field(default_factory=dict)
    confidence_summary: dict[str, float | int | None] = Field(default_factory=dict)
    validation_summary: dict[str, Any] | None = None
    construction_manifest: dict[str, Any] | None = None
    sources: list[KGStudioSource] = Field(default_factory=list)
    source_documents: list[KGStudioSourceDocument] = Field(default_factory=list)
    graph_nodes: list[KGStudioGraphNode] = Field(default_factory=list)
    graph_edges: list[KGStudioGraphEdge] = Field(default_factory=list)
    review_targets: list[KGStudioReviewTarget] = Field(default_factory=list)
    note: str = (
        "KG Studio is read-only in this foundation version; feedback is append-only "
        "and does not mutate candidate or tracked KG CSV files."
    )


def kg_studio_payload(
    *,
    candidate_dirs: tuple[Path, ...] = DEFAULT_CANDIDATE_KG_DIRS,
    source_registry_path: Path = DEFAULT_SOURCE_REGISTRY_PATH,
    source_docs_dir: Path = DEFAULT_SOURCE_DOCS_DIR,
    graph_edge_limit: int = GRAPH_PREVIEW_EDGE_LIMIT,
) -> KGStudioPayload:
    """Build the read-only KG Studio payload for dashboard clients."""
    artifacts = _first_candidate_artifacts(candidate_dirs)
    sources = _load_source_registry(source_registry_path)
    source_documents = _load_source_documents(source_docs_dir)
    if artifacts is None:
        return KGStudioPayload(
            status="empty",
            claim_boundary=_claim_boundary(),
            candidate_dir=None,
            nodes_path=None,
            edges_path=None,
            source_registry_path=str(source_registry_path),
            node_count=0,
            edge_count=0,
            sources=sources,
            source_documents=source_documents,
        )

    nodes_path = artifacts.nodes_path
    edges_path = artifacts.edges_path
    node_rows = _read_csv_rows(nodes_path, required_columns=REQUIRED_NODE_COLUMNS)
    edge_rows = _read_csv_rows(edges_path, required_columns=REQUIRED_EDGE_COLUMNS)
    graph_nodes, graph_edges = _graph_preview(node_rows, edge_rows, limit=graph_edge_limit)
    validation_summary = _validation_summary(artifacts.summary_path)
    construction_manifest = _construction_manifest(artifacts.manifest_path)

    return KGStudioPayload(
        status="ok",
        claim_boundary=_claim_boundary(),
        candidate_dir=str(artifacts.candidate_dir),
        nodes_path=str(nodes_path),
        edges_path=str(edges_path),
        summary_path=str(artifacts.summary_path) if artifacts.summary_path else None,
        manifest_path=str(artifacts.manifest_path) if artifacts.manifest_path else None,
        source_registry_path=str(source_registry_path),
        node_count=len(node_rows),
        edge_count=len(edge_rows),
        scenario_counts=_count_field(edge_rows, "scenario"),
        review_status_counts=_count_field(edge_rows, "review_status"),
        source_counts=_count_field(edge_rows, "source"),
        confidence_summary=_confidence_summary(edge_rows),
        validation_summary=validation_summary,
        construction_manifest=construction_manifest,
        sources=sources,
        source_documents=source_documents,
        graph_nodes=graph_nodes,
        graph_edges=graph_edges,
        review_targets=_edge_review_targets(graph_edges),
    )


def _first_candidate_artifacts(candidate_dirs: tuple[Path, ...]) -> _CandidateArtifacts | None:
    for candidate_dir in candidate_dirs:
        for artifact_dir in _candidate_artifact_dirs(candidate_dir):
            if candidate := _candidate_artifacts_from_dir(artifact_dir):
                return candidate
    return None


def _candidate_artifact_dirs(candidate_dir: Path) -> list[Path]:
    if not candidate_dir.is_dir():
        return [candidate_dir]
    children = [
        child
        for child in candidate_dir.iterdir()
        if child.is_dir()
        and (
            (child / "nodes_candidate.csv").is_file()
            or (child / "nodes.csv").is_file()
        )
    ]
    children.sort(key=_candidate_dir_mtime, reverse=True)
    return [candidate_dir, *children]


def _candidate_dir_mtime(path: Path) -> float:
    manifest_path = path / "kg_construction_manifest.json"
    if manifest_path.is_file():
        return manifest_path.stat().st_mtime
    return path.stat().st_mtime


def _candidate_artifacts_from_dir(candidate_dir: Path) -> _CandidateArtifacts | None:
    if (
        (candidate_dir / "nodes_candidate.csv").is_file()
        and (candidate_dir / "edges_candidate.csv").is_file()
    ):
        return _CandidateArtifacts(
            candidate_dir=candidate_dir,
            nodes_path=candidate_dir / "nodes_candidate.csv",
            edges_path=candidate_dir / "edges_candidate.csv",
            summary_path=candidate_dir / "validation_report.json",
            manifest_path=None,
        )
    if (candidate_dir / "nodes.csv").is_file() and (candidate_dir / "edges.csv").is_file():
        return _CandidateArtifacts(
            candidate_dir=candidate_dir,
            nodes_path=candidate_dir / "nodes.csv",
            edges_path=candidate_dir / "edges.csv",
            summary_path=candidate_dir / "kg_construction_summary.json",
            manifest_path=candidate_dir / "kg_construction_manifest.json",
        )
    return None


def _load_source_registry(path: Path) -> list[KGStudioSource]:
    if not path.is_file():
        return []
    rows = _read_csv_rows(path)
    sources: list[KGStudioSource] = []
    for row in rows:
        sources.append(
            KGStudioSource(
                source_id=row.get("source_id", ""),
                title=row.get("title", ""),
                source_type=row.get("type", ""),
                path_or_url=row.get("path_or_url", ""),
                used_for=row.get("used_for", ""),
                notes=row.get("notes", ""),
            )
        )
    return sources


def _load_source_documents(source_docs_dir: Path) -> list[KGStudioSourceDocument]:
    if not source_docs_dir.is_dir():
        return []
    documents: list[KGStudioSourceDocument] = []
    for path in sorted(source_docs_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        title = _markdown_title(text) or path.stem
        documents.append(
            KGStudioSourceDocument(
                path=str(path),
                title=title,
                line_count=len(text.splitlines()),
            )
        )
    return documents


def _read_csv_rows(
    path: Path,
    *,
    required_columns: set[str] | None = None,
) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        if required_columns and not required_columns.issubset(fieldnames):
            return []
        return [{key: value or "" for key, value in row.items()} for row in reader]


def _graph_preview(
    node_rows: list[dict[str, str]],
    edge_rows: list[dict[str, str]],
    *,
    limit: int,
) -> tuple[list[KGStudioGraphNode], list[KGStudioGraphEdge]]:
    node_by_id = {row.get("id", ""): row for row in node_rows if row.get("id")}
    selected_edges = edge_rows[: max(limit, 0)]
    used_node_ids = {
        node_id
        for row in selected_edges
        for node_id in (row.get("head", ""), row.get("tail", ""))
        if node_id
    }
    graph_nodes = [
        _graph_node(node_by_id[node_id])
        for node_id in sorted(used_node_ids)
        if node_id in node_by_id
    ]
    graph_edges = [_graph_edge(row) for row in selected_edges]
    return graph_nodes, graph_edges


def _graph_node(row: dict[str, str]) -> KGStudioGraphNode:
    return KGStudioGraphNode(
        node_id=row.get("id", ""),
        label=row.get("name") or row.get("id", ""),
        node_type=row.get("label", ""),
        scenario=row.get("scenario", ""),
        description=row.get("description", ""),
    )


def _graph_edge(row: dict[str, str]) -> KGStudioGraphEdge:
    edge_id = _edge_id(row)
    return KGStudioGraphEdge(
        edge_id=edge_id,
        target_key=f"edge:{edge_id}",
        head=row.get("head", ""),
        relation=row.get("relation", ""),
        tail=row.get("tail", ""),
        scenario=row.get("scenario", ""),
        source=row.get("source", ""),
        evidence=row.get("evidence", ""),
        confidence=_float_or_none(row.get("confidence")),
        weight=_float_or_none(row.get("weight")),
        review_status=row.get("review_status", ""),
    )


def _edge_review_targets(edges: list[KGStudioGraphEdge]) -> list[KGStudioReviewTarget]:
    return [
        KGStudioReviewTarget(
            target_type="edge",
            target_id=edge.edge_id,
            target_key=edge.target_key,
            label=f"{edge.head} {edge.relation} {edge.tail}",
            source=edge.source,
            confidence=edge.confidence,
            review_status=edge.review_status,
        )
        for edge in edges
    ]


def _validation_summary(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    summary = payload.get("summary")
    return summary if isinstance(summary, dict) else None


def _construction_manifest(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _confidence_summary(edge_rows: list[dict[str, str]]) -> dict[str, float | int | None]:
    values = [
        value
        for value in (_float_or_none(row.get("confidence")) for row in edge_rows)
        if value is not None
    ]
    if not values:
        return {"count": 0, "min": None, "mean": None, "max": None}
    return {
        "count": len(values),
        "min": round(min(values), 4),
        "mean": round(sum(values) / len(values), 4),
        "max": round(max(values), 4),
    }


def _count_field(rows: list[dict[str, str]], field_name: str) -> dict[str, int]:
    return dict(sorted(Counter(row.get(field_name, "unknown") for row in rows).items()))


def _markdown_title(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return None


def _float_or_none(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _edge_id(row: dict[str, str]) -> str:
    return "|".join(
        [
            row.get("head", ""),
            row.get("relation", ""),
            row.get("tail", ""),
            row.get("scenario", ""),
        ]
    )


def _claim_boundary() -> str:
    return "candidate/plausible explanation only; not a verified root-cause label"
