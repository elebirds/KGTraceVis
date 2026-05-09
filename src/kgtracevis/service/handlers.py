"""Reusable service handlers for the KGTraceVis web system."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from kgtracevis.core import KGTracePipeline
from kgtracevis.core.result import AnalysisResult
from kgtracevis.schema.evidence_schema import Evidence, KGAnalysis
from kgtracevis.schema.validators import load_evidence_json
from kgtracevis.service.runs import workflow_steps_for_case

DEFAULT_EVIDENCE_DIRS = (
    Path("data/examples"),
    Path("runs/real_model_pipeline/assets/mvtec/adapter_pipeline/evidence"),
    Path("runs/real_model_pipeline/assets/wm811k/adapter_pipeline/evidence"),
)
DEFAULT_FEEDBACK_PATH = Path("runs/web_feedback/feedback.jsonl")

FeedbackTargetType = Literal["case", "link", "correction", "path"]
FeedbackDecision = Literal["accept", "reject", "comment"]


class CaseSummary(BaseModel):
    """Compact case metadata for the web case list."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    dataset: str
    source: str
    evidence_path: str
    source_kind: str
    observation_count: int
    label: str
    is_real_output: bool = False


class AnalyzeRequest(BaseModel):
    """Request to analyze an existing case or a full Evidence payload."""

    model_config = ConfigDict(extra="forbid")

    case_id: str | None = None
    evidence: Evidence | None = None
    top_k: int = Field(default=5, ge=1, le=20)


class WhatIfRequest(BaseModel):
    """Request to patch an existing case and run analysis on the edited evidence."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    anomaly_type: str
    location: str | None = None
    morphology: str | None = None
    variables: list[str] = Field(default_factory=list)
    log_events: list[str] = Field(default_factory=list)
    severity: float | None = None
    confidence: float | None = None
    top_k: int = Field(default=5, ge=1, le=20)


class FeedbackRequest(BaseModel):
    """Lightweight feedback record submitted from the web UI."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    target_type: FeedbackTargetType
    decision: FeedbackDecision
    target_id: str | None = None
    comment: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def list_cases(
    case_dirs: Sequence[str | Path] = DEFAULT_EVIDENCE_DIRS,
) -> list[CaseSummary]:
    """Return all discoverable evidence cases for the web UI."""
    summaries: list[CaseSummary] = []
    for path in _iter_evidence_paths(case_dirs):
        evidence = load_evidence_json(path)
        summaries.append(_case_summary(path, evidence))
    return sorted(summaries, key=lambda item: (item.dataset, item.case_id, item.source_kind))


def get_case_detail(
    case_id: str,
    *,
    top_k: int = 5,
    pipeline: KGTracePipeline | None = None,
    case_dirs: Sequence[str | Path] = DEFAULT_EVIDENCE_DIRS,
) -> dict[str, Any]:
    """Load one case and return evidence plus fresh pipeline analysis."""
    path = _find_case_path(case_id, case_dirs=case_dirs)
    evidence = load_evidence_json(path)
    return _analysis_envelope(
        evidence,
        case_summary=_case_summary(path, evidence),
        pipeline=pipeline,
        top_k=top_k,
    )


def analyze_request(
    request: AnalyzeRequest,
    *,
    pipeline: KGTracePipeline | None = None,
    case_dirs: Sequence[str | Path] = DEFAULT_EVIDENCE_DIRS,
) -> dict[str, Any]:
    """Analyze either a full evidence payload or a known case ID."""
    if request.evidence is not None:
        return _analysis_envelope(request.evidence, pipeline=pipeline, top_k=request.top_k)
    if request.case_id is not None:
        return get_case_detail(
            request.case_id,
            top_k=request.top_k,
            pipeline=pipeline,
            case_dirs=case_dirs,
        )
    raise ValueError("analyze request requires either evidence or case_id")


def what_if_request(
    request: WhatIfRequest,
    *,
    pipeline: KGTracePipeline | None = None,
    case_dirs: Sequence[str | Path] = DEFAULT_EVIDENCE_DIRS,
) -> dict[str, Any]:
    """Patch one case and return fresh analysis for the edited evidence."""
    path = _find_case_path(request.case_id, case_dirs=case_dirs)
    base = load_evidence_json(path)
    edited = _apply_what_if(base, request)
    return _analysis_envelope(
        edited,
        case_summary=_case_summary(path, edited),
        pipeline=pipeline,
        top_k=request.top_k,
    )


def record_feedback(
    request: FeedbackRequest,
    *,
    output_path: str | Path = DEFAULT_FEEDBACK_PATH,
) -> dict[str, Any]:
    """Append one lightweight feedback record to JSONL and return a receipt."""
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "feedback_id": _feedback_id(request),
        "created_at": datetime.now(timezone.utc).isoformat(),
        **request.model_dump(mode="json"),
    }
    with destination.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return {
        "status": "recorded",
        "feedback_path": str(destination),
        "record": record,
    }


