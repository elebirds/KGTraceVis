"""Run-session helpers for uploaded sample processing."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from kgtracevis.core import KGTracePipeline
from kgtracevis.core.result import AnalysisResult
from kgtracevis.experiments.adapter_pipeline import run_adapter_pipeline
from kgtracevis.schema.evidence_schema import DatasetName, Evidence
from kgtracevis.schema.validators import load_evidence_json

DEFAULT_RUNS_DIR = Path("runs/web_sessions")
UploadMode = Literal["evidence", "records"]
RunStatus = Literal["completed", "failed"]


class WorkflowStep(BaseModel):
    """One visible step in an uploaded-sample or evidence analysis run."""

    model_config = ConfigDict(extra="forbid")

    step_id: str
    title: str
    status: RunStatus
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)


class RunSummary(BaseModel):
    """Compact metadata for the run list."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    created_at: str
    mode: UploadMode
    source_filename: str
    top_k: int
    run_dir: str
    status: RunStatus = "completed"
    dataset: str | None = None
    case_count: int = 0
    evidence_count: int = 0
    label: str


class RunDetail(BaseModel):
    """Persisted detail record for one uploaded sample run."""

    model_config = ConfigDict(extra="forbid")

    run: RunSummary
    workflow_steps: list[WorkflowStep] = Field(default_factory=list)
    claim_boundary: str
    evidence: dict[str, Any] | None = None
    evidence_with_analysis: dict[str, Any] | None = None
    analysis: dict[str, Any] | None = None
    summary: dict[str, Any] | None = None
    cases: list[dict[str, Any]] = Field(default_factory=list)
    artifacts: dict[str, str] = Field(default_factory=dict)


def list_runs(
    runs_dir: str | Path = DEFAULT_RUNS_DIR,
) -> list[RunSummary]:
    """Return persisted uploaded-sample runs, newest first."""
    base = Path(runs_dir)
    if not base.exists():
        return []

    runs: list[RunSummary] = []
    for manifest_path in sorted(base.glob("*/manifest.json")):
        try:
            detail = RunDetail.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        runs.append(detail.run)
    return sorted(runs, key=lambda item: item.created_at, reverse=True)


def get_run_detail(
    run_id: str,
    *,
    runs_dir: str | Path = DEFAULT_RUNS_DIR,
) -> RunDetail:
    """Load one persisted run detail by ID."""
    manifest_path = Path(runs_dir) / run_id / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"unknown run session: {run_id}")
    return RunDetail.model_validate_json(manifest_path.read_text(encoding="utf-8"))


def create_run_from_upload(
    filename: str,
    content: bytes,
    *,
    mode: UploadMode,
    top_k: int,
    dataset: DatasetName | None = None,
    runs_dir: str | Path = DEFAULT_RUNS_DIR,
    pipeline: KGTracePipeline | None = None,
) -> RunDetail:
    """Persist one uploaded sample and run the applicable pipeline path."""
    if top_k < 1:
        raise ValueError("top_k must be >= 1")

    base_dir = Path(runs_dir)
    run_id = _build_run_id(filename)
    run_dir = base_dir / run_id
    input_dir = run_dir / "input"
    output_dir = run_dir / "output"
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    source_name = _safe_filename(filename)
    input_path = input_dir / source_name
    input_path.write_bytes(content)

    created_at = datetime.now(timezone.utc).isoformat()
    active_pipeline = pipeline or KGTracePipeline()
    if mode == "evidence":
        detail = _run_evidence_upload(
            run_id=run_id,
            created_at=created_at,
            input_path=input_path,
            source_filename=source_name,
            top_k=top_k,
            pipeline=active_pipeline,
        )
    elif mode == "records":
        detail = _run_records_upload(
            run_id=run_id,
            created_at=created_at,
            input_path=input_path,
            source_filename=source_name,
            top_k=top_k,
            dataset=dataset,
            pipeline=active_pipeline,
            output_dir=output_dir / "adapter_pipeline",
        )
    else:
        raise ValueError("upload mode must be evidence or records")

    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(json.dumps(detail.model_dump(mode="json"), indent=2), encoding="utf-8")
    return detail


def parse_upload_mode(value: str) -> UploadMode:
    """Normalize a string form value into a supported upload mode."""
    normalized = value.strip().lower()
    if normalized in {"evidence", "record", "records"}:
        return "records" if normalized in {"record", "records"} else "evidence"
    raise ValueError("upload mode must be evidence or records")


def parse_dataset_override(value: str | None) -> DatasetName | None:
    """Normalize an optional dataset override from form data."""
    if value is None:
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None
    if normalized not in {"mvtec", "tep", "wafer"}:
        raise ValueError("dataset must be one of mvtec, tep, wafer")
    return cast(DatasetName, normalized)


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


