"""Calibration helpers for MVTec producer evidence thresholds."""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


@dataclass(frozen=True)
class MVTecObjectThresholds:
    """Per-object thresholds used to convert PatchCore scores/maps into evidence."""

    object_name: str
    score_threshold: float | None = None
    map_threshold: float | None = None
    min_area_ratio: float | None = None
    threshold_source: str = "unknown"
    uses_ground_truth: bool = False
    calibration_scope: str = "object_specific"
    method: str = "unknown"


@dataclass(frozen=True)
class MVTecThresholdConfig:
    """Loaded threshold configuration for MVTec producer records."""

    thresholds: Mapping[str, MVTecObjectThresholds]
    threshold_source: str = "unknown"
    uses_ground_truth: bool = False
    calibration_scope: str = "object_specific"

    def for_object(self, object_name: str) -> MVTecObjectThresholds | None:
        """Return thresholds for an object name, if configured."""
        return self.thresholds.get(_canonical_object(object_name))


def load_mvtec_threshold_config(path: str | Path | None) -> MVTecThresholdConfig | None:
    """Load a MVTec threshold config JSON file, returning ``None`` for no path."""
    if path is None:
        return None
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return threshold_config_from_mapping(payload)


def threshold_config_from_mapping(payload: Mapping[str, Any]) -> MVTecThresholdConfig:
    """Build a threshold config from a JSON-like mapping."""
    source = str(payload.get("threshold_source") or payload.get("method") or "unknown")
    uses_ground_truth = bool(payload.get("uses_ground_truth", False))
    scope = str(payload.get("calibration_scope") or "object_specific")
    raw_objects = payload.get("objects")
    if not isinstance(raw_objects, Mapping):
        raise ValueError("MVTec threshold config must contain an 'objects' mapping")

    thresholds: dict[str, MVTecObjectThresholds] = {}
    for object_name, raw_value in raw_objects.items():
        if not isinstance(raw_value, Mapping):
            raise ValueError(f"threshold entry for {object_name!r} must be a mapping")
        canonical = _canonical_object(str(object_name))
        thresholds[canonical] = MVTecObjectThresholds(
            object_name=canonical,
            score_threshold=_optional_float(raw_value.get("score_threshold")),
            map_threshold=_optional_float(raw_value.get("map_threshold")),
            min_area_ratio=_optional_float(raw_value.get("min_area_ratio")),
            threshold_source=str(raw_value.get("threshold_source") or source),
            uses_ground_truth=bool(raw_value.get("uses_ground_truth", uses_ground_truth)),
            calibration_scope=str(raw_value.get("calibration_scope") or scope),
            method=str(raw_value.get("method") or payload.get("method") or "unknown"),
        )
    return MVTecThresholdConfig(
        thresholds=thresholds,
        threshold_source=source,
        uses_ground_truth=uses_ground_truth,
        calibration_scope=scope,
    )


def threshold_config_to_mapping(
    thresholds: Sequence[MVTecObjectThresholds],
    *,
    threshold_source: str,
    uses_ground_truth: bool,
    calibration_scope: str = "object_specific",
    method: str = "supervised_f1_quick",
) -> dict[str, Any]:
    """Return a stable JSON-serializable threshold config mapping."""
    return {
        "artifact_type": "mvtec_patchcore_threshold_config_v0",
        "threshold_source": threshold_source,
        "uses_ground_truth": uses_ground_truth,
        "calibration_scope": calibration_scope,
        "method": method,
        "objects": {
            item.object_name: {
                "score_threshold": item.score_threshold,
                "map_threshold": item.map_threshold,
                "min_area_ratio": item.min_area_ratio,
                "threshold_source": item.threshold_source,
                "uses_ground_truth": item.uses_ground_truth,
                "calibration_scope": item.calibration_scope,
                "method": item.method,
            }
            for item in sorted(thresholds, key=lambda value: value.object_name)
        },
    }


def write_threshold_config(
    thresholds: Sequence[MVTecObjectThresholds],
    output_path: str | Path,
    *,
    threshold_source: str = "supervised_ds_mvtec_quick_calibration",
    uses_ground_truth: bool = True,
    method: str = "supervised_f1_quick",
) -> Path:
    """Write thresholds as JSON and return the destination path."""
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = threshold_config_to_mapping(
        thresholds,
        threshold_source=threshold_source,
        uses_ground_truth=uses_ground_truth,
        method=method,
    )
    destination.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return destination


def write_threshold_csv(
    thresholds: Sequence[MVTecObjectThresholds],
    output_path: str | Path,
) -> Path:
    """Write a compact threshold table for human review."""
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "object",
        "score_threshold",
        "map_threshold",
        "min_area_ratio",
        "method",
        "threshold_source",
        "uses_ground_truth",
        "calibration_scope",
    ]
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in sorted(thresholds, key=lambda value: value.object_name):
            writer.writerow(
                {
                    "object": item.object_name,
                    "score_threshold": item.score_threshold,
                    "map_threshold": item.map_threshold,
                    "min_area_ratio": item.min_area_ratio,
                    "method": item.method,
                    "threshold_source": item.threshold_source,
                    "uses_ground_truth": item.uses_ground_truth,
                    "calibration_scope": item.calibration_scope,
                }
            )
    return destination


