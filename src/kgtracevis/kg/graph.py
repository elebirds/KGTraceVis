"""In-memory knowledge graph utilities for v0 analysis.

The in-memory graph is intentionally small and deterministic. It gives scripts,
tests, and service handlers a fast backend before Neo4j is required.
"""

from __future__ import annotations

import csv
import importlib
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import networkx as nx

try:  # pragma: no cover - exercised only when rapidfuzz is installed.
    _rapidfuzz_fuzz: Any | None = importlib.import_module("rapidfuzz.fuzz")
except ImportError:  # pragma: no cover
    _rapidfuzz_fuzz = None

REQUIRED_NODE_COLUMNS = {"id", "name", "label", "scenario", "aliases", "description"}
REQUIRED_EDGE_COLUMNS = {
    "head",
    "relation",
    "tail",
    "scenario",
    "source",
    "evidence",
    "confidence",
    "weight",
    "review_status",
    "feedback_count",
    "accepted_count",
    "rejected_count",
}
DEFAULT_NODE_PATHS = (
    Path("data/kg/nodes.csv"),
    Path("data/kg/mvtec_nodes.csv"),
    Path("data/kg/wafer_nodes.csv"),
)
DEFAULT_EDGE_PATHS = (
    Path("data/kg/edges.csv"),
    Path("data/kg/mvtec_rca_reference.csv"),
    Path("data/kg/mvtec_edges.csv"),
    Path("data/kg/wafer_edges.csv"),
)


def normalize_text(value: str | None) -> str:
    """Normalize text for deterministic matching."""
    if value is None:
        return ""
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def split_aliases(value: str | None) -> list[str]:
    """Split aliases from CSV cells."""
    if not value:
        return []
    return [part.strip() for part in re.split(r"[|;,]", value) if part.strip()]


@dataclass(frozen=True)
class KGNode:
    """A node from the task-oriented KG."""

    id: str
    name: str
    label: str
    scenario: str
    aliases: tuple[str, ...]
    description: str = ""

    @property
    def searchable_terms(self) -> tuple[str, ...]:
        """Return terms that can be matched by the entity linker."""
        return (self.id, self.name, *self.aliases)


@dataclass(frozen=True)
class KGEdge:
    """A source-constrained KG edge."""

    head: str
    relation: str
    tail: str
    scenario: str
    source: str
    evidence: str
    confidence: float
    weight: float
    review_status: str
    feedback_count: int
    accepted_count: int
    rejected_count: int

    @property
    def edge_id(self) -> str:
        """Return a stable edge identifier."""
        return f"{self.head}|{self.relation}|{self.tail}|{self.scenario}"

    def model_dump(self) -> dict[str, object]:
        """Return a JSON-serializable edge representation."""
        return {
            "edge_id": self.edge_id,
            "head": self.head,
            "relation": self.relation,
            "tail": self.tail,
            "scenario": self.scenario,
            "source": self.source,
            "evidence": self.evidence,
            "confidence": self.confidence,
            "weight": self.weight,
            "review_status": self.review_status,
            "feedback_count": self.feedback_count,
            "accepted_count": self.accepted_count,
            "rejected_count": self.rejected_count,
        }


@dataclass(frozen=True)
class LinkCandidate:
    """One entity linking candidate."""

    entity_id: str
    name: str
    label: str
    scenario: str
    score: float
    match_type: str
    matched_term: str

    def model_dump(self) -> dict[str, object]:
        """Return a JSON-serializable candidate representation."""
        return {
            "entity_id": self.entity_id,
            "name": self.name,
            "label": self.label,
            "scenario": self.scenario,
            "score": round(self.score, 4),
            "match_type": self.match_type,
            "matched_term": self.matched_term,
        }


