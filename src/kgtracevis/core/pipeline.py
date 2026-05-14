"""Minimal reusable pipeline facade.

Scripts and services should call this facade instead of duplicating analysis
logic in their own entry points.
"""

from __future__ import annotations

from copy import deepcopy
from inspect import Parameter, signature
from typing import Any, Protocol

from kgtracevis.core.result import AnalysisResult, RankedRootCause, ranked_root_causes_from_paths
from kgtracevis.kg.consistency_checker import check_consistency
from kgtracevis.kg.correction_generator import generate_correction_candidates
from kgtracevis.kg.entity_linker import link_evidence_entities
from kgtracevis.kg.graph import KnowledgeGraph
from kgtracevis.kg.import_neo4j import resolve_neo4j_config
from kgtracevis.kg.neo4j_repository import Neo4jKGRepository
from kgtracevis.kg.path_ranker import rank_root_cause_paths
from kgtracevis.schema.evidence_schema import Evidence


class KGSnapshotRepository(Protocol):
    """Runtime repository that can provide a scenario-scoped KG snapshot."""

    def to_knowledge_graph(self, *, scenario: str | None = None) -> KnowledgeGraph:
        """Return a graph snapshot for the selected scenario plus shared layer."""


class RootCauseProvider(Protocol):
    """Optional provider for scenario-specific RCA rankings."""

    def rank_root_causes(
        self,
        evidence: Evidence,
        *,
        graph: KnowledgeGraph | None = None,
        top_k: int = 5,
        top_k_paths: list[dict[str, Any]] | None = None,
    ) -> list[RankedRootCause]:
        """Return unified root-cause candidates for one evidence object."""


class KGTracePipeline:
    """Reusable analysis pipeline entry point."""

    def __init__(
        self,
        graph: KnowledgeGraph | None = None,
        *,
        neo4j_repository: KGSnapshotRepository | None = None,
        root_cause_provider: RootCauseProvider | None = None,
    ) -> None:
        """Create a pipeline backed by runtime Neo4j unless a graph is explicit."""
        self.neo4j_repository = neo4j_repository
        self.root_cause_provider = root_cause_provider
        self.graph = graph
        self._graph_cache: dict[str, KnowledgeGraph] = {}

    def analyze(self, evidence: Evidence, *, top_k: int = 5) -> AnalysisResult:
        """Analyze one evidence object.

        The v0 pipeline runs entity linking, consistency checking, correction
        candidate generation, and relation-weighted RCA path ranking.
        """
        graph = self.graph_for_evidence(evidence)
        linked_entities = link_evidence_entities(evidence, graph)
        consistency = check_consistency(evidence, graph, linked_entities)
        correction_candidates = generate_correction_candidates(
            evidence,
            graph,
            linked_entities,
            consistency,
        )
        top_k_paths = rank_root_cause_paths(evidence, graph, linked_entities, top_k=top_k)
        ranked_root_causes = self._rank_root_causes(
            evidence,
            graph=graph,
            top_k=top_k,
            top_k_paths=top_k_paths,
        )
        return AnalysisResult(
            case_id=evidence.case_id,
            linked_entities=linked_entities,
            consistency_score=consistency["consistency_score"],
            inconsistent_fields=consistency["inconsistent_fields"],
            correction_candidates=correction_candidates,
            top_k_paths=top_k_paths,
            ranked_root_causes=ranked_root_causes,
            human_feedback=deepcopy(evidence.human_feedback),
        )

    def graph_for_evidence(self, evidence: Evidence) -> KnowledgeGraph:
        """Return the explicit graph or a cached Neo4j snapshot for this evidence dataset."""
        if self.graph is not None:
            return self.graph
        if evidence.dataset in self._graph_cache:
            return self._graph_cache[evidence.dataset]
        if self.neo4j_repository is not None:
            graph = self.neo4j_repository.to_knowledge_graph(scenario=evidence.dataset)
            self._graph_cache[evidence.dataset] = graph
            return graph

        repository = Neo4jKGRepository.connect(resolve_neo4j_config())
        try:
            graph = repository.to_knowledge_graph(scenario=evidence.dataset)
            self._graph_cache[evidence.dataset] = graph
            return graph
        finally:
            repository.close()

    def _rank_root_causes(
        self,
        evidence: Evidence,
        *,
        graph: KnowledgeGraph,
        top_k: int,
        top_k_paths: list[dict[str, Any]],
    ) -> list[RankedRootCause]:
        if self.root_cause_provider is not None:
            ranker = self.root_cause_provider.rank_root_causes
            if _provider_accepts_graph(ranker):
                provided = ranker(
                    evidence,
                    graph=graph,
                    top_k=top_k,
                    top_k_paths=top_k_paths,
                )
            else:
                provided = ranker(
                    evidence,
                    top_k=top_k,
                    top_k_paths=top_k_paths,
                )
            if provided:
                return provided
        return ranked_root_causes_from_paths(evidence.case_id, top_k_paths)


def _provider_accepts_graph(ranker: Any) -> bool:
    """Return whether a root-cause provider method accepts runtime graph context."""
    try:
        parameters = signature(ranker).parameters
    except (TypeError, ValueError):
        return True
    return "graph" in parameters or any(
        parameter.kind is Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )
