"""TEP RCA providers for the unified root-cause ranking contract."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from kgtracevis.core.result import RankedRootCause, RcaRankingResult, RcaReasoningResult
from kgtracevis.kg.graph import KGEdge, KGNode, KnowledgeGraph, normalize_text
from kgtracevis.schema.evidence_schema import Evidence

SCENARIO_ID_KEYS = ("scenario_id", "case_id", "scenario", "scenario_key")
FAULT_NUMBER_KEYS = ("fault_number", "fault_id")
SIMULATION_RUN_KEYS = ("simulation_run", "simulation_id", "run_id")
TEP_VARIABLE_KEYS = ("variables", "variable_names", "abnormal_variables", "tags", "sensors")
TEP_CONTRIBUTION_KEYS = (
    "variable_contributions",
    "contributions",
    "attribution",
    "variable_scores",
    "contribution_scores",
    "graph_contributions",
    "channel_contributions",
)
ROOT_CAUSE_LABELS = {"RootCause", "CauseCategory", "FaultType", "FaultAnchor"}


class TepRcaArtifactConfig(BaseModel):
    """Configurable paths for bridge-mode TEP RCA artifacts."""

    model_config = ConfigDict(extra="forbid")

    artifact_dir: Path | None = None
    ranking_path: Path | None = None
    contributions_path: Path | None = None
    source_name: str = "tep_rca_artifact"
    allow_global_rankings: bool = False


class TepScenarioSelector(BaseModel):
    """Deterministic keys used to match TEP evidence to RCA artifacts."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    scenario_ids: tuple[str, ...]
    fault_numbers: tuple[int, ...] = ()
    simulation_runs: tuple[int, ...] = ()


class TepNativeRcaConfig(BaseModel):
    """Scoring knobs for KGTraceVis-native TEP RCA ranking."""

    model_config = ConfigDict(extra="forbid")

    alpha: float = 0.50
    beta: float = 0.30
    delta: float = 0.25
    gamma: float = 0.10
    broad_fault_penalty: float = 0.12
    max_depth: int = Field(default=4, ge=1)
    max_support_variables: int = Field(default=8, ge=1)
    min_support_contribution: float = Field(default=0.0, ge=0.0, le=1.0)
    source_name: str = "tep_native_kg"


@dataclass(frozen=True)
class TepVariableEvidence:
    """One normalized TEP variable observation used by native RCA scoring."""

    variable: str
    contribution: float
    raw_names: tuple[str, ...]


@dataclass(frozen=True)
class _TepSupportPath:
    variable: TepVariableEvidence
    variable_node: KGNode
    path_nodes: tuple[str, ...]
    path_edges: tuple[KGEdge, ...]


class TepNativeRcaProvider:
    """Rank TEP root-cause candidates directly from Evidence and KGTraceVis KG."""

    def __init__(
        self,
        graph: KnowledgeGraph | None = None,
        *,
        config: TepNativeRcaConfig | None = None,
    ) -> None:
        """Create a native provider with an optional fixed graph."""
        self.graph = graph
        self.config = config or TepNativeRcaConfig()

    def reason_root_causes(
        self,
        evidence: Evidence,
        *,
        graph: KnowledgeGraph,
        linked_entities: list[dict[str, Any]],
        top_k: int = 5,
    ) -> RcaReasoningResult:
        """Return aligned native TEP support paths and root-cause rankings."""
        del linked_entities
        ranked = self.rank_root_causes(evidence, graph=graph, top_k=top_k)
        return RcaReasoningResult(
            case_id=evidence.case_id,
            top_k_paths=_native_top_k_paths_from_ranked(ranked, top_k=top_k),
            ranked_root_causes=ranked,
            scoring_method="tep_native_kg",
            metadata={
                "reasoner": "tep_native_graph",
                "scenario_scope": ["tep", "shared"],
                "uses_fault_number_for_scoring": False,
            },
        )

    def rank_root_causes(
        self,
        evidence: Evidence,
        *,
        graph: KnowledgeGraph | None = None,
        top_k: int = 5,
        top_k_paths: list[dict[str, Any]] | None = None,
    ) -> list[RankedRootCause]:
        """Return KG-backed native RCA rankings for TEP evidence."""
        if evidence.dataset != "tep":
            return []
        active_graph = graph or self.graph
        if active_graph is None:
            return []
        variable_evidence = extract_tep_variable_evidence(evidence)
        variable_evidence = _select_support_variable_evidence(
            variable_evidence,
            max_variables=self.config.max_support_variables,
            min_contribution=self.config.min_support_contribution,
        )
        if not variable_evidence:
            return []

        variable_nodes = _resolve_variable_nodes(variable_evidence, active_graph)
        if not variable_nodes:
            return []

        ranked: list[RankedRootCause] = []
        evidence_total = sum(item.contribution for item, _node in variable_nodes.values())
        variable_count = len(variable_nodes)
        for candidate in _tep_root_cause_candidates(active_graph):
            support_paths = _candidate_support_paths(
                candidate,
                active_graph,
                variable_nodes,
                max_depth=self.config.max_depth,
            )
            if not support_paths:
                continue
            ranked.append(
                _native_root_cause_from_support(
                    candidate,
                    evidence=evidence,
                    support_paths=support_paths,
                    evidence_total=evidence_total,
                    variable_count=variable_count,
                    rank=1,
                    config=self.config,
                    top_k_paths=top_k_paths or [],
                )
            )

        ranked.sort(key=lambda item: (-item.score, item.candidate_id))
        return [
            item.model_copy(update={"rank": index})
            for index, item in enumerate(ranked[:top_k], start=1)
        ]


