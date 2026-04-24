"""Minimal reusable pipeline facade.

Scripts, Streamlit, and future services should call this facade instead of
duplicating analysis logic in their own entry points.
"""

from __future__ import annotations

from kgtracevis.core.result import AnalysisResult
from kgtracevis.schema.evidence_schema import Evidence


class KGTracePipeline:
    """Reusable analysis pipeline entry point."""

    def analyze(self, evidence: Evidence) -> AnalysisResult:
        """Analyze one evidence object.

        The v0 skeleton only returns the stable result envelope. Entity linking,
        consistency checking, correction, and path ranking should be wired here
        as those modules are implemented.
        """
        return AnalysisResult(
            case_id=evidence.case_id,
            linked_entities=evidence.kg_analysis.linked_entities,
            consistency_score=evidence.kg_analysis.consistency_score,
            inconsistent_fields=evidence.kg_analysis.inconsistent_fields,
            correction_candidates=evidence.kg_analysis.correction_candidates,
            top_k_paths=evidence.kg_analysis.top_k_paths,
            human_feedback=evidence.human_feedback,
        )