def calibrate_thresholds_from_records(
    records: Sequence[Mapping[str, Any]],
    *,
    method: str = "supervised_f1_quick",
    threshold_source: str = "supervised_ds_mvtec_quick_calibration",
    min_area_ratio: float = 0.001,
) -> list[MVTecObjectThresholds]:
    """Compute per-object image and map thresholds from producer records."""
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for record in records:
        object_name = _canonical_object(str(record.get("object") or "unknown"))
        grouped.setdefault(object_name, []).append(record)

    thresholds: list[MVTecObjectThresholds] = []
    for object_name, object_records in sorted(grouped.items()):
        score_threshold = _score_threshold(object_records)
        map_threshold = _map_threshold(object_records)
        thresholds.append(
            MVTecObjectThresholds(
                object_name=object_name,
                score_threshold=score_threshold,
                map_threshold=map_threshold,
                min_area_ratio=min_area_ratio,
                threshold_source=threshold_source,
                uses_ground_truth=True,
                calibration_scope="object_specific",
                method=method,
            )
        )
    return thresholds


def calibration_metadata(thresholds: MVTecObjectThresholds) -> dict[str, Any]:
    """Return producer metadata fields for an applied threshold entry."""
    return {
        "threshold_source": thresholds.threshold_source,
        "uses_ground_truth": thresholds.uses_ground_truth,
        "calibration_scope": thresholds.calibration_scope,
        "calibration_object": thresholds.object_name,
        "score_threshold": thresholds.score_threshold,
        "map_threshold": thresholds.map_threshold,
        "min_area_ratio": thresholds.min_area_ratio,
        "calibration_method": thresholds.method,
    }


def calibrated_confidence(score: float | None, threshold: float | None) -> float | None:
    """Return a simple unit-scale anomaly confidence from a calibrated score."""
    if score is None:
        return None
    if threshold is None:
        return min(max(float(score), 0.0), 1.0)
    return 1.0 if float(score) >= float(threshold) else 0.0


def calibrated_label(score: float | None, threshold: float | None) -> str | None:
    """Return an image-level calibrated prediction label."""
    if score is None or threshold is None:
        return None
    return "anomalous" if float(score) >= float(threshold) else "normal"


def mask_from_anomaly_map(
    anomaly_map: np.ndarray,
    *,
    map_threshold: float,
    min_area_ratio: float | None = None,
) -> np.ndarray:
    """Threshold an anomaly map and optionally suppress tiny components globally."""
    mask = np.asarray(anomaly_map, dtype=float) >= float(map_threshold)
    if min_area_ratio is not None and mask.size:
        if float(mask.sum() / mask.size) < float(min_area_ratio):
            mask = np.zeros_like(mask, dtype=bool)
    return mask


def _score_threshold(records: Sequence[Mapping[str, Any]]) -> float | None:
    scores: list[float] = []
    labels: list[int] = []
    for record in records:
        score = _optional_float(record.get("score"))
        if score is None:
            continue
        scores.append(score)
        labels.append(0 if str(record.get("defect_type", "")).lower() == "good" else 1)
    if not scores or len(set(labels)) < 2:
        return None
    return _best_f1_threshold(np.asarray(scores, dtype=float), np.asarray(labels, dtype=int))


def _map_threshold(records: Sequence[Mapping[str, Any]]) -> float | None:
    values: list[np.ndarray] = []
    labels: list[np.ndarray] = []
    for record in records:
        heatmap_path = record.get("heatmap_path") or record.get("anomaly_map_path")
        if not heatmap_path:
            continue
        try:
            heatmap = np.asarray(json.loads(Path(str(heatmap_path)).read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            continue
        if heatmap.ndim > 2:
            heatmap = np.squeeze(heatmap)
        if heatmap.ndim != 2:
            continue
        gt_mask = _gt_mask_for_record(record, shape=heatmap.shape)
        values.append(heatmap.astype(float).ravel())
        labels.append(gt_mask.astype(int).ravel())
    if not values or not labels:
        return None
    flat_values = np.concatenate(values)
    flat_labels = np.concatenate(labels)
    if flat_values.size == 0 or len(set(flat_labels.tolist())) < 2:
        return None
    quantiles = np.linspace(0.0, 1.0, 512)
    candidates = np.unique(np.quantile(flat_values, quantiles))
    return _best_f1_threshold(flat_values, flat_labels, candidates=candidates)


def _gt_mask_for_record(record: Mapping[str, Any], *, shape: tuple[int, int]) -> np.ndarray:
    gt_mask_path = record.get("gt_mask_path")
    if not gt_mask_path:
        return np.zeros(shape, dtype=bool)
    try:
        from PIL import Image

        image = Image.open(Path(str(gt_mask_path))).convert("L")
    except (OSError, TypeError, ValueError):
        return np.zeros(shape, dtype=bool)
    height, width = shape
    if image.size != (width, height):
        image = image.resize((width, height), Image.Resampling.NEAREST)
    return np.asarray(image) > 0


def _best_f1_threshold(
    scores: np.ndarray,
    labels: np.ndarray,
    *,
    candidates: np.ndarray | None = None,
) -> float:
    if candidates is None:
        candidates = np.unique(scores)
    best_threshold = float(candidates[0])
    best_f1 = -1.0
    for threshold in candidates:
        predicted = scores >= threshold
        true_positive = int(np.logical_and(predicted, labels == 1).sum())
        false_positive = int(np.logical_and(predicted, labels == 0).sum())
        false_negative = int(np.logical_and(~predicted, labels == 1).sum())
        precision_denominator = true_positive + false_positive
        recall_denominator = true_positive + false_negative
        precision = true_positive / precision_denominator if precision_denominator else 0.0
        recall = true_positive / recall_denominator if recall_denominator else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        if f1 > best_f1 or (f1 == best_f1 and float(threshold) > best_threshold):
            best_f1 = f1
            best_threshold = float(threshold)
    return best_threshold


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _canonical_object(value: str) -> str:
    text = value.strip().lower()
    if text.startswith("mvtec_"):
        text = text.removeprefix("mvtec_")
    return text
