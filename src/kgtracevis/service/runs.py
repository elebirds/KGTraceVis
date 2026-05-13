"""Run-session helpers for uploaded sample processing."""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from kgtracevis.adapters import evidence_from_mvtec_record
from kgtracevis.adapters.batch import load_records as load_adapter_records
from kgtracevis.core import KGTracePipeline
from kgtracevis.core.result import AnalysisResult
from kgtracevis.experiments.adapter_pipeline import run_adapter_pipeline
from kgtracevis.producers import (
    AMAZON_PATCHCORE_BACKEND,
    AmazonPatchCoreBackend,
    AnomalibMVTecBackend,
    MVTecAnomalyPredictor,
    build_mvtec_records,
    download_selected_model_assets,
    is_amazon_patchcore_artifact_collection,
    is_amazon_patchcore_artifact_dir,
    list_mvtec_model_presets,
    resolve_amazon_patchcore_artifact_dir,
    write_jsonl_records,
)
from kgtracevis.producers.model_assets import ModelAsset
from kgtracevis.producers.mvtec_models import (
    DEFAULT_MVTEC_EFFICIENTAD_CHECKPOINT,
    DEFAULT_MVTEC_PATCHCORE_CHECKPOINT,
    DEFAULT_MVTEC_STFPM_CHECKPOINT,
    resolve_mvtec_model_selection,
)
from kgtracevis.schema.evidence_schema import DatasetName, Evidence
from kgtracevis.schema.validators import load_evidence_json
from kgtracevis.service.visual_evidence import (
    build_visual_evidence_artifacts,
    normalize_visual_evidence_items,
)

ROOTLENS_RUNS_DIR = Path("runs/rootlens_sessions")
LEGACY_WEB_RUNS_DIR = Path("runs/web_sessions")
DEFAULT_RUNS_DIR = ROOTLENS_RUNS_DIR
DEFAULT_MVTEC_UPLOAD_CHECKPOINT = DEFAULT_MVTEC_STFPM_CHECKPOINT
UploadMode = Literal["evidence", "records", "image"]
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
    model_preset: str | None = None
    model_backend: str | None = None


class RunDetail(BaseModel):
    """Persisted detail record for one uploaded sample run."""

    model_config = ConfigDict(extra="forbid")

    run: RunSummary
    workflow_steps: list[WorkflowStep] = Field(default_factory=list)
    claim_boundary: str
    evidence: dict[str, Any] | None = None
    evidence_summary: dict[str, Any] | None = None
    evidence_with_analysis: dict[str, Any] | None = None
    analysis: dict[str, Any] | None = None
    summary: dict[str, Any] | None = None
    cases: list[dict[str, Any]] = Field(default_factory=list)
    linked_entities: list[dict[str, Any]] = Field(default_factory=list)
    correction_candidates: list[dict[str, Any]] = Field(default_factory=list)
    top_k_paths: list[dict[str, Any]] = Field(default_factory=list)
    path_graph: dict[str, Any] = Field(default_factory=dict)
    source_edge_provenance: list[dict[str, Any]] = Field(default_factory=list)
    review_targets: list[dict[str, Any]] = Field(default_factory=list)
    artifacts: dict[str, str] = Field(default_factory=dict)
    visual_evidence: list[dict[str, Any]] = Field(default_factory=list)


def list_runs(
    runs_dir: str | Path | None = None,
) -> list[RunSummary]:
    """Return persisted uploaded-sample runs, newest first."""
    runs: list[RunSummary] = []
    seen: set[str] = set()
    for base in _run_store_dirs(runs_dir):
        if not base.exists():
            continue
        for manifest_path in sorted(base.glob("*/manifest.json")):
            try:
                detail = RunDetail.model_validate_json(
                    manifest_path.read_text(encoding="utf-8")
                )
            except Exception:
                continue
            if detail.run.run_id in seen:
                continue
            seen.add(detail.run.run_id)
            runs.append(detail.run)
    return sorted(runs, key=lambda item: item.created_at, reverse=True)