class KnowledgeGraph:
    """Small directed KG loaded from CSV files."""

    def __init__(self, nodes: Iterable[KGNode], edges: Iterable[KGEdge]) -> None:
        self.nodes: dict[str, KGNode] = {node.id: node for node in nodes}
        self.edges: list[KGEdge] = list(edges)
        self.graph = nx.MultiDiGraph()
        for node in self.nodes.values():
            self.graph.add_node(node.id, **node.__dict__)
        for edge in self.edges:
            if edge.head not in self.nodes:
                raise ValueError(f"edge head does not exist in nodes.csv: {edge.head}")
            if edge.tail not in self.nodes:
                raise ValueError(f"edge tail does not exist in nodes.csv: {edge.tail}")
            self.graph.add_edge(edge.head, edge.tail, key=edge.edge_id, **edge.model_dump())

    @classmethod
    def from_csv(
        cls,
        nodes_path: str | Path = "data/kg/nodes.csv",
        edges_path: str | Path = "data/kg/edges.csv",
    ) -> KnowledgeGraph:
        """Load a knowledge graph from node and edge CSV files."""
        return cls.from_paths([nodes_path], [edges_path])

    @classmethod
    def from_default_paths(cls) -> KnowledgeGraph:
        """Load the default development KG and reference layers."""
        return cls.from_paths(DEFAULT_NODE_PATHS, DEFAULT_EDGE_PATHS, skip_missing=True)

    @classmethod
    def from_paths(
        cls,
        nodes_paths: Iterable[str | Path],
        edges_paths: Iterable[str | Path],
        *,
        skip_missing: bool = False,
        allow_reviewed_overwrite: bool = False,
    ) -> KnowledgeGraph:
        """Load and merge node and edge CSV files.

        Later files may add new rows. Duplicate edge keys are deduplicated, but a
        reviewed edge is not overwritten unless explicitly allowed.
        """
        nodes = _merge_nodes(_load_many_nodes(nodes_paths, skip_missing=skip_missing))
        edges = _merge_edges(
            _load_many_edges(edges_paths, skip_missing=skip_missing),
            allow_reviewed_overwrite=allow_reviewed_overwrite,
        )
        return cls(nodes.values(), edges.values())

    def candidates(
        self,
        mention: str | None,
        *,
        scenario: str | None = None,
        top_k: int = 5,
        min_score: float = 0.55,
    ) -> list[LinkCandidate]:
        """Return top-k entity candidates for one mention."""
        normalized_mention = normalize_text(mention)
        if not normalized_mention:
            return []

        candidates: list[LinkCandidate] = []
        for node in self.nodes.values():
            if scenario and node.scenario not in {scenario, "shared"}:
                continue
            best: LinkCandidate | None = None
            for term in node.searchable_terms:
                score, match_type = _match_score(normalized_mention, term, node)
                if score < min_score:
                    continue
                candidate = LinkCandidate(
                    entity_id=node.id,
                    name=node.name,
                    label=node.label,
                    scenario=node.scenario,
                    score=score,
                    match_type=match_type,
                    matched_term=term,
                )
                if best is None or candidate.score > best.score:
                    best = candidate
            if best is not None:
                candidates.append(best)

        candidates.sort(key=lambda item: (-item.score, item.entity_id))
        return candidates[:top_k]

    def outgoing(
        self,
        node_id: str,
        relation: str | None = None,
        *,
        scenario: str | None = None,
    ) -> list[KGEdge]:
        """Return outgoing edges, optionally filtered by relation and scenario."""
        edges = [edge for edge in self.edges if edge.head == node_id]
        if relation is not None:
            edges = [edge for edge in edges if edge.relation == relation]
        if scenario is not None:
            edges = [edge for edge in edges if self._edge_in_scope(edge, scenario)]
        return edges

    def incoming(
        self,
        node_id: str,
        relation: str | None = None,
        *,
        scenario: str | None = None,
    ) -> list[KGEdge]:
        """Return incoming edges, optionally filtered by relation and scenario."""
        edges = [edge for edge in self.edges if edge.tail == node_id]
        if relation is not None:
            edges = [edge for edge in edges if edge.relation == relation]
        if scenario is not None:
            edges = [edge for edge in edges if self._edge_in_scope(edge, scenario)]
        return edges

    def has_edge(
        self,
        head: str,
        relation: str,
        tail: str,
        *,
        scenario: str | None = None,
    ) -> bool:
        """Return whether the KG contains an in-scope relation between two nodes."""
        return any(
            edge.head == head and edge.relation == relation and edge.tail == tail
            and (scenario is None or self._edge_in_scope(edge, scenario))
            for edge in self.edges
        )

    def edge_between(
        self,
        head: str,
        tail: str,
        *,
        scenario: str | None = None,
    ) -> list[KGEdge]:
        """Return all in-scope edges between two nodes."""
        return [
            edge
            for edge in self.edges
            if edge.head == head
            and edge.tail == tail
            and (scenario is None or self._edge_in_scope(edge, scenario))
        ]

    def node_in_scope(self, node_id: str, scenario: str | None) -> bool:
        """Return whether a node belongs to the selected scenario or shared layer."""
        if scenario is None:
            return node_id in self.nodes
        node = self.nodes.get(node_id)
        return node is not None and node.scenario in {scenario, "shared"}

    def _edge_in_scope(self, edge: KGEdge, scenario: str) -> bool:
        return (
            edge.scenario in {scenario, "shared"}
            and self.node_in_scope(edge.head, scenario)
            and self.node_in_scope(edge.tail, scenario)
        )


