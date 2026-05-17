"""Reusable KGTracePipeline construction with reasoning-profile resolution."""

from __future__ import annotations

from typing import Any, Literal

from kgtracevis.core import KGTracePipeline
from kgtracevis.core.pipeline import KGSnapshotRepository
from kgtracevis.core.rca import RcaReasoner
from kgtracevis.core.result import RcaReasoningResult
from kgtracevis.kg.graph import KnowledgeGraph
from kgtracevis.schema.evidence_schema import Evidence
from kgtracevis.workflows.reasoning_registry import (
    ReasoningAdapterRegistry,
    ResolvedReasoningProfile,
    default_reasoning_registry,
)

SelectionMode = Literal['default', 'explicit']


class ProfileResolvingReasoner:
    """Resolve a default or explicit reasoning adapter/profile for each Evidence."""

    def __init__(
        self,
        *,
        reasoning_profile_id: str | None = None,
        registry: ReasoningAdapterRegistry | None = None,
    ) -> None:
        """Create a resolver backed by the built-in adapter/profile registry."""
        self.registry = registry or default_reasoning_registry()
        requested = str(reasoning_profile_id or '').strip() or None
        self.reasoning_profile_id = requested
        self.selection_mode: SelectionMode = 'explicit' if requested else 'default'
        if requested is not None:
            self.registry.resolve_profile(requested)

    def reason_root_causes(
        self,
        evidence: Evidence,
        *,
        graph: KnowledgeGraph,
        linked_entities: list[dict[str, Any]],
        top_k: int = 5,
    ) -> RcaReasoningResult:
        """Resolve the selected adapter/profile and delegate RCA scoring to it."""
        profile = self._resolve_profile_for_dataset(evidence.dataset)
        reasoner = self.registry.build_reasoner(profile.reasoning_profile_id)
        result = reasoner.reason_root_causes(
            evidence,
            graph=graph,
            linked_entities=linked_entities,
            top_k=top_k,
        )
        metadata = dict(result.metadata)
        metadata['reasoning_profile_id'] = profile.reasoning_profile_id
        metadata['reasoner_adapter'] = profile.reasoner_adapter
        metadata['selection_mode'] = self.selection_mode
        return result.model_copy(update={'metadata': metadata})

    def _resolve_profile_for_dataset(self, dataset: str | None) -> ResolvedReasoningProfile:
        if self.reasoning_profile_id is not None:
            return self.registry.validate_profile_for_dataset(self.reasoning_profile_id, dataset)
        profile_id = self.registry.default_profile_id_for_dataset(dataset)
        return self.registry.resolve_profile(profile_id)


DefaultProfileResolvingReasoner = ProfileResolvingReasoner


def build_root_cause_reasoner(
    *,
    reasoning_profile_id: str | None = None,
    registry: ReasoningAdapterRegistry | None = None,
) -> RcaReasoner:
    """Build a dataset-aware RCA resolver for KGTracePipeline."""
    return ProfileResolvingReasoner(
        reasoning_profile_id=reasoning_profile_id,
        registry=registry,
    )


def build_pipeline(
    *,
    graph: KnowledgeGraph | None = None,
    neo4j_repository: KGSnapshotRepository | None = None,
    reasoning_profile_id: str | None = None,
    reasoning_registry: ReasoningAdapterRegistry | None = None,
) -> KGTracePipeline:
    """Build a KGTracePipeline with reasoning-profile resolution."""
    return KGTracePipeline(
        graph=graph,
        neo4j_repository=neo4j_repository,
        root_cause_reasoner=build_root_cause_reasoner(
            reasoning_profile_id=reasoning_profile_id,
            registry=reasoning_registry,
        ),
    )