def get_run_detail(
    run_id: str,
    *,
    runs_dir: str | Path | None = None,
) -> RunDetail:
    """Load one persisted run detail by ID."""
    for base in _run_store_dirs(runs_dir):
        manifest_path = base / run_id / "manifest.json"
        if manifest_path.is_file():
            detail = RunDetail.model_validate_json(
                manifest_path.read_text(encoding="utf-8")
            )
            return _enrich_run_detail(detail)
    raise ValueError(f"unknown run session: {run_id}")


def get_run_artifact_path(
    run_id: str,
    artifact_name: str,
    *,
    runs_dir: str | Path | None = None,
) -> Path:
    """Return a safe run artifact path by filename."""
    if artifact_name != Path(artifact_name).name:
        raise ValueError("artifact name must not contain path separators")
    detail = get_run_detail(run_id, runs_dir=runs_dir)
    artifact_path = Path(detail.run.run_dir) / "artifacts" / artifact_name
    if not artifact_path.is_file():
        raise ValueError(f"unknown run artifact: {artifact_name}")
    return artifact_path


def create_run_from_upload(
    filename: str,
    content: bytes,
    *,
    mode: UploadMode,
    top_k: int,
    dataset: DatasetName | None = None,
    object_name: str | None = None,
    defect_type: str | None = None,
    model_preset: str | None = None,
    runs_dir: str | Path | None = None,
    pipeline: KGTracePipeline | None = None,
) -> RunDetail:
    """Persist one uploaded sample and run the applicable pipeline path."""
    if top_k < 1:
        raise ValueError("top_k must be >= 1")

    base_dir = Path(runs_dir or DEFAULT_RUNS_DIR)
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
    elif mode == "image":
        if dataset is not None and dataset != "mvtec":
            raise ValueError("image upload mode only supports mvtec")
        detail = _run_mvtec_image_upload(
            run_id=run_id,
            created_at=created_at,
            input_path=input_path,
            source_filename=source_name,
            object_name=_required_text(object_name, default="capsule"),
            defect_type=_optional_text(defect_type),
            model_preset=model_preset,
            top_k=top_k,
            pipeline=active_pipeline,
            output_dir=output_dir / "mvtec_image_pipeline",
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
        raise ValueError("upload mode must be evidence, records, or image")

    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(json.dumps(detail.model_dump(mode="json"), indent=2), encoding="utf-8")
    return detail


def parse_upload_mode(value: str) -> UploadMode:
    """Normalize a string form value into a supported upload mode."""
    normalized = value.strip().lower()
    if normalized in {"evidence", "record", "records", "image", "img"}:
        if normalized in {"image", "img"}:
            return "image"
        return "records" if normalized in {"record", "records"} else "evidence"
    raise ValueError("upload mode must be evidence, records, or image")


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
        **_dashboard_fields_from_analysis(evidence, analysis),
        evidence_with_analysis=_evidence_with_analysis(evidence, analysis),
        analysis=analysis.model_dump(mode="json"),
        artifacts={
            "input_path": str(input_path),
        },
        visual_evidence=build_visual_evidence_artifacts(
            [evidence.model_dump(mode="json")],
            run_id=run_id,
            run_dir=input_path.parent.parent,
        ),
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
    records = _load_visual_records(input_path)
    summary_cases = _list_of_dicts(summary.get("cases"))
    case_rows = _enriched_case_rows(summary_cases)
    inferred_dataset = None
    if case_rows:
        first_case = case_rows[0]
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
        cases=case_rows,
        **_dashboard_fields_from_cases(case_rows),
        artifacts={
            "input_path": str(input_path),
            "output_dir": str(output_dir),
            "summary_path": str(output.summary_path),
            "table_path": str(output.table_path),
        },
        visual_evidence=build_visual_evidence_artifacts(
            records,
            run_id=run_id,
            run_dir=input_path.parent.parent,
        ),
    )
    return detail


