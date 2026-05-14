"""Unified RCA reasoning contracts and default graph-path implementation."""

from __future__ import annotations

from inspect import Parameter, signature
from typing import Any, Protocol

from kgtracevis.core.result import (
    RankedRootCause,
    RcaReasoningResult,
    ranked_root_causes_from_paths,
)
from kgtracevis.kg.graph import KnowledgeGraph
from kgtracevis.kg.path_ranker import rank_root_cause_paths
from kgtracevis.schema.evidence_schema import Evidence


class RootCauseProvider(Protocol):
    """Backward-compatible provider for scenario-specific RCA rankings."""

    def rank_root_causes(
        self,
        evidence: Evidence,
        *,
        graph: KnowledgeGraph | None = None,
        top_k: int = 5,
        top_k_paths: list[dict[str, Any]] | None = None,
    ) -> list[RankedRootCause]:
        """Return unified root-cause candidates for one evidence object."""


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

    def __init__(self, root_cause_provider: RootCauseProvider | None = None) -> None:
        """Create a generic reasoner with an optional legacy ranking provider."""
        self.root_cause_provider = root_cause_provider

    def reason_root_causes(
        self,
        evidence: Evidence,
        *,
        graph: KnowledgeGraph,
        linked_entities: list[dict[str, Any]],
        top_k: int = 5,
    ) -> RcaReasoningResult:
        """Rank generic KG paths and derive or override root-cause candidates."""
        top_k_paths = rank_root_cause_paths(evidence, graph, linked_entities, top_k=top_k)
        ranked_root_causes = self._rank_root_causes(
            evidence,
            graph=graph,
            top_k=top_k,
            top_k_paths=top_k_paths,
        )
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
                "legacy_provider": (
                    type(self.root_cause_provider).__name__
                    if self.root_cause_provider is not None
                    else None
                ),
            },
        )

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
            if provider_accepts_graph(ranker):
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


def provider_accepts_graph(ranker: Any) -> bool:
    """Return whether a provider method accepts runtime graph context."""
    try:
        parameters = signature(ranker).parameters
    except (TypeError, ValueError):
        return True
    return "graph" in parameters or any(
        parameter.kind is Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )


def provider_has_reasoner(provider: RootCauseProvider | None) -> bool:
    """Return whether a provider also implements the unified reasoner method."""
    if provider is None:
        return False
    method = getattr(provider, "reason_root_causes", None)
    return callable(method)