def extract_tep_variable_evidence(evidence: Evidence) -> list[TepVariableEvidence]:
    """Extract normalized TEP variable contribution evidence from an Evidence item."""
    weights: dict[str, float | None] = {}
    raw_names: dict[str, set[str]] = {}

    def add_variable(name: Any, contribution: Any = None) -> None:
        text = str(name).strip() if name not in (None, "") else ""
        if not text:
            return
        key = _tep_variable_key(text)
        raw_names.setdefault(key, set()).add(text)
        value = _optional_float(contribution)
        if value is not None:
            weights[key] = max(0.0, value)
        else:
            weights.setdefault(key, None)

    def add_contribution_map(value: Any) -> None:
        value = _decoded_value(value)
        if not isinstance(value, dict):
            return
        for variable, contribution in value.items():
            add_variable(variable, contribution)

    for variable in evidence.raw_evidence.variables:
        add_variable(variable, evidence.raw_evidence.variable_contributions.get(variable))
    add_contribution_map(evidence.raw_evidence.variable_contributions)

    raw_extra = evidence.raw_evidence.extra or {}
    for key in TEP_VARIABLE_KEYS:
        for variable in _list_from_field(raw_extra.get(key)):
            add_variable(variable)
    for key in TEP_CONTRIBUTION_KEYS:
        add_contribution_map(raw_extra.get(key))

    normalized = evidence.normalized_evidence or {}
    for key in TEP_VARIABLE_KEYS:
        for variable in _list_from_field(normalized.get(key)):
            add_variable(variable)
    for key in TEP_CONTRIBUTION_KEYS:
        add_contribution_map(normalized.get(key))

    for observation in evidence.observations:
        if observation.facet != "variable":
            continue
        add_variable(observation.name, observation.value)
        add_contribution_map(observation.metadata.get("variable_contributions"))

    if not weights:
        return []
    positive_values = [value for value in weights.values() if value is not None and value > 0.0]
    max_value = max(positive_values, default=1.0)
    normalized_max = max(max_value, 1.0)
    results = []
    for key in sorted(weights):
        value = weights[key]
        contribution = 1.0 if value is None else min(1.0, value / normalized_max)
        results.append(
            TepVariableEvidence(
                variable=key,
                contribution=round(contribution, 6),
                raw_names=tuple(sorted(raw_names.get(key, {key}))),
            )
        )
    return results


