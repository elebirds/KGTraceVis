"""Reusable KGTracePipeline construction with the TEP Root-KGD reasoner."""

from __future__ import annotations

from kgtracevis.core import KGTracePipeline
from kgtracevis.core.pipeline import KGSnapshotRepository
from kgtracevis.core.rca import RcaReasoner
from kgtracevis.kg.graph import KnowledgeGraph
from kgtracevis.workflows.tep_root_kgd import TepRootKgdRcaProvider


def build_root_cause_reasoner() -> RcaReasoner:
    """Build the single supported scenario-specific RCA reasoner.

    ``TepRootKgdRcaProvider`` only returns rankings for TEP Evidence. For other
    datasets it returns an empty RCA result and ``KGTracePipeline`` falls back to
    the generic graph path reasoner.
    """
    return TepRootKgdRcaProvider()


def build_pipeline(
    *,
    graph: KnowledgeGraph | None = None,
    neo4j_repository: KGSnapshotRepository | None = None,
) -> KGTracePipeline:
    """Build a KGTracePipeline with the single supported TEP RCA reasoner."""
    return KGTracePipeline(
        graph=graph,
        neo4j_repository=neo4j_repository,
        root_cause_reasoner=build_root_cause_reasoner(),
    )
