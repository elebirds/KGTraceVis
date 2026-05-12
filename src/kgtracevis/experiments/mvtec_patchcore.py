"""Reusable DS-MVTec PatchCore experiment helpers."""

from __future__ import annotations

import csv
import json
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any

import numpy as np

from kgtracevis.experiments.adapter_pipeline import run_adapter_pipeline
from kgtracevis.producers import ANOMALIB_ENGINE_BACKEND, AnomalibMVTecBackend, write_jsonl_records
from kgtracevis.producers.mvtec_records import build_mvtec_records

IMAGE_SUFFIXES = {".bmp", ".jpg", ".jpeg", ".png", ".tif", ".tiff"}
OBJECT_SUMMARY_FILENAME = "summary.json"
BATCH_SUMMARY_FILENAME = "batch_summary.json"
BATCH_TABLE_FILENAME = "batch_summary.csv"
CLAIM_BOUNDARY = (
    "PatchCore outputs are anomaly detection/localization evidence. "
    "Folder labels are source labels, not model-inferred semantic classes."
)


@dataclass(frozen=True)
class PatchCoreObjectRunConfig:
    """Configuration for one target-domain DS-MVTec PatchCore fit/eval run."""

    object_dir: Path
    output_root: Path
    name: str | None = None
    normal_label: str = "good"
    fit_labels: Sequence[str] | None = None
    eval_labels: Sequence[str] | None = None
    max_eval_per_label: int = 1
    top_k: int = 5
    device: str = "cpu"
    overwrite: bool = False


def run_patchcore_object(config: PatchCoreObjectRunConfig) -> dict[str, Any]:
    """Fit PatchCore for one DS-MVTec object and run records through KGTracePipeline."""
    object_dir = config.object_dir
    if not object_dir.is_dir():
        raise FileNotFoundError(f"object directory does not exist: {object_dir}")
    if config.max_eval_per_label < 1:
        raise ValueError("max_eval_per_label must be >= 1")
    if config.top_k < 1:
        raise ValueError("top_k must be >= 1")

    output_root = config.output_root
    if output_root.exists() and config.overwrite:
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    name = config.name or object_dir.name
    fit_labels = selected_labels(
        object_dir,
        normal_label=config.normal_label,
        requested=config.fit_labels,
    )
    eval_labels = selected_labels(
        object_dir,
        normal_label=config.normal_label,
        requested=config.eval_labels,
    )
    checkpoint = fit_patchcore(
        object_dir=object_dir,
        output_root=output_root / "fit",
        name=name,
        normal_label=config.normal_label,
        labels=fit_labels,
        device=config.device,
    )

    input_root = build_mvtec_like_eval_root(
        object_dir=object_dir,
        output_root=output_root / "eval_input",
        object_name=object_dir.name,
        normal_label=config.normal_label,
        labels=eval_labels,
        max_per_label=config.max_eval_per_label,
    )
    predictor = AnomalibMVTecBackend(
        backend=ANOMALIB_ENGINE_BACKEND,
        checkpoint=checkpoint,
        device=config.device,
    )
    records = build_mvtec_records(
        input_root,
        predictor,
        output_dir=output_root / "records",
        model_backend=ANOMALIB_ENGINE_BACKEND,
        checkpoint=checkpoint,
        include_good=True,
    )
    records_path = write_jsonl_records(
        records,
        output_root / "mvtec_patchcore_records.jsonl",
        overwrite=config.overwrite,
    )
    adapter_output = run_adapter_pipeline(
        records_path,
        output_root / "adapter_pipeline",
        dataset="mvtec",
        top_k=config.top_k,
        overwrite=True,
    )

    summary = {
        "artifact_type": "mvtec_patchcore_fit_run_v0",
        "object": object_dir.name,
        "object_dir": str(object_dir),
        "output_root": str(output_root),
        "checkpoint": str(checkpoint),
        "records_path": str(records_path),
        "adapter_summary": str(adapter_output.summary_path),
        "adapter_table": str(adapter_output.table_path),
        "record_count": len(records),
        "fit_labels": fit_labels,
        "eval_labels": eval_labels,
        "sanity": summarize_records(records),
        "claim_boundary": CLAIM_BOUNDARY,
    }
    summary_path = output_root / OBJECT_SUMMARY_FILENAME
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def discover_ds_mvtec_object_dirs(
    dataset_root: str | Path,
    *,
    object_names: Sequence[str] | None = None,
    max_objects: int | None = None,
    normal_label: str = "good",
) -> list[Path]:
    """Return DS-MVTec object directories that contain ``image/<normal_label>``."""
    if max_objects is not None and max_objects < 1:
        raise ValueError("max_objects must be >= 1 when provided")

    root = Path(dataset_root)
    if (root / "DS-MVTec").is_dir():
        root = root / "DS-MVTec"
    if not root.is_dir():
        raise FileNotFoundError(f"dataset root does not exist: {root}")

    if object_names:
        ordered_names = list(dict.fromkeys(object_names))
        object_dirs = [root / name for name in ordered_names]
    else:
        object_dirs = sorted(path for path in root.iterdir() if path.is_dir())

    valid_dirs: list[Path] = []
    for object_dir in object_dirs:
        if not (object_dir / "image" / normal_label).is_dir():
            if object_names:
                raise FileNotFoundError(
                    f"DS-MVTec object is missing image/{normal_label}: {object_dir}"
                )
            continue
        valid_dirs.append(object_dir)
        if max_objects is not None and len(valid_dirs) >= max_objects:
            break
    return valid_dirs