class TepRcaArtifactProvider:
    """Read small TEP RCA artifacts and emit unified root-cause rankings."""

    def __init__(self, config: TepRcaArtifactConfig | str | Path) -> None:
        """Create a provider from an artifact directory or explicit config."""
        if isinstance(config, TepRcaArtifactConfig):
            self.config = config
        else:
            self.config = TepRcaArtifactConfig(artifact_dir=Path(config))
        self.ranking_path = _resolve_ranking_path(self.config)
        self.contributions_path = _resolve_contributions_path(self.config)
        self._ranking_rows = _load_rows(self.ranking_path) if self.ranking_path else []
        self._contributions_by_scenario = (
            _load_contributions(self.contributions_path) if self.contributions_path else {}
        )

    def reason_root_causes(
        self,
        evidence: Evidence,
        *,
        graph: KnowledgeGraph,
        linked_entities: list[dict[str, Any]],
        top_k: int = 5,
    ) -> RcaReasoningResult:
        """Return artifact-backed TEP root-cause rankings through the unified contract."""
        del graph
        del linked_entities
        ranked = self.rank_root_causes(evidence, top_k=top_k)
        selector = tep_scenario_selector(evidence)
        return RcaReasoningResult(
            case_id=evidence.case_id,
            top_k_paths=[],
            ranked_root_causes=ranked,
            scoring_method="tep_artifact_bridge",
            metadata={
                "reasoner": "tep_artifact_bridge",
                "scenario_selector": selector.model_dump(mode="json"),
                "ranking_path": str(self.ranking_path) if self.ranking_path else None,
                "contributions_path": (
                    str(self.contributions_path) if self.contributions_path else None
                ),
            },
        )

    def rank_root_causes(
        self,
        evidence: Evidence,
        *,
        graph: KnowledgeGraph | None = None,
        top_k: int = 5,
        top_k_paths: list[dict[str, Any]] | None = None,
    ) -> list[RankedRootCause]:
        """Return artifact-backed RCA rankings for TEP evidence."""
        del graph
        del top_k_paths
        if evidence.dataset != "tep" or not self._ranking_rows:
            return []
        selector = tep_scenario_selector(evidence)
        rows = [
            row
            for row in self._ranking_rows
            if _row_matches_selector(
                row,
                selector,
                allow_global_rankings=self.config.allow_global_rankings,
            )
        ]
        rows = _sort_ranking_rows(rows)
        results: list[RankedRootCause] = []
        for index, row in enumerate(rows[:top_k], start=1):
            candidate_id = _candidate_id(row)
            contribution = _matching_contribution(
                row,
                selector,
                self._contributions_by_scenario,
            )
            results.append(
                _root_cause_from_row(
                    row,
                    evidence=evidence,
                    rank=_optional_int(row.get("rank")) or index,
                    candidate_id=candidate_id,
                    contribution=contribution,
                    config=self.config,
                    selector=selector,
                    ranking_path=self.ranking_path,
                    contributions_path=self.contributions_path,
                )
            )
        results.sort(key=lambda item: (item.rank, -item.score, item.candidate_id))
        return [
            item.model_copy(update={"rank": index})
            for index, item in enumerate(results, start=1)
        ]


def run_tep_rca_bridge(
    evidence: Evidence,
    config: TepRcaArtifactConfig | str | Path,
    *,
    top_k: int = 5,
) -> RcaRankingResult:
    """Run bridge-mode TEP RCA artifact mapping for one evidence object."""
    provider = TepRcaArtifactProvider(config)
    ranked = provider.rank_root_causes(evidence, top_k=top_k)
    selector = tep_scenario_selector(evidence)
    return RcaRankingResult(
        case_id=evidence.case_id,
        ranked_root_causes=ranked,
        scoring_method="tep_artifact_bridge",
        metadata={
            "scenario_selector": selector.model_dump(mode="json"),
            "ranking_path": str(provider.ranking_path) if provider.ranking_path else None,
            "contributions_path": (
                str(provider.contributions_path) if provider.contributions_path else None
            ),
        },
    )


def _tep_root_cause_candidates(graph: KnowledgeGraph) -> list[KGNode]:
    candidates = [
        node
        for node in graph.nodes.values()
        if node.scenario in {"tep", "shared"}
        and (node.label in ROOT_CAUSE_LABELS or node.id.endswith("Cause"))
    ]
    return sorted(candidates, key=lambda node: node.id)


def _resolve_variable_nodes(
    variable_evidence: list[TepVariableEvidence],
    graph: KnowledgeGraph,
) -> dict[str, tuple[TepVariableEvidence, KGNode]]:
    variable_nodes: dict[str, tuple[TepVariableEvidence, KGNode]] = {}
    for item in variable_evidence:
        node = _best_variable_node(item, graph)
        if node is not None:
            variable_nodes[item.variable] = (item, node)
    return variable_nodes


def _best_variable_node(item: TepVariableEvidence, graph: KnowledgeGraph) -> KGNode | None:
    raw_terms = {item.variable, *item.raw_names}
    normalized_terms = {_tep_variable_key(term) for term in raw_terms}
    best_node: KGNode | None = None
    best_score = 0.0
    for node in graph.nodes.values():
        if node.scenario not in {"tep", "shared"}:
            continue
        if node.label in ROOT_CAUSE_LABELS:
            continue
        node_terms = {node.id, node.name, *node.aliases}
        exact = bool(normalized_terms & {_tep_variable_key(term) for term in node_terms})
        if exact:
            score = 1.0
        else:
            candidates = [
                candidate
                for raw_name in raw_terms
                for candidate in graph.candidates(raw_name, scenario="tep", top_k=3, min_score=0.84)
                if candidate.entity_id == node.id
            ]
            score = max((candidate.score for candidate in candidates), default=0.0)
        if score > best_score:
            best_node = node
            best_score = score
    return best_node if best_score >= 0.84 else None


def _candidate_support_paths(
    candidate: KGNode,
    graph: KnowledgeGraph,
    variable_nodes: dict[str, tuple[TepVariableEvidence, KGNode]],
    *,
    max_depth: int,
) -> list[_TepSupportPath]:
    paths: list[_TepSupportPath] = []
    for item, variable_node in variable_nodes.values():
        path = _shortest_support_path(graph, candidate.id, variable_node.id, max_depth)
        if path is not None:
            path_nodes, path_edges = path
            paths.append(
                _TepSupportPath(
                    variable=item,
                    variable_node=variable_node,
                    path_nodes=tuple(path_nodes),
                    path_edges=tuple(path_edges),
                )
            )
    return paths


