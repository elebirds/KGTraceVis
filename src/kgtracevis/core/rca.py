"""Unified RCA reasoning contracts and default graph-path implementation."""

from __future__ import annotations

from typing import Any, Protocol

from kgtracevis.core.result import (
    RcaReasoningResult,
    ranked_root_causes_from_paths,
)
from kgtracevis.kg.graph import KnowledgeGraph
from kgtracevis.kg.path_ranker import rank_root_cause_paths
from kgtracevis.schema.evidence_schema import Evidence


class RcaReasoner(Protocol):
    """Scenario-aware RCA strategy returning aligned paths and rankings."""

    def reason_root_causes(
        self,
        evidence: Evidence,
        *,
        graph: KnowledgeGraph,
        linked_entities: list[dict[str, Any]],
        top_k: int = 5,
    ) -> RcaReasoningResult:
        """Return RCA paths and root-cause candidates from one strategy."""


class GenericGraphPathReasoner:
    """Default relation-weighted graph path RCA strategy."""

    def reason_root_causes(
        self,
        evidence: Evidence,
        *,
        graph: KnowledgeGraph,
        linked_entities: list[dict[str, Any]],
        top_k: int = 5,
    ) -> RcaReasoningResult:
        """Rank generic KG paths and derive root-cause candidates from those paths."""
        top_k_paths = rank_root_cause_paths(evidence, graph, linked_entities, top_k=top_k)
        ranked_root_causes = ranked_root_causes_from_paths(evidence.case_id, top_k_paths)
        return RcaReasoningResult(
            case_id=evidence.case_id,
            top_k_paths=top_k_paths,
            ranked_root_causes=ranked_root_causes,
            scoring_method=(
                ranked_root_causes[0].scoring_method
                if ranked_root_causes
                else "relation_weighted_path"
            ),
            metadata={
                "reasoner": "generic_graph_path",
            },
        )
