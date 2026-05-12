"""One-command calibrated MVTec Amazon PatchCore pipeline orchestration."""

from __future__ import annotations

import json
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kgtracevis.experiments.adapter_pipeline import AdapterPipelineOutput, run_adapter_pipeline
from kgtracevis.experiments.mvtec_patchcore import (
    CLAIM_BOUNDARY,
    build_ds_mvtec_subset_input,
    summarize_records,
)
from kgtracevis.producers import (
    AMAZON_PATCHCORE_BACKEND,
    AmazonPatchCoreObjectRouter,
    MVTecAnomalyPredictor,
    write_jsonl_records,
)
from kgtracevis.producers.mvtec_calibration import load_mvtec_threshold_config
from kgtracevis.producers.mvtec_records import build_mvtec_records

PIPELINE_SUMMARY_FILENAME = "mvtec_calibrated_pipeline_summary.json"


@dataclass(frozen=True)
class MVTecCalibratedPipelineConfig:
    """Configuration for a calibrated official Amazon PatchCore MVTec pipeline run."""

    dataset_root: Path
    artifact_root: Path
    threshold_config: Path
    output_root: Path
    object_names: Sequence[str] | None = None
    max_objects: int | None = None
    max_good: int = 1
    max_defect_per_label: int = 1
    top_k: int = 5
    device: str = "cpu"
    overwrite: bool = False


@dataclass(frozen=True)
class MVTecCalibratedPipelineOutput:
    """Paths and summary produced by a calibrated MVTec pipeline run."""

    summary_path: Path
    records_path: Path
    adapter_summary_path: Path
    adapter_table_path: Path
    summary: dict[str, Any]


def run_mvtec_calibrated_pipeline(
    config: MVTecCalibratedPipelineConfig,
    *,
    predictor: MVTecAnomalyPredictor | None = None,
) -> MVTecCalibratedPipelineOutput:
    """Run calibrated PatchCore producer records through Evidence/KGTracePipeline."""
    if config.top_k < 1:
        raise ValueError("top_k must be >= 1")
    output_root = config.output_root
    if output_root.exists() and config.overwrite:
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    input_root, manifest = build_ds_mvtec_subset_input(
        dataset_root=config.dataset_root,
        output_root=output_root / "input",
        object_names=config.object_names,
        max_objects=config.max_objects,
        max_good=config.max_good,
        max_defect_per_label=config.max_defect_per_label,
    )
    active_predictor = predictor or AmazonPatchCoreObjectRouter(
        checkpoint_root=config.artifact_root,
        device=config.device,
    )
    threshold_config = load_mvtec_threshold_config(config.threshold_config)
    records = build_mvtec_records(
        input_root,
        active_predictor,
        output_dir=output_root / "records",
        model_backend=AMAZON_PATCHCORE_BACKEND,
        checkpoint=config.artifact_root,
        include_good=True,
        threshold_config=threshold_config,
    )
    records_path = write_jsonl_records(
        records,
        output_root / "mvtec_calibrated_records.jsonl",
        overwrite=True,
    )
    adapter_output = run_adapter_pipeline(
        records_path,
        output_root / "adapter_pipeline",
        dataset="mvtec",
        top_k=config.top_k,
        overwrite=True,
    )
    summary = _pipeline_summary(
        config=config,
        input_root=input_root,
        manifest=manifest,
        records_path=records_path,
        records=records,
        adapter_output=adapter_output,
    )
    summary_path = output_root / PIPELINE_SUMMARY_FILENAME
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return MVTecCalibratedPipelineOutput(
        summary_path=summary_path,
        records_path=records_path,
        adapter_summary_path=adapter_output.summary_path,
        adapter_table_path=adapter_output.table_path,
        summary=summary,
    )


def _pipeline_summary(
    *,
    config: MVTecCalibratedPipelineConfig,
    input_root: Path,
    manifest: list[dict[str, Any]],
    records_path: Path,
    records: list[dict[str, Any]],
    adapter_output: AdapterPipelineOutput,
) -> dict[str, Any]:
    sanity = summarize_records(records)
    return {
        "artifact_type": "mvtec_calibrated_patchcore_pipeline_v0",
        "dataset_root": str(config.dataset_root),
        "artifact_root": str(config.artifact_root),
        "threshold_config": str(config.threshold_config),
        "output_root": str(config.output_root),
        "input_root": str(input_root),
        "records_path": str(records_path),
        "adapter_summary": str(adapter_output.summary_path),
        "adapter_table": str(adapter_output.table_path),
        "record_count": len(records),
        "adapter_case_count": adapter_output.summary["case_count"],
        "manifest_count": len(manifest),
        "object_count": len({record.get("object") for record in records}),
        "objects": sorted({str(record.get("object")) for record in records}),
        "sampling": {
            "objects": list(config.object_names) if config.object_names is not None else None,
            "max_objects": config.max_objects,
            "max_good": config.max_good,
            "max_defect_per_label": config.max_defect_per_label,
        },
        "pipeline": {
            "model_backend": AMAZON_PATCHCORE_BACKEND,
            "device": config.device,
            "top_k": config.top_k,
        },
        "sanity": sanity,
        "claim_boundary": (
            f"{CLAIM_BOUNDARY} Calibrated thresholds are supervised evidence-generation "
            "artifacts, not unsupervised MVTec benchmark results."
        ),
    }