def _shortest_support_path(
    graph: KnowledgeGraph,
    source_id: str,
    target_id: str,
    max_depth: int,
) -> tuple[list[str], list[KGEdge]] | None:
    queue: list[tuple[str, list[str], list[KGEdge]]] = [(source_id, [source_id], [])]
    while queue:
        node_id, path_nodes, path_edges = queue.pop(0)
        if len(path_edges) >= max_depth:
            continue
        next_edges = sorted(
            _tep_support_edges(graph, node_id),
            key=lambda edge: (-edge.confidence, edge.edge_id),
        )
        for edge in next_edges:
            next_node = edge.tail if edge.head == node_id else edge.head
            if next_node in path_nodes:
                continue
            if next_node != target_id and _is_tep_root_cause_node(graph, next_node):
                continue
            next_path_nodes = [*path_nodes, next_node]
            next_path_edges = [*path_edges, edge]
            if next_node == target_id:
                return next_path_nodes, next_path_edges
            queue.append((next_node, next_path_nodes, next_path_edges))
    return None


def _tep_support_edges(graph: KnowledgeGraph, node_id: str) -> list[KGEdge]:
    edges: list[KGEdge] = []
    for edge in (*graph.outgoing(node_id), *graph.incoming(node_id)):
        if edge.scenario not in {"tep", "shared"}:
            continue
        other_node_id = edge.tail if edge.head == node_id else edge.head
        other_node = graph.nodes.get(other_node_id)
        if other_node is None or other_node.scenario not in {"tep", "shared"}:
            continue
        edges.append(edge)
    return edges


def _is_tep_root_cause_node(graph: KnowledgeGraph, node_id: str) -> bool:
    node = graph.nodes.get(node_id)
    return node is not None and (
        node.label in ROOT_CAUSE_LABELS or node.id.endswith("Cause")
    )


def _native_root_cause_from_support(
    candidate: KGNode,
    *,
    evidence: Evidence,
    support_paths: list[_TepSupportPath],
    evidence_total: float,
    variable_count: int,
    rank: int,
    config: TepNativeRcaConfig,
    top_k_paths: list[dict[str, Any]],
) -> RankedRootCause:
    total_contribution = sum(path.variable.contribution for path in support_paths)
    evidence_match = total_contribution / max(evidence_total, 1e-9)
    graph_confidence = _weighted_graph_confidence(support_paths)
    propagation_support = len({path.variable.variable for path in support_paths}) / max(
        1,
        variable_count,
    )
    length_penalty = _weighted_path_length(support_paths) / config.max_depth
    score = (
        config.alpha * evidence_match
        + config.beta * graph_confidence
        + config.delta * propagation_support
        - config.gamma * length_penalty
        - config.broad_fault_penalty * _broad_fault_ratio(candidate, support_paths)
    )
    explanation_paths = [
        _native_explanation_path(evidence.case_id, candidate, path)
        for path in support_paths
    ]
    source_edges = _dedupe_edges(
        edge for path in support_paths for edge in path.path_edges
    )
    top_k_path_ids = [
        str(path.get("path_id"))
        for path in top_k_paths
        if candidate.id
        in {
            str(path.get("target_entity_id") or ""),
            *(str(node_id) for node_id in path.get("nodes") or []),
        }
        and path.get("path_id")
    ]
    support_path_ids = [str(path["path_id"]) for path in explanation_paths]
    return RankedRootCause(
        ranking_id=_stable_ranking_id(evidence.case_id, candidate.id),
        rank=rank,
        candidate_id=candidate.id,
        candidate_name=candidate.name,
        candidate_label=candidate.label,
        candidate_role="native_kg_candidate",
        score=round(max(0.0, score), 4),
        confidence=round(max(0.0, min(1.0, graph_confidence)), 4),
        evidence_match=round(max(0.0, min(1.0, evidence_match)), 4),
        explanation_paths=explanation_paths,
        supporting_edges=[edge.model_dump() for edge in source_edges],
        supporting_evidence=[
            {
                "evidence_id": (
                    f"{evidence.case_id}_{candidate.id}_{path.variable.variable}_contribution"
                ),
                "source": "tep_evidence",
                "variable": path.variable.raw_names[0],
                "variable_node_id": path.variable_node.id,
                "contribution": path.variable.contribution,
            }
            for path in support_paths
        ],
        scoring_method="tep_native_kg",
        scoring_details={
            "formula": "alpha*evidence_match + beta*graph_confidence + "
            "delta*propagation_support - gamma*path_length",
            "weights": config.model_dump(mode="json", exclude={"source_name"}),
            "graph_confidence": round(graph_confidence, 4),
            "propagation_support": round(propagation_support, 4),
            "path_length": round(length_penalty, 4),
            "broad_fault_ratio": round(_broad_fault_ratio(candidate, support_paths), 4),
            "supported_variables": [
                {
                    "variable": path.variable.raw_names[0],
                    "variable_key": path.variable.variable,
                    "variable_node_id": path.variable_node.id,
                    "contribution": path.variable.contribution,
                    "path_id": explanation_paths[index]["path_id"],
                }
                for index, path in enumerate(support_paths)
            ],
            "top_k_path_ids": support_path_ids or top_k_path_ids,
            "generic_top_k_path_ids": top_k_path_ids,
        },
        source=config.source_name,
        review_status="auto",
    )