def _run_mvtec_image_upload(
    *,
    run_id: str,
    created_at: str,
    input_path: Path,
    source_filename: str,
    object_name: str,
    defect_type: str | None,
    model_preset: str | None,
    top_k: int,
    pipeline: KGTracePipeline,
    output_dir: Path,
    predictor: MVTecAnomalyPredictor | None = None,
    checkpoint: str | Path | None = None,
) -> RunDetail:
    image_root = input_path.parent / "mvtec_image_root"
    object_folder = _safe_filename(object_name)
    defect_folder = _safe_filename(defect_type or "unknown")
    case_image = image_root / object_folder / "test" / defect_folder / source_filename
    case_image.parent.mkdir(parents=True, exist_ok=True)
    case_image.write_bytes(input_path.read_bytes())

    selection = resolve_mvtec_model_selection(model_preset)
    if checkpoint is not None:
        checkpoint_path = _resolve_mvtec_checkpoint(checkpoint, model_preset=selection.preset)
    else:
        checkpoint_path = selection.checkpoint_path
    if selection.backend == AMAZON_PATCHCORE_BACKEND:
        checkpoint_path = resolve_amazon_patchcore_artifact_dir(
            checkpoint_path,
            object_name=object_folder,
        )
    active_predictor = predictor or _build_mvtec_upload_predictor(
        model_backend=selection.backend,
        checkpoint=checkpoint_path,
        device=_resolve_mvtec_device(),
    )

    generated_records = build_mvtec_records(
        image_root,
        active_predictor,
        output_dir=output_dir / "generated_records",
        model_backend=selection.backend,
        checkpoint=checkpoint_path,
        threshold=0.5,
        max_cases=1,
        include_good=True,
    )
    if not generated_records:
        raise ValueError("no MVTec evidence records were produced from the uploaded image")
    records_path = write_jsonl_records(
        generated_records,
        output_dir / "mvtec_image_records.jsonl",
        overwrite=True,
    )
    adapter_output = run_adapter_pipeline(
        records_path,
        output_dir / "adapter_pipeline",
        dataset="mvtec",
        top_k=top_k,
        overwrite=True,
        pipeline=pipeline,
    )

    evidence = evidence_from_mvtec_record(generated_records[0])
    analysis = pipeline.analyze(evidence, top_k=top_k)
    summary = adapter_output.summary
    run = RunSummary(
        run_id=run_id,
        created_at=created_at,
        mode="image",
        source_filename=source_filename,
        top_k=top_k,
        run_dir=str(input_path.parent.parent),
        dataset="mvtec",
        case_count=int(summary.get("case_count", 1)),
        evidence_count=len(adapter_output.evidence_paths),
        label=f"{object_folder} · {defect_folder} · {source_filename}",
        model_preset=selection.preset,
        model_backend=selection.backend,
    )
    detail = RunDetail(
        run=run,
        workflow_steps=workflow_steps_for_image_case(
            source_filename=source_filename,
            image_path=str(case_image),
            object_name=object_folder,
            defect_type=_optional_text(defect_type),
            model_preset=selection.preset,
            model_backend=selection.backend,
            checkpoint=str(checkpoint_path),
            evidence=evidence,
            analysis=analysis,
            top_k=top_k,
        ),
        claim_boundary=str(summary.get("note") or (
            "candidate/plausible explanation only; not a verified root-cause label"
        )),
        evidence=evidence.model_dump(mode="json"),
        **_dashboard_fields_from_analysis(evidence, analysis),
        evidence_with_analysis=_evidence_with_analysis(evidence, analysis),
        analysis=analysis.model_dump(mode="json"),
        summary=summary,
        cases=list(summary.get("cases", [])) if isinstance(summary.get("cases"), list) else [],
        artifacts={
            "input_path": str(input_path),
            "mvtec_image_root": str(image_root),
            "records_path": str(records_path),
            "output_dir": str(output_dir),
            "summary_path": str(adapter_output.summary_path),
            "table_path": str(adapter_output.table_path),
            "checkpoint_path": str(checkpoint_path),
            "model_preset": selection.preset,
            "model_backend": selection.backend,
        },
        visual_evidence=build_visual_evidence_artifacts(
            generated_records,
            run_id=run_id,
            run_dir=input_path.parent.parent,
        ),
    )
    return detail


def _build_mvtec_upload_predictor(
    *,
    model_backend: str,
    checkpoint: Path,
    device: str | None,
) -> MVTecAnomalyPredictor:
    """Build the selected raw-image upload predictor."""
    if model_backend == AMAZON_PATCHCORE_BACKEND:
        return AmazonPatchCoreBackend(checkpoint=checkpoint, device=device)
    return AnomalibMVTecBackend(
        backend=model_backend,
        checkpoint=checkpoint,
        device=device,
    )