def fit_patchcore(
    *,
    object_dir: Path,
    output_root: Path,
    name: str,
    normal_label: str,
    labels: Sequence[str],
    device: str,
) -> Path:
    """Fit a PatchCore checkpoint on one target-domain DS-MVTec object."""
    from anomalib.data import Folder
    from anomalib.engine import Engine
    from anomalib.models import Patchcore

    image_dir = object_dir / "image"
    mask_dir = object_dir / "mask"
    normal_dir = image_dir / normal_label
    if not normal_dir.is_dir():
        raise FileNotFoundError(f"normal image directory does not exist: {normal_dir}")
    abnormal_dirs = [image_dir / label for label in labels if label != normal_label]
    missing_abnormal = [path for path in abnormal_dirs if not path.is_dir()]
    if missing_abnormal:
        raise FileNotFoundError(f"missing abnormal image directories: {missing_abnormal}")
    mask_dirs = [mask_dir / label for label in labels if (mask_dir / label).is_dir()]

    datamodule = Folder(
        name=name,
        root=object_dir,
        normal_dir=normal_dir,
        normal_test_dir=normal_dir,
        abnormal_dir=abnormal_dirs,
        mask_dir=mask_dirs or None,
        train_batch_size=4,
        eval_batch_size=1,
        num_workers=0,
        seed=42,
    )
    engine = Engine(
        default_root_dir=output_root,
        accelerator=accelerator_for_device(device),
        devices=1,
        logger=False,
        enable_checkpointing=True,
    )
    engine.fit(model=Patchcore(), datamodule=datamodule)
    checkpoints = sorted(output_root.rglob("*.ckpt"))
    if not checkpoints:
        raise FileNotFoundError(
            f"PatchCore fit completed but no checkpoint was found under {output_root}"
        )
    return checkpoints[-1]


def build_mvtec_like_eval_root(
    *,
    object_dir: Path,
    output_root: Path,
    object_name: str,
    normal_label: str,
    labels: Sequence[str],
    max_per_label: int,
) -> Path:
    """Create a symlinked MVTec-like eval root from a DS-MVTec object directory."""
    if output_root.exists():
        shutil.rmtree(output_root)
    image_dir = object_dir / "image"
    mask_dir = object_dir / "mask"
    input_root = output_root / "input_root"
    for label in [normal_label, *[item for item in labels if item != normal_label]]:
        images = image_files(image_dir / label)[:max_per_label]
        for image_path in images:
            destination = input_root / object_name / "test" / label / image_path.name
            symlink_or_copy(image_path, destination)
            if label == normal_label:
                continue
            mask_path = mask_for_image(mask_dir / label, image_path)
            if mask_path is not None:
                symlink_or_copy(
                    mask_path,
                    input_root / object_name / "ground_truth" / label / mask_path.name,
                )
    return input_root


def selected_labels(
    object_dir: Path,
    *,
    normal_label: str,
    requested: Sequence[str] | None,
) -> list[str]:
    """Return requested labels or all non-normal labels under ``image/``."""
    image_dir = object_dir / "image"
    if requested:
        return list(dict.fromkeys(requested))
    return sorted(
        path.name for path in image_dir.iterdir() if path.is_dir() and path.name != normal_label
    )


def image_files(path: Path) -> list[Path]:
    """Return sorted image files in one DS-MVTec label directory."""
    if not path.is_dir():
        raise FileNotFoundError(f"image label directory does not exist: {path}")
    return sorted(
        child
        for child in path.iterdir()
        if child.is_file() and child.suffix.lower() in IMAGE_SUFFIXES
    )