def _weighted_graph_confidence(support_paths: list[_TepSupportPath]) -> float:
    total_weight = sum(path.variable.contribution for path in support_paths)
    if total_weight <= 0.0:
        return 0.0
    return sum(
        path.variable.contribution
        * (sum(edge.confidence for edge in path.path_edges) / max(1, len(path.path_edges)))
        for path in support_paths
    ) / total_weight


def _weighted_path_length(support_paths: list[_TepSupportPath]) -> float:
    total_weight = sum(path.variable.contribution for path in support_paths)
    if total_weight <= 0.0:
        return 0.0
    return sum(
        path.variable.contribution * len(path.path_edges)
        for path in support_paths
    ) / total_weight


def _broad_fault_ratio(candidate: KGNode, support_paths: list[_TepSupportPath]) -> float:
    if not support_paths:
        return 0.0
    indirect_paths = sum(1 for path in support_paths if len(path.path_edges) > 1)
    return indirect_paths / len(support_paths)


def _select_support_variable_evidence(
    variable_evidence: list[TepVariableEvidence],
    *,
    max_variables: int,
    min_contribution: float,
) -> list[TepVariableEvidence]:
    ranked = sorted(
        variable_evidence,
        key=lambda item: (-item.contribution, item.variable),
    )
    return [
        item
        for item in ranked
        if item.contribution >= min_contribution
    ][:max_variables]


def _native_explanation_path(
    case_id: str,
    candidate: KGNode,
    support_path: _TepSupportPath,
) -> dict[str, Any]:
    relations = [
        edge.relation if edge.head == head else f"REVERSE_{edge.relation}"
        for head, edge in zip(support_path.path_nodes, support_path.path_edges, strict=False)
    ]
    confidence = (
        sum(edge.confidence for edge in support_path.path_edges)
        / max(1, len(support_path.path_edges))
    )
    return {
        "path_id": _native_path_id(
            case_id,
            candidate.id,
            support_path.variable_node.id,
            support_path.path_nodes,
            relations,
        ),
        "source_entity_id": candidate.id,
        "target_entity_id": support_path.variable_node.id,
        "nodes": list(support_path.path_nodes),
        "node_names": _native_path_node_names(candidate, support_path),
        "relations": relations,
        "score": round(support_path.variable.contribution * confidence, 4),
        "length": len(support_path.path_edges),
        "confidence": round(confidence, 4),
        "evidence_match": support_path.variable.contribution,
        "supporting_evidence": [edge.evidence for edge in support_path.path_edges],
        "source_edge_ids": [edge.edge_id for edge in support_path.path_edges],
        "source_edges": [edge.model_dump() for edge in support_path.path_edges],
    }


def _native_top_k_paths_from_ranked(
    ranked_root_causes: list[RankedRootCause],
    *,
    top_k: int,
) -> list[dict[str, Any]]:
    paths: list[dict[str, Any]] = []
    seen_path_ids: set[str] = set()
    sorted_paths_by_root = [
        (
            root_cause,
            sorted(
                root_cause.explanation_paths,
                key=lambda path: (
                    -float(path.get("score") or 0.0),
                    str(path.get("path_id") or ""),
                ),
            ),
        )
        for root_cause in ranked_root_causes
    ]
    for root_cause, explanation_paths in sorted_paths_by_root:
        if explanation_paths and _append_native_path(
            paths,
            seen_path_ids,
            root_cause=root_cause,
            explanation_path=explanation_paths[0],
            top_k=top_k,
        ):
            return paths
    for root_cause, explanation_paths in sorted_paths_by_root:
        for explanation_path in explanation_paths[1:]:
            if _append_native_path(
                paths,
                seen_path_ids,
                root_cause=root_cause,
                explanation_path=explanation_path,
                top_k=top_k,
            ):
                return paths
    return paths


