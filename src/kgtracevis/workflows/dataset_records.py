"""Workflow for building producer-output dataset records."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from kgtracevis.producers import (
    AMAZON_PATCHCORE_BACKEND,
    ANOMALIB_ENGINE_BACKEND,
    ANOMALIB_OPENVINO_BACKEND,
    ANOMALIB_TORCH_BACKEND,
    SKLEARN_BACKEND,
    TORCH_RESNET_BACKEND,
    AmazonPatchCoreBackend,
    AmazonPatchCoreObjectRouter,
    AnomalibMVTecBackend,
    MVTecAnomalyPredictor,
    SklearnWM811KBackend,
    TorchWM811KBackend,
    WM811KClassifier,
    write_jsonl_records,
)
from kgtracevis.producers.mvtec_calibration import load_mvtec_threshold_config
from kgtracevis.producers.mvtec_records import build_mvtec_records
from kgtracevis.producers.wm811k_records import build_wm811k_records

MVTEC_BACKENDS = (
    ANOMALIB_ENGINE_BACKEND,
    ANOMALIB_TORCH_BACKEND,
    ANOMALIB_OPENVINO_BACKEND,
    AMAZON_PATCHCORE_BACKEND,
)
WM811K_BACKENDS = (SKLEARN_BACKEND, TORCH_RESNET_BACKEND)
MODEL_BACKENDS = (*MVTEC_BACKENDS, *WM811K_BACKENDS)

DatasetRecordName = Literal["mvtec", "wm811k", "wafer"]


@dataclass(frozen=True)
class DatasetRecordBuildConfig:
    """Configuration for producer-output record generation."""

    dataset: DatasetRecordName
    output_jsonl: Path
    model_backend: str
    input_root: Path | None = None
    input: Path | None = None
    checkpoint: Path | None = None
    model_source_repo: str | None = None
    model_source_file: str | None = None
    object_checkpoint_root: Path | None = None
    threshold: float = 0.5
    threshold_config: Path | None = None
    max_cases: int | None = None
    max_per_label: int | None = None
    seed: int | None = None
    device: str | None = None
    include_good: bool = False
    overwrite: bool = False


@dataclass(frozen=True)
class DatasetRecordBuildResult:
    """Result of a dataset-record build workflow."""

    output_path: Path
    artifact_dir: Path
    records: list[Mapping[str, Any]]
    summary: dict[str, Any]


def build_dataset_records(config: DatasetRecordBuildConfig) -> DatasetRecordBuildResult:
    """Build normalized producer-output records for adapter ingestion."""
    artifact_dir = config.output_jsonl.with_suffix("")

    if config.dataset == "mvtec":
        records = _build_mvtec_dataset_records(config, artifact_dir=artifact_dir)
    else:
        records = _build_wafer_dataset_records(config, artifact_dir=artifact_dir)

    output_path = write_jsonl_records(
        records,
        config.output_jsonl,
        overwrite=config.overwrite,
    )
    summary = {
        "dataset": config.dataset,
        "record_count": len(records),
        "labels": dict(sorted(_label_counts(records).items())),
        "output_jsonl": str(output_path),
        "artifact_dir": str(artifact_dir),
        "claim_boundary": (
            "producer records contain observed model outputs and native labels only; "
            "root causes and ranked paths are KGTracePipeline runtime outputs"
        ),
    }
    return DatasetRecordBuildResult(
        output_path=output_path,
        artifact_dir=artifact_dir,
        records=records,
        summary=summary,
    )


def build_mvtec_predictor(
    *,
    model_backend: str,
    checkpoint: Path | None = None,
    object_checkpoint_root: Path | None = None,
    device: str | None = None,
) -> MVTecAnomalyPredictor:
    """Return the selected MVTec predictor backend."""
    if object_checkpoint_root is not None and model_backend != AMAZON_PATCHCORE_BACKEND:
        raise ValueError(
            "--object-checkpoint-root is only supported with "
            f"--model-backend {AMAZON_PATCHCORE_BACKEND}"
        )
    if checkpoint is not None and object_checkpoint_root is not None:
        raise ValueError("--checkpoint and --object-checkpoint-root cannot both be set")
    if model_backend in {
        ANOMALIB_ENGINE_BACKEND,
        ANOMALIB_TORCH_BACKEND,
        ANOMALIB_OPENVINO_BACKEND,
    }:
        return AnomalibMVTecBackend(
            backend=model_backend,
            checkpoint=checkpoint,
            device=device,
        )
    if model_backend == AMAZON_PATCHCORE_BACKEND:
        if object_checkpoint_root is not None:
            return AmazonPatchCoreObjectRouter(
                checkpoint_root=object_checkpoint_root,
                device=device,
            )
        return AmazonPatchCoreBackend(
            checkpoint=checkpoint,
            device=device,
        )
    raise ValueError(
        f"unsupported MVTec --model-backend {model_backend!r}; expected one of {MVTEC_BACKENDS}"
    )


def build_wm811k_classifier(
    *,
    model_backend: str,
    checkpoint: Path | None = None,
    device: str | None = None,
    model_source_repo: str | None = None,
    model_source_file: str | None = None,
) -> WM811KClassifier:
    """Return the selected WM811K classifier backend."""
    if model_backend == SKLEARN_BACKEND:
        return SklearnWM811KBackend(checkpoint=checkpoint)
    if model_backend == TORCH_RESNET_BACKEND:
        return TorchWM811KBackend(
            checkpoint=checkpoint,
            device=device,
            model_source=model_source_repo,
            model_file=model_source_file,
        )
    raise ValueError(
        f"unsupported WM811K --model-backend {model_backend!r}; expected one of {WM811K_BACKENDS}"
    )


def _build_mvtec_dataset_records(
    config: DatasetRecordBuildConfig,
    *,
    artifact_dir: Path,
) -> list[Mapping[str, Any]]:
    if config.input_root is None:
        raise ValueError("--input-root is required for --dataset mvtec")
    if config.model_backend not in MVTEC_BACKENDS:
        raise ValueError(
            "--model-backend for --dataset mvtec must be one of "
            f"{MVTEC_BACKENDS}"
        )
    predictor = build_mvtec_predictor(
        model_backend=config.model_backend,
        checkpoint=config.checkpoint,
        object_checkpoint_root=config.object_checkpoint_root,
        device=config.device,
    )
    checkpoint_for_records = config.object_checkpoint_root or config.checkpoint
    return build_mvtec_records(
        config.input_root,
        predictor,
        output_dir=artifact_dir,
        model_backend=config.model_backend,
        checkpoint=checkpoint_for_records,
        threshold=config.threshold,
        max_cases=config.max_cases,
        max_per_label=config.max_per_label,
        seed=config.seed,
        include_good=config.include_good,
        threshold_config=load_mvtec_threshold_config(config.threshold_config),
    )


def _build_wafer_dataset_records(
    config: DatasetRecordBuildConfig,
    *,
    artifact_dir: Path,
) -> list[Mapping[str, Any]]:
    if config.input is None:
        raise ValueError("--input is required for --dataset wm811k/wafer")
    if config.model_backend not in WM811K_BACKENDS:
        raise ValueError(
            "--model-backend for --dataset wm811k/wafer must be one of "
            f"{WM811K_BACKENDS}"
        )
    classifier = build_wm811k_classifier(
        model_backend=config.model_backend,
        checkpoint=config.checkpoint,
        device=config.device,
        model_source_repo=config.model_source_repo,
        model_source_file=config.model_source_file,
    )
    return build_wm811k_records(
        config.input,
        classifier,
        output_dir=artifact_dir,
        model_backend=config.model_backend,
        checkpoint=config.checkpoint,
        threshold=config.threshold,
        max_cases=config.max_cases,
        max_per_label=config.max_per_label,
        seed=config.seed,
    )


def _label_counts(records: Sequence[Mapping[str, Any]]) -> Counter[str]:
    return Counter(
        str(record.get("defect_type") or record.get("failure_pattern") or "unknown")
        for record in records
    )