def mask_for_image(mask_dir: Path, image_path: Path) -> Path | None:
    """Return the matching DS-MVTec mask path for an image, if present."""
    for suffix in sorted(IMAGE_SUFFIXES):
        for stem in (f"{image_path.stem}_mask", image_path.stem):
            candidate = mask_dir / f"{stem}{suffix}"
            if candidate.is_file():
                return candidate
    return None


def symlink_or_copy(source: Path, destination: Path) -> None:
    """Create a symlink, falling back to copy on filesystems that reject symlinks."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        destination.unlink()
    resolved_source = source.resolve()
    try:
        destination.symlink_to(resolved_source)
    except OSError:
        shutil.copy2(resolved_source, destination)


def summarize_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Return compact detection, score, mask-area, and optional IoU sanity metrics."""
    rows: list[dict[str, Any]] = []
    scores: list[float] = []
    mask_areas: list[float] = []
    ious: list[float] = []
    defect_total = 0
    defect_anomalous = 0
    defect_normal = 0
    good_total = 0
    good_anomalous = 0
    good_normal = 0

    for record in records:
        label = _text_or_none(record.get("defect_type")) or "unknown"
        score = _float_or_none(record.get("score"))
        raw_mask_stats = record.get("mask_stats")
        mask_stats = raw_mask_stats if isinstance(raw_mask_stats, Mapping) else {}
        mask_area = _float_or_none(mask_stats.get("area_ratio")) if mask_stats else None
        pred_label = _prediction_label(record)
        is_anomalous = _is_anomalous_prediction(pred_label, score=score)
        iou = _record_mask_iou(record)

        if label.lower() == "good":
            good_total += 1
            if is_anomalous is True:
                good_anomalous += 1
            elif is_anomalous is False:
                good_normal += 1
        else:
            defect_total += 1
            if is_anomalous is True:
                defect_anomalous += 1
            elif is_anomalous is False:
                defect_normal += 1

        if score is not None:
            scores.append(score)
        if mask_area is not None:
            mask_areas.append(mask_area)
        if iou is not None:
            ious.append(iou)

        rows.append(
            {
                "case_id": record.get("case_id"),
                "label": label,
                "score": score,
                "pred_label": pred_label,
                "is_anomalous": is_anomalous,
                "mask_area_ratio": mask_area,
                "mask_iou": iou,
            }
        )

    return {
        "records": rows,
        "record_count": len(records),
        "defect_count": defect_total,
        "good_count": good_total,
        "defect_pred_anomalous_count": defect_anomalous,
        "defect_pred_normal_count": defect_normal,
        "good_pred_anomalous_count": good_anomalous,
        "good_pred_normal_count": good_normal,
        "score_min": min(scores) if scores else None,
        "score_max": max(scores) if scores else None,
        "mask_area_min": min(mask_areas) if mask_areas else None,
        "mask_area_max": max(mask_areas) if mask_areas else None,
        "mean_iou": mean(ious) if ious else None,
        "iou_count": len(ious),
    }