def _append_native_path(
    paths: list[dict[str, Any]],
    seen_path_ids: set[str],
    *,
    root_cause: RankedRootCause,
    explanation_path: dict[str, Any],
    top_k: int,
) -> bool:
    path = dict(explanation_path)
    path_id = str(path.get("path_id") or "")
    if path_id and path_id in seen_path_ids:
        return False
    if path_id:
        seen_path_ids.add(path_id)
    path.setdefault("root_cause_candidate_id", root_cause.candidate_id)
    path.setdefault("root_cause_ranking_id", root_cause.ranking_id)
    paths.append(path)
    return len(paths) >= top_k


def _native_path_node_names(candidate: KGNode, support_path: _TepSupportPath) -> list[str]:
    names: list[str] = []
    for node_id in support_path.path_nodes:
        if node_id == candidate.id:
            names.append(candidate.name)
        elif node_id == support_path.variable_node.id:
            names.append(support_path.variable_node.name)
        else:
            names.append(node_id)
    return names


def _dedupe_edges(edges: Any) -> list[KGEdge]:
    by_id: dict[str, KGEdge] = {}
    for edge in edges:
        by_id.setdefault(edge.edge_id, edge)
    return [by_id[edge_id] for edge_id in sorted(by_id)]


def _native_path_id(
    case_id: str,
    candidate_id: str,
    variable_node_id: str,
    nodes: tuple[str, ...],
    relations: list[str],
) -> str:
    signature = "|".join((candidate_id, variable_node_id, *nodes, *relations))
    digest = hashlib.sha1(signature.encode("utf-8")).hexdigest()[:10]
    return f"tep_path_{case_id}_{digest}"


def _tep_variable_key(value: str) -> str:
    token = normalize_text(value)
    token = re.sub(r"^variable", "", token)
    return token


def _resolve_ranking_path(config: TepRcaArtifactConfig) -> Path | None:
    if config.ranking_path is not None:
        return _existing_path(config.ranking_path)
    if config.artifact_dir is None:
        return None
    candidates = [
        config.artifact_dir / "root_cause_rankings.jsonl",
        config.artifact_dir / "root_kgd_rankings.jsonl",
        config.artifact_dir / "baseline_root_scores.csv",
        config.artifact_dir / "outputs" / "rca" / "baseline_root_scores.csv",
        config.artifact_dir / "data" / "processed" / "models" / "root_cause_rankings.jsonl",
        config.artifact_dir / "data" / "processed" / "models" / "root_kgd_rankings.jsonl",
    ]
    return next((path for path in candidates if path.exists()), None)


def _resolve_contributions_path(config: TepRcaArtifactConfig) -> Path | None:
    if config.contributions_path is not None:
        return _existing_path(config.contributions_path)
    if config.artifact_dir is None:
        return None
    candidates = [
        config.artifact_dir / "rbc_contributions.jsonl",
        config.artifact_dir / "data" / "processed" / "rca" / "rbc_contributions.jsonl",
    ]
    return next((path for path in candidates if path.exists()), None)


def _existing_path(path: Path) -> Path:
    if not path.exists():
        raise FileNotFoundError(f"TEP RCA artifact path does not exist: {path}")
    return path