def _analysis_envelope(
    evidence: Evidence,
    *,
    case_summary: CaseSummary | None = None,
    pipeline: KGTracePipeline | None = None,
    top_k: int = 5,
) -> dict[str, Any]:
    active_pipeline = pipeline or KGTracePipeline()
    analysis = active_pipeline.analyze(evidence, top_k=top_k)
    return {
        "case": case_summary.model_dump(mode="json") if case_summary is not None else None,
        "evidence": evidence.model_dump(mode="json"),
        "analysis": analysis.model_dump(mode="json"),
        "evidence_with_analysis": _evidence_with_analysis(evidence, analysis),
        "workflow_steps": [
            step.model_dump(mode="json")
            for step in (
                workflow_steps_for_case(
                    evidence_path=case_summary.evidence_path,
                    evidence=evidence,
                    analysis=analysis,
                    top_k=top_k,
                )
                if case_summary is not None
                else []
            )
        ],
        "claim_boundary": (
            "candidate/plausible explanation only; not a verified root-cause label"
        ),
    }


def _evidence_with_analysis(evidence: Evidence, analysis: AnalysisResult) -> dict[str, Any]:
    payload = evidence.model_dump(mode="json")
    payload["kg_analysis"] = {
        "linked_entities": analysis.linked_entities,
        "consistency_score": analysis.consistency_score,
        "inconsistent_fields": analysis.inconsistent_fields,
        "correction_candidates": analysis.correction_candidates,
        "top_k_paths": analysis.top_k_paths,
    }
    return payload


def _iter_evidence_paths(case_dirs: Sequence[str | Path]) -> list[Path]:
    paths: list[Path] = []
    for directory in case_dirs:
        path = Path(directory)
        if path.is_dir():
            paths.extend(sorted(path.glob("*.json")))
    return sorted(paths, key=lambda path: (_source_priority(path), path.as_posix()))


def _find_case_path(
    case_id: str,
    *,
    case_dirs: Sequence[str | Path],
) -> Path:
    for path in _iter_evidence_paths(case_dirs):
        evidence = load_evidence_json(path)
        if evidence.case_id == case_id:
            return path
    raise ValueError(f"unknown evidence case: {case_id}")


def _case_summary(path: Path, evidence: Evidence) -> CaseSummary:
    source_kind = _source_kind(path)
    return CaseSummary(
        case_id=evidence.case_id,
        dataset=evidence.dataset,
        source=evidence.source,
        evidence_path=str(path),
        source_kind=source_kind,
        observation_count=len(evidence.observations),
        label=f"{evidence.dataset.upper()} · {evidence.case_id}",
        is_real_output=source_kind == "real_model_pipeline",
    )


def _source_kind(path: Path) -> str:
    path_text = path.as_posix()
    if "runs/real_model_pipeline" in path_text:
        return "real_model_pipeline"
    if path_text.startswith("data/examples/"):
        return "checked_in_example"
    return "external_evidence"


def _source_priority(path: Path) -> int:
    source_kind = _source_kind(path)
    if source_kind == "real_model_pipeline":
        return 0
    if source_kind == "checked_in_example":
        return 1
    return 2


def _apply_what_if(base: Evidence, request: WhatIfRequest) -> Evidence:
    payload = base.model_dump(mode="json")
    payload["anomaly_type"] = _required_text(request.anomaly_type)
    payload["location"] = _optional_text(request.location)
    payload["morphology"] = _optional_text(request.morphology)
    if request.severity is not None:
        payload["severity"] = request.severity
    if request.confidence is not None:
        payload["confidence"] = request.confidence

    raw_evidence = dict(payload["raw_evidence"])
    raw_evidence["variables"] = _clean_list(request.variables)
    raw_evidence["log_events"] = _clean_list(request.log_events)
    payload["raw_evidence"] = raw_evidence

    payload["observations"] = []
    payload["normalized_evidence"] = {}
    payload["kg_analysis"] = KGAnalysis().model_dump(mode="json")
    return Evidence.model_validate(payload)


def _required_text(value: str) -> str:
    text = value.strip()
    return text or "unknown"


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _clean_list(values: Sequence[str]) -> list[str]:
    return [str(value).strip() for value in values if str(value).strip()]


def _feedback_id(request: FeedbackRequest) -> str:
    target = request.target_id or request.target_type
    raw = f"{request.case_id}_{request.target_type}_{target}_{request.decision}"
    return "fb_" + "_".join("".join(ch.lower() if ch.isalnum() else " " for ch in raw).split())