def batch_row_from_object_summary(
    *,
    object_name: str,
    status: str,
    object_summary_path: Path | None = None,
    object_summary: Mapping[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """Build one per-object batch table row from a run summary or failure."""
    sanity = object_summary.get("sanity", {}) if object_summary else {}
    if not isinstance(sanity, Mapping):
        sanity = {}
    record_count = sanity.get(
        "record_count",
        object_summary.get("record_count") if object_summary else 0,
    )
    return {
        "object": object_name,
        "status": status,
        "record_count": record_count,
        "defect_count": sanity.get("defect_count"),
        "defect_pred_anomalous_count": sanity.get("defect_pred_anomalous_count"),
        "defect_pred_normal_count": sanity.get("defect_pred_normal_count"),
        "good_count": sanity.get("good_count"),
        "good_pred_anomalous_count": sanity.get("good_pred_anomalous_count"),
        "good_pred_normal_count": sanity.get("good_pred_normal_count"),
        "score_min": sanity.get("score_min"),
        "score_max": sanity.get("score_max"),
        "mask_area_min": sanity.get("mask_area_min"),
        "mask_area_max": sanity.get("mask_area_max"),
        "mean_iou": sanity.get("mean_iou"),
        "iou_count": sanity.get("iou_count"),
        "object_summary": str(object_summary_path) if object_summary_path is not None else None,
        "records_path": object_summary.get("records_path") if object_summary else None,
        "adapter_summary": object_summary.get("adapter_summary") if object_summary else None,
        "adapter_table": object_summary.get("adapter_table") if object_summary else None,
        "checkpoint": object_summary.get("checkpoint") if object_summary else None,
        "error": error,
    }


def write_batch_outputs(
    *,
    output_root: Path,
    dataset_root: Path,
    rows: Sequence[Mapping[str, Any]],
    args: Mapping[str, Any],
) -> tuple[Path, Path]:
    """Write batch summary JSON and CSV and return their paths."""
    summary = {
        "artifact_type": "mvtec_patchcore_batch_v0",
        "dataset_root": str(dataset_root),
        "output_root": str(output_root),
        "object_count": len(rows),
        "success_count": sum(1 for row in rows if row.get("status") == "ok"),
        "failed_count": sum(1 for row in rows if row.get("status") == "failed"),
        "skipped_count": sum(1 for row in rows if str(row.get("status", "")).startswith("skipped")),
        "objects": list(rows),
        "args": dict(args),
        "claim_boundary": CLAIM_BOUNDARY,
    }
    summary_path = output_root / BATCH_SUMMARY_FILENAME
    table_path = output_root / BATCH_TABLE_FILENAME
    output_root.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_batch_table(rows, table_path)
    return summary_path, table_path


def write_batch_table(rows: Sequence[Mapping[str, Any]], output_path: str | Path) -> Path:
    """Write a compact per-object DS-MVTec PatchCore summary CSV."""
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "object",
        "status",
        "record_count",
        "defect_count",
        "defect_pred_anomalous_count",
        "defect_pred_normal_count",
        "good_count",
        "good_pred_anomalous_count",
        "good_pred_normal_count",
        "score_min",
        "score_max",
        "mask_area_min",
        "mask_area_max",
        "mean_iou",
        "iou_count",
        "object_summary",
        "records_path",
        "adapter_summary",
        "adapter_table",
        "checkpoint",
        "error",
    ]
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name) for name in fieldnames})
    return destination


def load_summary(path: str | Path) -> dict[str, Any]:
    """Load a JSON summary file."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def accelerator_for_device(device: str) -> str:
    """Return the Anomalib accelerator name for a CLI device value."""
    if device == "auto":
        return "auto"
    if device == "gpu":
        return "gpu"
    return device


def _record_mask_iou(record: Mapping[str, Any]) -> float | None:
    mask_path = _path_or_none(record.get("mask_path"))
    gt_mask_path = _path_or_none(record.get("gt_mask_path"))
    if mask_path is None or gt_mask_path is None:
        return None
    try:
        predicted = _load_predicted_mask(mask_path)
        gt_mask = _load_gt_mask(gt_mask_path, shape=predicted.shape)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None
    return _binary_iou(predicted, gt_mask)


def _load_predicted_mask(path: Path) -> np.ndarray:
    data = json.loads(path.read_text(encoding="utf-8"))
    array = np.asarray(data)
    if array.ndim > 2:
        array = np.squeeze(array)
    if array.ndim != 2:
        raise ValueError(f"predicted mask must be 2D: {path}")
    return array.astype(float) > 0


def _load_gt_mask(path: Path, *, shape: tuple[int, int]) -> np.ndarray:
    from PIL import Image

    image = Image.open(path).convert("L")
    target_height, target_width = shape
    if image.size != (target_width, target_height):
        image = image.resize((target_width, target_height), Image.Resampling.NEAREST)
    return np.asarray(image) > 0


def _binary_iou(predicted: np.ndarray, target: np.ndarray) -> float:
    intersection = np.logical_and(predicted, target).sum()
    union = np.logical_or(predicted, target).sum()
    if union == 0:
        return 1.0
    return float(intersection / union)


def _prediction_label(record: Mapping[str, Any]) -> Any:
    raw_detector = record.get("detector")
    detector: Mapping[str, Any] = raw_detector if isinstance(raw_detector, Mapping) else {}
    for key in ("raw_pred_label", "label", "pred_label"):
        if key in detector:
            return detector[key]
    return None


def _is_anomalous_prediction(label: Any, *, score: float | None) -> bool | None:
    if isinstance(label, bool):
        return label
    if isinstance(label, (int, float)):
        return bool(label)
    text = _text_or_none(label)
    if text is None:
        return score is not None and score >= 0.5
    lowered = text.lower()
    if any(token in lowered for token in ("true", "anomal", "abnormal", "defect")):
        return True
    if any(token in lowered for token in ("false", "normal", "good")):
        return False
    if lowered in {"0", "0.0"}:
        return False
    if lowered in {"1", "1.0"}:
        return True
    return score is not None and score >= 0.5


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _path_or_none(value: Any) -> Path | None:
    text = _text_or_none(value)
    if text is None:
        return None
    path = Path(text)
    return path if path.is_file() else None