def _run_evidence_upload(
    *,
    run_id: str,
    created_at: str,
    input_path: Path,
    source_filename: str,
    top_k: int,
    pipeline: KGTracePipeline,
) -> RunDetail:
    evidence = load_evidence_json(input_path)
    analysis = pipeline.analyze(evidence, top_k=top_k)
    run = RunSummary(
        run_id=run_id,
        created_at=created_at,
        mode="evidence",
        source_filename=source_filename,
        top_k=top_k,
        run_dir=str(input_path.parent.parent),
        dataset=evidence.dataset,
        case_count=1,
        evidence_count=1,
        label=f"{evidence.dataset.upper()} · {evidence.case_id}",
    )
    detail = RunDetail(
        run=run,
        workflow_steps=[
            WorkflowStep(
                step_id="upload",
                title="Upload sample",
                status="completed",
                summary=f"Received {source_filename}",
                details={
                    "filename": source_filename,
                    "mode": "evidence",
                    "bytes": input_path.stat().st_size,
                },
            ),
            WorkflowStep(
                step_id="validate",
                title="Validate evidence",
                status="completed",
                summary=f"Validated {evidence.case_id}",
                details={
                    "case_id": evidence.case_id,
                    "dataset": evidence.dataset,
                    "source": evidence.source,
                    "object": evidence.object,
                    "anomaly_type": evidence.anomaly_type,
                },
            ),
            WorkflowStep(
                step_id="pipeline",
                title="Run pipeline",
                status="completed",
                summary=(
                    f"{len(analysis.linked_entities)} linked entities, "
                    f"{len(analysis.top_k_paths)} paths"
                ),
                details={
                    "analysis": analysis.model_dump(mode="json"),
                },
            ),
        ],
        claim_boundary=(
            "candidate/plausible explanation only; not a verified root-cause label"
        ),
        evidence=evidence.model_dump(mode="json"),
        evidence_with_analysis=_evidence_with_analysis(evidence, analysis),
        analysis=analysis.model_dump(mode="json"),
        artifacts={
            "input_path": str(input_path),
        },
    )
    return detail


def _run_records_upload(
    *,
    run_id: str,
    created_at: str,
    input_path: Path,
    source_filename: str,
    top_k: int,
    dataset: DatasetName | None,
    pipeline: KGTracePipeline,
    output_dir: Path,
) -> RunDetail:
    output = run_adapter_pipeline(
        input_path,
        output_dir,
        dataset=dataset,
        top_k=top_k,
        overwrite=True,
        pipeline=pipeline,
    )
    summary = output.summary
    summary_cases = summary.get("cases", [])
    inferred_dataset = None
    if isinstance(summary_cases, list) and summary_cases:
        first_case = summary_cases[0]
        if isinstance(first_case, dict):
            inferred_dataset = first_case.get("dataset")
    dataset_name = str(
        summary.get("input", {}).get("dataset_override")
        or dataset
        or inferred_dataset
        or "auto"
    )
    run = RunSummary(
        run_id=run_id,
        created_at=created_at,
        mode="records",
        source_filename=source_filename,
        top_k=top_k,
        run_dir=str(input_path.parent.parent),
        dataset=dataset_name,
        case_count=int(summary.get("case_count", 0)),
        evidence_count=len(output.evidence_paths),
        label=f"{source_filename} · {summary.get('case_count', 0)} cases",
    )
    detail = RunDetail(
        run=run,
        workflow_steps=[
            WorkflowStep(
                step_id="upload",
                title="Upload sample bundle",
                status="completed",
                summary=f"Received {source_filename}",
                details={
                    "filename": source_filename,
                    "mode": "records",
                    "dataset_override": dataset,
                    "bytes": input_path.stat().st_size,
                },
            ),
            WorkflowStep(
                step_id="adapt",
                title="Convert records to evidence",
                status="completed",
                summary=f"{len(output.evidence_paths)} evidence files written",
                details={
                    "summary_path": str(output.summary_path),
                    "table_path": str(output.table_path),
                    "evidence_paths": [str(path) for path in output.evidence_paths],
                    "case_count": summary.get("case_count", 0),
                },
            ),
            WorkflowStep(
                step_id="pipeline",
                title="Run KGTracePipeline",
                status="completed",
                summary=f"{summary.get('case_count', 0)} candidate explanation cases ready",
                details={
                    "summary": summary,
                },
            ),
        ],
        claim_boundary=str(summary.get("note") or (
            "candidate/plausible explanation only; not a verified root-cause label"
        )),
        summary=summary,
        cases=list(summary.get("cases", [])) if isinstance(summary.get("cases"), list) else [],
        artifacts={
            "input_path": str(input_path),
            "output_dir": str(output_dir),
            "summary_path": str(output.summary_path),
            "table_path": str(output.table_path),
        },
    )
    return detail


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


def _build_run_id(filename: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"run_{stamp}_{uuid.uuid4().hex[:8]}_{_safe_filename(Path(filename).stem)}"


def _safe_filename(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return token or "upload"