def mvtec_model_presets() -> list[dict[str, Any]]:
    """Return the selectable MVTec model presets for API clients."""
    return list_mvtec_model_presets()


def download_model_assets(
    *,
    models: tuple[ModelAsset, ...] = ("mvtec-stfpm",),
    force: bool = False,
) -> dict[str, Any]:
    """Download trusted default model assets for service clients."""
    return download_selected_model_assets(models=models, force=force)


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


def _dashboard_fields_from_analysis(
    evidence: Evidence,
    analysis: AnalysisResult,
) -> dict[str, Any]:
    top_k_paths = list(analysis.top_k_paths)
    source_edges = _unique_source_edges(top_k_paths)
    correction_candidates = list(analysis.correction_candidates)
    linked_entities = list(analysis.linked_entities)
    return {
        "evidence_summary": _compact_evidence_summary(evidence),
        "linked_entities": linked_entities,
        "correction_candidates": correction_candidates,
        "top_k_paths": top_k_paths,
        "path_graph": _path_graph_from_paths(top_k_paths),
        "source_edge_provenance": source_edges,
        "review_targets": _review_targets(
            linked_entities=linked_entities,
            correction_candidates=correction_candidates,
            top_k_paths=top_k_paths,
            source_edges=source_edges,
        ),
    }


def _enrich_run_detail(detail: RunDetail) -> RunDetail:
    """Backfill derived dashboard fields for older persisted run manifests."""
    changed = False
    path_graph = detail.path_graph
    if not path_graph and detail.top_k_paths:
        path_graph = _path_graph_from_paths(detail.top_k_paths)
        changed = True
    review_targets = detail.review_targets
    if any("target_key" not in target for target in review_targets):
        review_targets = [
            {
                **target,
                "target_key": _review_target_key(
                    str(target.get("target_type", "target")),
                    target.get("target_id", ""),
                ),
            }
            for target in review_targets
        ]
        changed = True
    visual_evidence = normalize_visual_evidence_items(detail.visual_evidence)
    if visual_evidence != detail.visual_evidence:
        changed = True
    if not changed:
        return detail
    return detail.model_copy(
        update={
            "path_graph": path_graph,
            "review_targets": review_targets,
            "visual_evidence": visual_evidence,
        }
    )


def _load_visual_records(input_path: Path) -> list[dict[str, Any]]:
    try:
        return [dict(record) for record in load_adapter_records(input_path)]
    except (OSError, ValueError, json.JSONDecodeError):
        return []


