"""Minimal reusable pipeline facade.

Scripts, Streamlit, and future services should call this facade instead of
duplicating analysis logic in their own entry points.
"""

from __future__ import annotations

from copy import deepcopy

from kgtracevis.core.result import AnalysisResult
from kgtracevis.kg.consistency_checker import check_consistency
from kgtracevis.kg.correction_generator import generate_correction_candidates
from kgtracevis.kg.entity_linker import link_evidence_entities
from kgtracevis.kg.graph import KnowledgeGraph
from kgtracevis.kg.path_ranker import rank_root_cause_paths
from kgtracevis.schema.evidence_schema import Evidence


class KGTracePipeline:
    """Reusable analysis pipeline entry point."""

    def __init__(self, graph: KnowledgeGraph | None = None) -> None:
        """Create a pipeline backed by an in-memory KG."""
        self.graph = graph or KnowledgeGraph.from_default_paths()

    def analyze(self, evidence: Evidence) -> AnalysisResult:
        """Analyze one evidence object.

        The v0 pipeline runs entity linking, consistency checking, correction
        candidate generation, and relation-weighted RCA path ranking.
        """
        linked_entities = link_evidence_entities(evidence, self.graph)
        consistency = check_consistency(evidence, self.graph, linked_entities)
        correction_candidates = generate_correction_candidates(
            evidence,
            self.graph,
            linked_entities,
            consistency,
        )
        top_k_paths = rank_root_cause_paths(evidence, self.graph, linked_entities)
        return AnalysisResult(
            case_id=evidence.case_id,
            linked_entities=linked_entities,
            consistency_score=consistency["consistency_score"],
            inconsistent_fields=consistency["inconsistent_fields"],
            correction_candidates=correction_candidates,
            top_k_paths=top_k_paths,
            human_feedback=deepcopy(evidence.human_feedback),
        )
