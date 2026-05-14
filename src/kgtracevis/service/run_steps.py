"""Visible workflow-step builders for run details and case detail views."""

from __future__ import annotations

from kgtracevis.core.result import AnalysisResult
from kgtracevis.schema.evidence_schema import Evidence
from kgtracevis.service.run_models import WorkflowStep


def workflow_steps_for_case(
    *,
    evidence_path: str,
    evidence: Evidence,
    analysis: AnalysisResult,
    top_k: int,
) -> list[WorkflowStep]:
    """Build visible step cards for a loaded evidence case."""
    return [
        WorkflowStep(
            step_id="load_case",
            title="Load evidence case",
            status="completed",
            summary=f"Loaded {evidence.case_id} from {evidence_path}",
            details={
                "case_id": evidence.case_id,
                "dataset": evidence.dataset,
                "source": evidence.source,
                "observation_count": len(evidence.observations),
                "evidence_path": evidence_path,
            },
        ),
        WorkflowStep(
            step_id="validate_case",
            title="Validate evidence",
            status="completed",
            summary="Evidence schema and observed fields are ready for analysis",
            details={
                "object": evidence.object,
                "anomaly_type": evidence.anomaly_type,
                "location": evidence.location,
                "morphology": evidence.morphology,
                "confidence": evidence.confidence,
                "top_k": top_k,
            },
        ),
        WorkflowStep(
            step_id="pipeline_analysis",
            title="Run KGTracePipeline",
            status="completed",
            summary=(
                f"{len(analysis.linked_entities)} linked entities, "
                f"{len(analysis.top_k_paths)} candidate paths"
            ),
            details={
                "linked_entities": analysis.linked_entities,
                "consistency_score": analysis.consistency_score,
                "inconsistent_fields": analysis.inconsistent_fields,
                "correction_candidates": analysis.correction_candidates,
                "top_k_paths": analysis.top_k_paths,
            },
        ),
    ]


def workflow_steps_for_image_case(
    *,
    source_filename: str,
    image_path: str,
    object_name: str,
    defect_type: str | None,
    model_preset: str,
    model_backend: str,
    checkpoint: str,
    evidence: Evidence,
    analysis: AnalysisResult,
    top_k: int,
) -> list[WorkflowStep]:
    """Build visible step cards for a single uploaded image run."""
    return [
        WorkflowStep(
            step_id="upload",
            title="Upload image",
            status="completed",
            summary=f"Received {source_filename}",
            details={
                "filename": source_filename,
                "image_path": image_path,
                "object_name": object_name,
                "defect_type": defect_type,
                "model_preset": model_preset,
            },
        ),
        WorkflowStep(
            step_id="predict",
            title="Run MVTec predictor",
            status="completed",
            summary=f"Generated anomaly prediction and geometry outputs via {model_preset}",
            details={
                "model_preset": model_preset,
                "model_backend": model_backend,
                "checkpoint": checkpoint,
                "confidence": evidence.confidence,
                "anomaly_type": evidence.anomaly_type,
                "object": evidence.object,
            },
        ),
        WorkflowStep(
            step_id="adapter",
            title="Build evidence",
            status="completed",
            summary="Converted the image sample into unified evidence JSON",
            details={
                "case_id": evidence.case_id,
                "dataset": evidence.dataset,
                "observation_count": len(evidence.observations),
                "top_k": top_k,
            },
        ),
        WorkflowStep(
            step_id="pipeline_analysis",
            title="Run KGTracePipeline",
            status="completed",
            summary=(
                f"{len(analysis.linked_entities)} linked entities, "
                f"{len(analysis.top_k_paths)} candidate paths"
            ),
            details={
                "linked_entities": analysis.linked_entities,
                "consistency_score": analysis.consistency_score,
                "inconsistent_fields": analysis.inconsistent_fields,
                "correction_candidates": analysis.correction_candidates,
                "top_k_paths": analysis.top_k_paths,
            },
        ),
    ]