def _enriched_case_rows(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for case in cases:
        row = dict(case)
        top_k_paths = _list_of_dicts(row.get("top_k_paths"))
        linked_entities = _list_of_dicts(row.get("linked_entities"))
        correction_candidates = _list_of_dicts(row.get("correction_candidates"))
        source_edges = _list_of_dicts(row.get("source_edge_provenance"))
        row["path_graph"] = _path_graph_from_paths(top_k_paths)
        row["review_targets"] = _review_targets(
            linked_entities=linked_entities,
            correction_candidates=correction_candidates,
            top_k_paths=top_k_paths,
            source_edges=source_edges,
        )
        enriched.append(row)
    return enriched


def _dashboard_fields_from_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    linked_entities: list[dict[str, Any]] = []
    correction_candidates: list[dict[str, Any]] = []
    top_k_paths: list[dict[str, Any]] = []
    source_edges_by_id: dict[str, dict[str, Any]] = {}
    evidence_summary: dict[str, Any] | None = None

    for case in cases:
        if evidence_summary is None and isinstance(case.get("generated_evidence"), dict):
            evidence_summary = dict(case["generated_evidence"])
        linked_entities.extend(_list_of_dicts(case.get("linked_entities")))
        correction_candidates.extend(_list_of_dicts(case.get("correction_candidates")))
        top_k_paths.extend(_list_of_dicts(case.get("top_k_paths")))
        for edge in _list_of_dicts(case.get("source_edge_provenance")):
            edge_id = str(edge.get("edge_id", ""))
            if edge_id:
                source_edges_by_id.setdefault(edge_id, edge)

    source_edges = [source_edges_by_id[edge_id] for edge_id in sorted(source_edges_by_id)]
    return {
        "evidence_summary": evidence_summary,
        "linked_entities": linked_entities,
        "correction_candidates": correction_candidates,
        "top_k_paths": top_k_paths,
        "path_graph": _path_graph_from_paths(top_k_paths),
        "source_edge_provenance": source_edges,
        "review_targets": _review_targets(
            linked_entities=linked_entities,
            correction_candidates=correction_candidates,
            top_k_paths=top_k_paths,
            source_edges=source_edges,
        ),
    }


def _compact_evidence_summary(evidence: Evidence) -> dict[str, Any]:
    return {
        "case_id": evidence.case_id,
        "dataset": evidence.dataset,
        "source": evidence.source,
        "object": evidence.object,
        "anomaly_type": evidence.anomaly_type,
        "location": evidence.location,
        "morphology": evidence.morphology,
        "severity": evidence.severity,
        "confidence": evidence.confidence,
        "observation_count": len(evidence.observations),
    }


def _unique_source_edges(top_k_paths: list[dict[str, Any]]) -> list[dict[str, Any]]:
    edges_by_id: dict[str, dict[str, Any]] = {}
    for path in top_k_paths:
        for edge in _list_of_dicts(path.get("source_edges")):
            edge_id = str(edge.get("edge_id", ""))
            if edge_id:
                edges_by_id.setdefault(edge_id, edge)
    return [edges_by_id[edge_id] for edge_id in sorted(edges_by_id)]


def _path_graph_from_paths(top_k_paths: list[dict[str, Any]]) -> dict[str, Any]:
    paths: list[dict[str, Any]] = []
    edge_ids: set[str] = set()
    node_ids: set[str] = set()
    for index, path in enumerate(top_k_paths):
        path_id = str(path.get("path_id") or f"path_{index}")
        nodes = [str(node) for node in path.get("nodes", []) if node is not None]
        node_names = [str(name) for name in path.get("node_names", []) if name is not None]
        relations = [
            str(relation)
            for relation in path.get("relations", [])
            if relation is not None
        ]
        source_edges = _list_of_dicts(path.get("source_edges"))
        graph_nodes = []
        for node_index, node_id in enumerate(nodes):
            node_ids.add(node_id)
            graph_nodes.append(
                {
                    "node_id": node_id,
                    "label": node_names[node_index] if node_index < len(node_names) else node_id,
                    "role": _path_node_role(node_index, len(nodes)),
                }
            )
        graph_edges = []
        for edge_index, relation in enumerate(relations):
            edge = source_edges[edge_index] if edge_index < len(source_edges) else {}
            edge_id = str(
                edge.get("edge_id")
                or _fallback_edge_id(nodes, edge_index, relation, path_id)
            )
            edge_ids.add(edge_id)
            graph_edges.append(
                {
                    "edge_id": edge_id,
                    "target_key": _review_target_key("edge", edge_id),
                    "source_node_id": nodes[edge_index] if edge_index < len(nodes) else "",
                    "target_node_id": nodes[edge_index + 1] if edge_index + 1 < len(nodes) else "",
                    "relation": relation,
                    "source": edge.get("source"),
                    "evidence": edge.get("evidence"),
                    "confidence": edge.get("confidence"),
                    "review_status": edge.get("review_status"),
                }
            )
        paths.append(
            {
                "path_id": path_id,
                "target_key": _review_target_key("path", path_id),
                "source_entity_id": path.get("source_entity_id"),
                "target_entity_id": path.get("target_entity_id"),
                "score": path.get("score"),
                "confidence": path.get("confidence"),
                "supporting_evidence": path.get("supporting_evidence", []),
                "nodes": graph_nodes,
                "edges": graph_edges,
            }
        )
    return {
        "paths": paths,
        "path_count": len(paths),
        "node_count": len(node_ids),
        "edge_count": len(edge_ids),
    }


def _path_node_role(node_index: int, node_count: int) -> str:
    if node_index == 0:
        return "source"
    if node_index == node_count - 1:
        return "target"
    return "intermediate"


def _fallback_edge_id(nodes: list[str], edge_index: int, relation: str, path_id: str) -> str:
    head = nodes[edge_index] if edge_index < len(nodes) else path_id
    tail = nodes[edge_index + 1] if edge_index + 1 < len(nodes) else f"step_{edge_index}"
    return f"{head}|{relation}|{tail}|derived"


def _review_targets(
    *,
    linked_entities: list[dict[str, Any]],
    correction_candidates: list[dict[str, Any]],
    top_k_paths: list[dict[str, Any]],
    source_edges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    for path in top_k_paths:
        path_id = path.get("path_id")
        if path_id:
            targets.append(
                {
                    "target_type": "path",
                    "target_id": str(path_id),
                    "target_key": _review_target_key("path", path_id),
                    "label": str(path.get("target_entity_id") or path_id),
                }
            )
    for edge in source_edges:
        edge_id = edge.get("edge_id")
        if edge_id:
            targets.append(
                {
                    "target_type": "edge",
                    "target_id": str(edge_id),
                    "target_key": _review_target_key("edge", edge_id),
                    "label": str(edge.get("relation") or edge_id),
                }
            )
    for link in linked_entities:
        link_id = link.get("link_id") or link.get("field")
        if link_id:
            targets.append(
                {
                    "target_type": "entity_link",
                    "target_id": str(link_id),
                    "target_key": _review_target_key("entity_link", link_id),
                    "label": str(link.get("selected_entity_id") or link_id),
                }
            )
    for candidate in correction_candidates:
        candidate_id = candidate.get("candidate_id")
        if candidate_id:
            targets.append(
                {
                    "target_type": "correction",
                    "target_id": str(candidate_id),
                    "target_key": _review_target_key("correction", candidate_id),
                    "label": str(candidate.get("suggested_value") or candidate_id),
                }
            )
    return targets


def _review_target_key(target_type: str, target_id: object) -> str:
    return f"{target_type}:{target_id}"


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _run_store_dirs(runs_dir: str | Path | None) -> list[Path]:
    if runs_dir is None:
        return [DEFAULT_RUNS_DIR, LEGACY_WEB_RUNS_DIR]
    primary = Path(runs_dir)
    if primary != DEFAULT_RUNS_DIR:
        return [primary]
    return [DEFAULT_RUNS_DIR, LEGACY_WEB_RUNS_DIR]


def _build_run_id(filename: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"run_{stamp}_{uuid.uuid4().hex[:8]}_{_safe_filename(Path(filename).stem)}"


def _safe_filename(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return token or "upload"


def _resolve_mvtec_checkpoint(
    checkpoint: str | Path | None = None,
    *,
    model_preset: str | None = None,
) -> Path:
    if checkpoint is not None:
        candidate = Path(checkpoint)
    else:
        candidate = _default_checkpoint_for_preset(model_preset)
    candidate = Path(
        os.environ.get(_checkpoint_env_for_preset(model_preset))
        or candidate
    )
    if (
        candidate.is_file()
        or is_amazon_patchcore_artifact_dir(candidate)
        or is_amazon_patchcore_artifact_collection(candidate)
    ):
        return candidate
    raise FileNotFoundError(
        f"MVTec checkpoint not found: {candidate}. Set {_checkpoint_env_for_preset(model_preset)} "
        "or place a trusted local checkpoint at the configured default path."
    )


def _resolve_mvtec_device() -> str:
    return os.environ.get("KGTRACEVIS_MVTEC_DEVICE", "CPU")


def _default_checkpoint_for_preset(model_preset: str | None) -> Path:
    if model_preset == "efficientad":
        return DEFAULT_MVTEC_EFFICIENTAD_CHECKPOINT
    if model_preset == "patchcore":
        return DEFAULT_MVTEC_PATCHCORE_CHECKPOINT
    return DEFAULT_MVTEC_UPLOAD_CHECKPOINT


def _checkpoint_env_for_preset(model_preset: str | None) -> str:
    if model_preset == "efficientad":
        return "KGTRACEVIS_MVTEC_EFFICIENTAD_CHECKPOINT"
    if model_preset == "patchcore":
        return "KGTRACEVIS_MVTEC_PATCHCORE_CHECKPOINT"
    return "KGTRACEVIS_MVTEC_STFPM_CHECKPOINT"


def _required_text(value: str | None, *, default: str) -> str:
    text = _optional_text(value)
    return text or default


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None
