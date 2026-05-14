"""Minimal reusable pipeline facade.

Scripts and services should call this facade instead of duplicating analysis
logic in their own entry points.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Protocol, cast

from kgtracevis.core.rca import (
    GenericGraphPathReasoner,
    RcaReasoner,
    RootCauseProvider,
    provider_has_reasoner,
)
from kgtracevis.core.result import AnalysisResult, RcaReasoningResult
from kgtracevis.kg.consistency_checker import check_consistency
from kgtracevis.kg.correction_generator import generate_correction_candidates
from kgtracevis.kg.entity_linker import link_evidence_entities
from kgtracevis.kg.graph import KnowledgeGraph
from kgtracevis.kg.import_neo4j import resolve_neo4j_config
from kgtracevis.kg.neo4j_repository import Neo4jKGRepository
from kgtracevis.schema.evidence_schema import Evidence


class KGSnapshotRepository(Protocol):
    """Runtime repository that can provide a scenario-scoped KG snapshot."""

    def to_knowledge_graph(self, *, scenario: str | None = None) -> KnowledgeGraph:
        """Return a graph snapshot for the selected scenario plus shared layer."""


class KGTracePipeline:
    """Reusable analysis pipeline entry point."""

    def __init__(
        self,
        graph: KnowledgeGraph | None = None,
        *,
        neo4j_repository: KGSnapshotRepository | None = None,
        root_cause_provider: RootCauseProvider | None = None,
        root_cause_reasoner: RcaReasoner | None = None,
    ) -> None:
        """Create a pipeline backed by runtime Neo4j unless a graph is explicit."""
        self.neo4j_repository = neo4j_repository
        self.root_cause_provider = root_cause_provider
        self.root_cause_reasoner = root_cause_reasoner
        self._generic_rca_reasoner = GenericGraphPathReasoner(
            root_cause_provider=root_cause_provider
        )
        self.graph = graph
        self._graph_cache: dict[str, KnowledgeGraph] = {}

    def analyze(self, evidence: Evidence, *, top_k: int = 5) -> AnalysisResult:
        """Analyze one evidence object.

        The v0 pipeline runs entity linking, consistency checking, correction
        candidate generation, and scenario-aware RCA reasoning.
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
        rca_result = self._reason_root_causes(
            evidence,
            graph=graph,
            linked_entities=linked_entities,
            top_k=top_k,
        )
        return AnalysisResult(
            case_id=evidence.case_id,
            linked_entities=linked_entities,
            consistency_score=consistency["consistency_score"],
            inconsistent_fields=consistency["inconsistent_fields"],
            correction_candidates=correction_candidates,
            top_k_paths=rca_result.top_k_paths,
            ranked_root_causes=rca_result.ranked_root_causes,
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

    def _reason_root_causes(
        self,
        evidence: Evidence,
        *,
        graph: KnowledgeGraph,
        linked_entities: list[dict[str, Any]],
        top_k: int,
    ) -> RcaReasoningResult:
        reasoner = self.root_cause_reasoner
        if reasoner is None and provider_has_reasoner(self.root_cause_provider):
            reasoner = cast(RcaReasoner, self.root_cause_provider)
        if reasoner is not None:
            result = reasoner.reason_root_causes(
                evidence,
                graph=graph,
                linked_entities=linked_entities,
                top_k=top_k,
            )
            if result.top_k_paths or result.ranked_root_causes:
                return result
        return self._generic_rca_reasoner.reason_root_causes(
            evidence,
            graph=graph,
            linked_entities=linked_entities,
            top_k=top_k,
        )
