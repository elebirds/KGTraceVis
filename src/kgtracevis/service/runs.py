"""Run-session helpers for uploaded sample processing."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from kgtracevis.adapters import evidence_from_mvtec_record
from kgtracevis.adapters.batch import load_records as load_adapter_records
from kgtracevis.core import KGTracePipeline
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
    resolve_mvtec_model_selection,
)
from kgtracevis.schema.evidence_schema import DatasetName
from kgtracevis.schema.validators import load_evidence_json
from kgtracevis.service.run_enrichment import (
    dashboard_fields_from_analysis,
    dashboard_fields_from_cases,
    enrich_run_detail,
    enriched_case_rows,
    evidence_with_analysis,
    list_of_dicts,
)
from kgtracevis.service.run_models import RunDetail, RunSummary, UploadMode, WorkflowStep
from kgtracevis.service.run_steps import (
    workflow_steps_for_case,
    workflow_steps_for_image_case,
)
from kgtracevis.service.run_store import (
    build_run_id,
    configure_run_store_for_testing,
    run_store,
)
from kgtracevis.service.visual_evidence import (
    build_visual_evidence_artifacts,
)
from kgtracevis.workflows.reasoning_registry import default_reasoning_registry
from kgtracevis.workflows.root_cause_provider_selection import build_pipeline

DEFAULT_RUNS_DIR = Path("runs/rootlens_sessions")
DEFAULT_MVTEC_UPLOAD_CHECKPOINT = DEFAULT_MVTEC_PATCHCORE_CHECKPOINT

__all__ = [
    "RunDetail",
    "RunSummary",
    "WorkflowStep",
    "configure_run_store_for_testing",
    "create_run_from_upload",
    "download_model_assets",
    "get_run_artifact_path",
    "get_run_detail",
    "list_runs",
    "mvtec_model_presets",
    "parse_dataset_override",
    "parse_upload_mode",
    "workflow_steps_for_case",
]


def list_runs(
    runs_dir: str | Path | None = None,
) -> list[RunSummary]:
    """Return persisted uploaded-sample runs, newest first."""
    _ = runs_dir
    store = run_store()
    if store is None:
        return []
    return [RunSummary.model_validate(item) for item in store.list_runs()]


def get_run_detail(
    run_id: str,
    *,
    runs_dir: str | Path | None = None,
) -> RunDetail:
    """Load one persisted run detail by ID."""
    _ = runs_dir
    store = run_store()
    if store is None:
        raise ValueError("Postgres run store is not configured")
    return enrich_run_detail(RunDetail.model_validate(store.get_run_detail(run_id)))


def get_run_artifact_path(
    run_id: str,
    artifact_name: str,
    *,
    runs_dir: str | Path | None = None,
) -> Path:
    """Return a safe run artifact path by filename."""
    if artifact_name != Path(artifact_name).name:
        raise ValueError("artifact name must not contain path separators")
    _ = runs_dir
    store = run_store()
    if store is None:
        raise ValueError("Postgres run store is not configured")
    artifact_path = Path(store.get_artifact_path(run_id, artifact_name))
    detail = get_run_detail(run_id)
    artifact_root = Path(detail.run.run_dir) / "artifacts"
    try:
        artifact_path.resolve().relative_to(artifact_root.resolve())
    except ValueError as exc:
        raise ValueError(f"unknown run artifact: {artifact_name}") from exc
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
    reasoning_profile_id: str | None = None,
    runs_dir: str | Path | None = None,
    pipeline: KGTracePipeline | None = None,
) -> RunDetail:
    """Persist one uploaded sample and run the applicable pipeline path."""
    if top_k < 1:
        raise ValueError("top_k must be >= 1")

    base_dir = Path(runs_dir or DEFAULT_RUNS_DIR)
    run_id = build_run_id()
    run_dir = base_dir / run_id
    input_dir = run_dir / "input"
    output_dir = run_dir / "output"
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    source_name = _safe_filename(filename)
    input_path = input_dir / source_name
    input_path.write_bytes(content)

    created_at = datetime.now(timezone.utc).isoformat()
    if pipeline is not None and reasoning_profile_id is not None:
        raise ValueError("pass either pipeline or reasoning_profile_id, not both")
    if mode == "evidence":
        detail = _run_evidence_upload(
            run_id=run_id,
            created_at=created_at,
            input_path=input_path,
            source_filename=source_name,
            top_k=top_k,
            pipeline=pipeline or build_pipeline(reasoning_profile_id=reasoning_profile_id),
        )
    elif mode == "image":
        if dataset is not None and dataset != "mvtec":
            raise ValueError("image upload mode only supports mvtec")
        if reasoning_profile_id is not None:
            default_reasoning_registry().validate_profile_for_dataset(
                reasoning_profile_id,
                "mvtec",
            )
        detail = _run_mvtec_image_upload(
            run_id=run_id,
            created_at=created_at,
            input_path=input_path,
            source_filename=source_name,
            object_name=_required_text(object_name, default="capsule"),
            defect_type=_optional_text(defect_type),
            model_preset=model_preset,
            top_k=top_k,
            pipeline=pipeline or build_pipeline(reasoning_profile_id=reasoning_profile_id),
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
            pipeline=pipeline,
            reasoning_profile_id=reasoning_profile_id,
            output_dir=output_dir / "adapter_pipeline",
        )
    else:
        raise ValueError("upload mode must be evidence, records, or image")

    store = run_store()
    if store is None:
        raise ValueError("Postgres run store is not configured")
    saved_detail = RunDetail.model_validate(store.save_run(detail))
    return enrich_run_detail(saved_detail)


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


def _run_store() -> Any:
    """Backward-compatible private run-store accessor."""
    return run_store()


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
        **dashboard_fields_from_analysis(evidence, analysis),
        evidence_with_analysis=evidence_with_analysis(evidence, analysis),
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
    pipeline: KGTracePipeline | None,
    reasoning_profile_id: str | None,
    output_dir: Path,
) -> RunDetail:
    output = run_adapter_pipeline(
        input_path,
        output_dir,
        dataset=dataset,
        top_k=top_k,
        overwrite=True,
        pipeline=pipeline,
        reasoning_profile_id=reasoning_profile_id,
    )
    summary = output.summary
    records = _load_visual_records(input_path)
    summary_cases = list_of_dicts(summary.get("cases"))
    case_rows = enriched_case_rows(summary_cases)
    inferred_dataset = None
    if case_rows:
        first_case = case_rows[0]
        if isinstance(first_case, dict):
            inferred_dataset = first_case.get("dataset")
    dataset_name = str(
        dataset
        or inferred_dataset
        or summary.get("input", {}).get("dataset_override")
        or "mvtec"
    )
    if dataset_name not in {"mvtec", "tep", "wafer"}:
        dataset_name = "mvtec"
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
        **dashboard_fields_from_cases(case_rows),
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
        **dashboard_fields_from_analysis(evidence, analysis),
        evidence_with_analysis=evidence_with_analysis(evidence, analysis),
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
    models: tuple[ModelAsset, ...] = ("mvtec-patchcore",),
    force: bool = False,
) -> dict[str, Any]:
    """Download trusted default model assets for service clients."""
    return download_selected_model_assets(models=models, force=force)


def _load_visual_records(input_path: Path) -> list[dict[str, Any]]:
    try:
        return [dict(record) for record in load_adapter_records(input_path)]
    except (OSError, ValueError, json.JSONDecodeError):
        return []


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