def _load_nodes(path: Path) -> list[KGNode]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        _require_columns(path, reader.fieldnames, REQUIRED_NODE_COLUMNS)
        return [
            KGNode(
                id=row["id"].strip(),
                name=row["name"].strip(),
                label=row["label"].strip(),
                scenario=row["scenario"].strip(),
                aliases=tuple(split_aliases(row.get("aliases"))),
                description=row.get("description", "").strip(),
            )
            for row in reader
        ]


def _load_edges(path: Path) -> list[KGEdge]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        _require_columns(path, reader.fieldnames, REQUIRED_EDGE_COLUMNS)
        return [
            KGEdge(
                head=row["head"].strip(),
                relation=row["relation"].strip(),
                tail=row["tail"].strip(),
                scenario=row["scenario"].strip(),
                source=row["source"].strip(),
                evidence=row["evidence"].strip(),
                confidence=float(row["confidence"]),
                weight=float(row["weight"]),
                review_status=row["review_status"].strip(),
                feedback_count=int(row["feedback_count"]),
                accepted_count=int(row["accepted_count"]),
                rejected_count=int(row["rejected_count"]),
            )
            for row in reader
        ]


def _load_many_nodes(
    paths: Iterable[str | Path],
    *,
    skip_missing: bool,
) -> list[KGNode]:
    nodes: list[KGNode] = []
    for path_value in paths:
        path = Path(path_value)
        if skip_missing and not path.exists():
            continue
        nodes.extend(_load_nodes(path))
    return nodes


def _load_many_edges(
    paths: Iterable[str | Path],
    *,
    skip_missing: bool,
) -> list[KGEdge]:
    edges: list[KGEdge] = []
    for path_value in paths:
        path = Path(path_value)
        if skip_missing and not path.exists():
            continue
        edges.extend(_load_edges(path))
    return edges


def _merge_nodes(nodes: Iterable[KGNode]) -> dict[str, KGNode]:
    merged: dict[str, KGNode] = {}
    for node in nodes:
        existing = merged.get(node.id)
        if existing is not None and existing != node:
            raise ValueError(f"conflicting node definition for {node.id}")
        merged[node.id] = node
    return merged


def _merge_edges(
    edges: Iterable[KGEdge],
    *,
    allow_reviewed_overwrite: bool,
) -> dict[str, KGEdge]:
    merged: dict[str, KGEdge] = {}
    for edge in edges:
        existing = merged.get(edge.edge_id)
        if existing is None:
            merged[edge.edge_id] = edge
            continue
        if existing == edge:
            continue
        if existing.review_status == "reviewed" and not allow_reviewed_overwrite:
            raise ValueError(f"refusing to overwrite reviewed edge {edge.edge_id}")
        if edge.review_status == "reviewed" or existing.review_status != "reviewed":
            merged[edge.edge_id] = edge
    return merged


def _require_columns(path: Path, actual: Sequence[str] | None, required: set[str]) -> None:
    actual_set = set(actual or [])
    missing = sorted(required - actual_set)
    if missing:
        raise ValueError(f"{path} missing required columns: {', '.join(missing)}")


def _match_score(normalized_mention: str, term: str, node: KGNode) -> tuple[float, str]:
    normalized_term = normalize_text(term)
    if not normalized_term:
        return 0.0, "none"
    if normalized_mention == normalize_text(node.id):
        return 1.0, "exact_id"
    if normalized_mention == normalize_text(node.name):
        return 0.98, "exact_name"
    if normalized_mention == normalized_term:
        return 0.95, "alias"
    if normalized_mention in normalized_term or normalized_term in normalized_mention:
        return 0.82, "partial"
    if _rapidfuzz_fuzz is not None:
        return _rapidfuzz_fuzz.WRatio(normalized_mention, normalized_term) / 100.0, "fuzzy"
    return _fallback_ratio(normalized_mention, normalized_term), "fuzzy"


def _fallback_ratio(left: str, right: str) -> float:
    left_chars = set(left)
    right_chars = set(right)
    if not left_chars or not right_chars:
        return 0.0
    return len(left_chars & right_chars) / len(left_chars | right_chars)