def _load_rows(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    payloads = _load_json_payloads(path)
    rows: list[dict[str, Any]] = []
    for payload in payloads:
        rows.extend(_expand_ranking_payload(payload))
    return rows


def _load_contributions(path: Path) -> dict[str, dict[str, Any]]:
    rows: list[dict[str, Any]]
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            rows = [dict(row) for row in csv.DictReader(handle)]
    else:
        rows = [
            payload
            for payload in _load_json_payloads(path)
            if isinstance(payload, dict)
        ]
    by_scenario: dict[str, dict[str, Any]] = {}
    for row in rows:
        scenario_id = _scenario_id_from_row(row)
        if scenario_id:
            by_scenario.setdefault(scenario_id, row)
    return by_scenario


def _load_json_payloads(path: Path) -> list[Any]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if path.suffix.lower() == ".json":
        payload = json.loads(text)
        return payload if isinstance(payload, list) else [payload]
    payloads: list[Any] = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            payloads.append(json.loads(line))
    return payloads


def _expand_ranking_payload(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    candidates = (
        payload.get("ranked_candidates")
        or payload.get("rankings")
        or payload.get("candidates")
    )
    if isinstance(candidates, list):
        rows: list[dict[str, Any]] = []
        scenario_context = {
            key: value
            for key, value in payload.items()
            if key not in {"ranked_candidates", "rankings", "candidates"}
        }
        for candidate in candidates:
            if isinstance(candidate, dict):
                rows.append({**scenario_context, **candidate})
        return rows
    return [payload]


def tep_scenario_selector(evidence: Evidence) -> TepScenarioSelector:
    """Build artifact matching keys from KGTraceVis TEP evidence."""
    scenario_ids = {evidence.case_id}
    fault_numbers: set[int] = set()
    simulation_runs: set[int] = set()
    extra = evidence.raw_evidence.extra
    for key in SCENARIO_ID_KEYS:
        scenario_ids.update(_text_values(extra.get(key)))
    for key in FAULT_NUMBER_KEYS:
        fault_numbers.update(_int_values(extra.get(key)))
    for key in SIMULATION_RUN_KEYS:
        simulation_runs.update(_int_values(extra.get(key)))
    for observation in evidence.observations:
        metadata = observation.metadata or {}
        for key in SCENARIO_ID_KEYS:
            scenario_ids.update(_text_values(metadata.get(key)))
        for key in FAULT_NUMBER_KEYS:
            fault_numbers.update(_int_values(metadata.get(key)))
        for key in SIMULATION_RUN_KEYS:
            simulation_runs.update(_int_values(metadata.get(key)))
        time_window = observation.time_window or {}
        for key in SCENARIO_ID_KEYS:
            scenario_ids.update(_text_values(time_window.get(key)))
        for key in SIMULATION_RUN_KEYS:
            simulation_runs.update(_int_values(time_window.get(key)))
    return TepScenarioSelector(
        case_id=evidence.case_id,
        scenario_ids=tuple(sorted(scenario_ids)),
        fault_numbers=tuple(sorted(fault_numbers)),
        simulation_runs=tuple(sorted(simulation_runs)),
    )


def _row_matches_selector(
    row: dict[str, Any],
    selector: TepScenarioSelector,
    *,
    allow_global_rankings: bool,
) -> bool:
    scenario_id = _scenario_id_from_row(row)
    if scenario_id is not None and scenario_id in selector.scenario_ids:
        return True
    if _row_matches_fault_run(row, selector):
        return True
    return scenario_id is None and not _row_has_scenario_fields(row) and allow_global_rankings


def _scenario_id_from_row(row: dict[str, Any]) -> str | None:
    for key in SCENARIO_ID_KEYS:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _row_matches_fault_run(row: dict[str, Any], selector: TepScenarioSelector) -> bool:
    row_fault_numbers = _row_int_values(row, FAULT_NUMBER_KEYS)
    row_simulation_runs = _row_int_values(row, SIMULATION_RUN_KEYS)
    if not row_fault_numbers:
        return False
    if not set(selector.fault_numbers).isdisjoint(row_fault_numbers):
        if not row_simulation_runs:
            return True
        return not set(selector.simulation_runs).isdisjoint(row_simulation_runs)
    return False


def _row_has_scenario_fields(row: dict[str, Any]) -> bool:
    keys = (*SCENARIO_ID_KEYS, *FAULT_NUMBER_KEYS, *SIMULATION_RUN_KEYS)
    return any(row.get(key) not in (None, "") for key in keys)


def _row_int_values(row: dict[str, Any], keys: tuple[str, ...]) -> set[int]:
    values: set[int] = set()
    for key in keys:
        values.update(_int_values(row.get(key)))
    return values


def _sort_ranking_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            _optional_int(row.get("rank")) or 1_000_000,
            -_score_from_row(row),
            _candidate_id(row),
        ),
    )


def _root_cause_from_row(
    row: dict[str, Any],
    *,
    evidence: Evidence,
    rank: int,
    candidate_id: str,
    contribution: dict[str, Any] | None,
    config: TepRcaArtifactConfig,
    selector: TepScenarioSelector,
    ranking_path: Path | None,
    contributions_path: Path | None,
) -> RankedRootCause:
    score = _score_from_row(row)
    confidence = _confidence_from_row(row, score)
    top_affected_variables = _list_from_field(
        row.get("top_affected_variables")
        or row.get("top_variables")
        or (contribution or {}).get("top_variables")
        or (contribution or {}).get("top_channels")
    )
    supporting_paths = _support_paths_from_field(
        row.get("top_support_paths")
        or row.get("support_paths")
        or row.get("supporting_paths")
        or row.get("explanation_paths")
    )
    supporting_edges = _list_of_dicts(row.get("supporting_edges") or row.get("source_edges"))
    supporting_evidence = [
        {
            "evidence_id": f"{evidence.case_id}_{candidate_id}_ranking_row",
            "source": config.source_name,
            "artifact_path": str(ranking_path) if ranking_path else None,
            "payload": dict(row),
        }
    ]
    if contribution is not None:
        supporting_evidence.append(
            {
                "evidence_id": f"{evidence.case_id}_{candidate_id}_contributions",
                "source": config.source_name,
                "artifact_path": str(contributions_path) if contributions_path else None,
                "payload": dict(contribution),
            }
        )
    return RankedRootCause(
        ranking_id=_stable_ranking_id(evidence.case_id, candidate_id),
        rank=rank,
        candidate_id=candidate_id,
        candidate_name=str(
            row.get("candidate_name")
            or row.get("root_cause_name")
            or row.get("name")
            or candidate_id
        ),
        candidate_label=_optional_str(row.get("candidate_type") or row.get("candidate_label")),
        candidate_role=_optional_str(row.get("candidate_role") or row.get("role")),
        score=round(score, 4),
        confidence=confidence,
        evidence_match=_optional_float(row.get("evidence_match")),
        explanation_paths=supporting_paths,
        supporting_edges=supporting_edges,
        supporting_evidence=supporting_evidence,
        scoring_method="tep_artifact_bridge",
        scoring_details={
            "scenario_selector": selector.model_dump(mode="json"),
            "scenario_id": _scenario_id_from_row(row),
            "fault_number": row.get("fault_number") or (contribution or {}).get("fault_number"),
            "simulation_run": row.get("simulation_run")
            or (contribution or {}).get("simulation_run"),
            "root_score": _optional_float(row.get("root_score")),
            "ranking_score": _optional_float(row.get("ranking_score")),
            "structural_ranking_score": _optional_float(
                row.get("structural_ranking_score")
            ),
            "ranking_adjustment": _optional_float(row.get("ranking_adjustment")),
            "top_affected_variables": top_affected_variables,
            "artifact_paths": {
                "ranking": str(ranking_path) if ranking_path else None,
                "contributions": str(contributions_path) if contributions_path else None,
            },
        },
        source=config.source_name,
        review_status="auto",
    )


def _candidate_id(row: dict[str, Any]) -> str:
    for key in ("candidate_id", "candidate_entity_id", "root_cause_id", "entity_id"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    name = str(row.get("candidate_name") or row.get("root_cause_name") or "candidate")
    token = "".join(part.capitalize() for part in re.split(r"[^a-zA-Z0-9]+", name) if part)
    return token or f"Candidate{hashlib.sha1(name.encode('utf-8')).hexdigest()[:8]}"


def _score_from_row(row: dict[str, Any]) -> float:
    for key in ("ranking_score", "score", "root_score", "structural_ranking_score"):
        value = _optional_float(row.get(key))
        if value is not None:
            return value
    return 0.0


def _confidence_from_row(row: dict[str, Any], score: float) -> float | None:
    for key in ("confidence", "root_confidence"):
        value = _optional_float(row.get(key))
        if value is not None:
            return max(0.0, min(1.0, value))
    root_score = _optional_float(row.get("root_score"))
    if root_score is not None:
        return max(0.0, min(1.0, root_score))
    if 0.0 <= score <= 1.0:
        return score
    return None


def _matching_contribution(
    row: dict[str, Any],
    selector: TepScenarioSelector,
    contributions_by_scenario: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    scenario_id = _scenario_id_from_row(row)
    if scenario_id and scenario_id in contributions_by_scenario:
        return contributions_by_scenario[scenario_id]
    for key in selector.scenario_ids:
        if key in contributions_by_scenario:
            return contributions_by_scenario[key]
    for contribution in contributions_by_scenario.values():
        if _row_matches_fault_run(contribution, selector):
            return contribution
    return None


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _optional_str(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _text_values(value: Any) -> set[str]:
    value = _decoded_value(value)
    if value in (None, ""):
        return set()
    if isinstance(value, list | tuple | set):
        return {text for item in value for text in _text_values(item)}
    return {str(value)}


def _int_values(value: Any) -> set[int]:
    value = _decoded_value(value)
    if value in (None, ""):
        return set()
    if isinstance(value, list | tuple | set):
        return {number for item in value for number in _int_values(item)}
    try:
        return {int(float(str(value)))}
    except (TypeError, ValueError):
        return set()


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    value = _decoded_value(value)
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _support_paths_from_field(value: Any) -> list[dict[str, Any]]:
    value = _decoded_value(value)
    if not isinstance(value, list):
        return []
    paths: list[dict[str, Any]] = []
    for index, item in enumerate(value, start=1):
        if isinstance(item, dict):
            paths.append(dict(item))
            continue
        if isinstance(item, list):
            paths.append(
                {
                    "path_id": f"tep_support_path_{index}",
                    "nodes": [str(node_id) for node_id in item],
                    "relations": [],
                }
            )
    return paths


def _list_from_field(value: Any) -> list[Any]:
    value = _decoded_value(value)
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [part.strip() for part in str(value).split("|") if part.strip()]


def _decoded_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped:
        return value
    if stripped[0] in "[{":
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return value
    return value


def _stable_ranking_id(case_id: str, candidate_id: str) -> str:
    token = re.sub(r"[^a-zA-Z0-9]+", "_", candidate_id).strip("_").lower()
    return f"rca_{case_id}_{token or 'candidate'}"
