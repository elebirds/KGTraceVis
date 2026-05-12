"""MVTec/DS-MVTec model-aware producer-output records."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from kgtracevis.producers.common import (
    MVTecAnomalyPredictor,
    deterministic_subset,
    filter_forbidden_outputs,
    model_metadata,
    write_array_json,
)

IMAGE_SUFFIXES = {".bmp", ".jpg", ".jpeg", ".png", ".tif", ".tiff"}


@dataclass(frozen=True)
class MVTecSample:
    """One discovered MVTec-like image sample."""

    image_path: Path
    object_name: str
    defect_type: str
    split: str
    gt_mask_path: Path | None = None

    @property
    def label(self) -> str:
        """Return the class/defect label used for subset balancing."""
        return self.defect_type


def build_mvtec_records(
    input_root: str | Path,
    predictor: MVTecAnomalyPredictor,
    *,
    output_dir: str | Path | None = None,
    model_backend: str = "local",
    checkpoint: str | Path | None = None,
    threshold: float = 0.5,
    max_cases: int | None = None,
    max_per_label: int | None = None,
    seed: int | None = None,
    include_good: bool = False,
) -> list[dict[str, Any]]:
    """Run a predictor over a MVTec-like folder tree and return record dictionaries."""
    root = Path(input_root)
    samples = discover_mvtec_samples(root, include_good=include_good)
    selected = deterministic_subset(
        samples,
        label=lambda sample: sample.label,
        sort_key=lambda sample: sample.image_path.as_posix(),
        max_cases=max_cases,
        max_per_label=max_per_label,
        seed=seed,
    )
    asset_dir = Path(output_dir) if output_dir is not None else None
    records = [
        _record_from_sample(
            sample,
            predictor.predict(sample.image_path),
            root=root,
            output_dir=asset_dir,
            model_backend=model_backend,
            checkpoint=checkpoint,
            threshold=threshold,
        )
        for sample in selected
    ]
    return [filter_forbidden_outputs(record) for record in records]


def discover_mvtec_samples(
    input_root: str | Path,
    *,
    include_good: bool = False,
) -> list[MVTecSample]:
    """Discover image samples under standard and tiny MVTec-like directory layouts."""
    root = Path(input_root)
    if not root.exists():
        raise FileNotFoundError(f"MVTec input root does not exist: {root}")
    samples: list[MVTecSample] = []
    for object_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        test_dir = object_dir / "test"
        if test_dir.is_dir():
            samples.extend(_samples_from_split_dir(root, object_dir, test_dir, "test"))
        else:
            samples.extend(_samples_from_flat_object_dir(root, object_dir))
    if not include_good:
        samples = [sample for sample in samples if sample.defect_type.lower() != "good"]
    return samples


def _record_from_sample(
    sample: MVTecSample,
    prediction: Mapping[str, Any],
    *,
    root: Path,
    output_dir: Path | None,
    model_backend: str,
    checkpoint: str | Path | None,
    threshold: float,
) -> dict[str, Any]:
    case_id = _case_id(sample, root)
    anomaly_map = _array_or_none(prediction.get("anomaly_map"))
    predicted_mask = _array_or_none(prediction.get("mask"))
    if predicted_mask is None and anomaly_map is not None:
        predicted_mask = anomaly_map >= threshold

    heatmap_path = _text_or_none(
        prediction.get("heatmap_path") or prediction.get("anomaly_map_path")
    )
    if heatmap_path is None and output_dir is not None and anomaly_map is not None:
        heatmap_path = str(write_array_json(output_dir / f"{case_id}_heatmap.json", anomaly_map))

    mask_path = _text_or_none(prediction.get("mask_path"))
    if mask_path is None and output_dir is not None and predicted_mask is not None:
        mask_path = str(write_array_json(output_dir / f"{case_id}_mask.json", predicted_mask))

    mask_stats = dict(prediction.get("mask_stats") or {})
    if not mask_stats and predicted_mask is not None:
        mask_stats = mask_stats_from_array(predicted_mask)

    score = _float_or_none(_first_present(prediction, ("score", "pred_score")))
    confidence = _unit_confidence_or_none(_float_or_none(prediction.get("confidence")))
    if confidence is None:
        confidence = _unit_confidence_or_none(score)
    prediction_metadata = (
        prediction.get("metadata") if isinstance(prediction.get("metadata"), Mapping) else None
    )
    detector_metadata = model_metadata(
        name="mvtec_anomaly_predictor",
        backend=model_backend,
        checkpoint=checkpoint,
        threshold=threshold,
        extra=prediction_metadata,
    )
    if score is not None:
        detector_metadata["pred_score"] = score
    if confidence is not None:
        detector_metadata["confidence"] = confidence

    record: dict[str, Any] = {
        "dataset": "mvtec",
        "case_id": case_id,
        "object": sample.object_name,
        "defect_type": sample.defect_type,
        "image_path": str(sample.image_path),
        "source_dataset": "mvtec",
        "source_split": sample.split,
        "source_label": sample.defect_type,
        "source_path": str(sample.image_path),
        "annotation_type": "native_ground_truth",
        "confidence": confidence,
        "score": score,
        "detector": detector_metadata,
        "model_name": detector_metadata["name"],
    }
    if sample.gt_mask_path is not None:
        record["gt_mask_path"] = str(sample.gt_mask_path)
    if mask_path is not None:
        record["mask_path"] = mask_path
    if heatmap_path is not None:
        record["heatmap_path"] = heatmap_path
    if mask_stats:
        record["mask_stats"] = mask_stats
    return record


def mask_stats_from_array(mask: Sequence[Sequence[Any]] | np.ndarray) -> dict[str, Any]:
    """Compute deterministic geometry stats from a binary mask-like array."""
    array = np.asarray(mask)
    if array.ndim != 2:
        raise ValueError("mask array must be 2-dimensional")
    binary = array.astype(float) > 0
    height, width = binary.shape
    area = int(binary.sum())
    stats: dict[str, Any] = {
        "image_shape": [int(height), int(width)],
        "area": area,
        "area_ratio": float(area / binary.size) if binary.size else 0.0,
        "component_count": _component_count(binary),
    }
    if area:
        ys, xs = np.where(binary)
        stats["bbox"] = [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]
        stats["centroid"] = [float(xs.mean()), float(ys.mean())]
        stats["eccentricity"] = _eccentricity(xs.astype(float), ys.astype(float))
    return stats


def _samples_from_split_dir(
    root: Path,
    object_dir: Path,
    split_dir: Path,
    split: str,
) -> list[MVTecSample]:
    samples: list[MVTecSample] = []
    for defect_dir in sorted(path for path in split_dir.iterdir() if path.is_dir()):
        for image_path in _image_files(defect_dir):
            samples.append(
                MVTecSample(
                    image_path=image_path,
                    object_name=object_dir.name,
                    defect_type=defect_dir.name,
                    split=split,
                    gt_mask_path=_find_gt_mask(root, object_dir.name, defect_dir.name, image_path),
                )
            )
    return samples


def _samples_from_flat_object_dir(root: Path, object_dir: Path) -> list[MVTecSample]:
    samples: list[MVTecSample] = []
    for defect_dir in sorted(path for path in object_dir.iterdir() if path.is_dir()):
        for image_path in _image_files(defect_dir):
            samples.append(
                MVTecSample(
                    image_path=image_path,
                    object_name=object_dir.name,
                    defect_type=defect_dir.name,
                    split="unknown",
                    gt_mask_path=_find_gt_mask(root, object_dir.name, defect_dir.name, image_path),
                )
            )
    return samples


def _image_files(path: Path) -> list[Path]:
    return sorted(
        child
        for child in path.rglob("*")
        if child.is_file() and child.suffix.lower() in IMAGE_SUFFIXES
    )


def _find_gt_mask(root: Path, object_name: str, defect_type: str, image_path: Path) -> Path | None:
    if defect_type.lower() == "good":
        return None
    candidates: list[Path] = []
    ground_truth = root / object_name / "ground_truth" / defect_type
    for suffix in sorted(IMAGE_SUFFIXES):
        candidates.append(ground_truth / f"{image_path.stem}_mask{suffix}")
        candidates.append(ground_truth / f"{image_path.stem}{suffix}")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _case_id(sample: MVTecSample, root: Path) -> str:
    try:
        relative = sample.image_path.relative_to(root)
    except ValueError:
        relative = sample.image_path
    token = "_".join(relative.with_suffix("").parts)
    return "mvtec_" + _safe_token(token)


def _safe_token(value: str) -> str:
    return "_".join("".join(ch.lower() if ch.isalnum() else " " for ch in value).split())


def _array_or_none(value: Any) -> np.ndarray | None:
    if value is None:
        return None
    array = np.asarray(value)
    if array.size == 0:
        return None
    if array.ndim > 2:
        array = np.squeeze(array)
    return array


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _unit_confidence_or_none(value: float | None) -> float | None:
    if value is None:
        return None
    return min(max(float(value), 0.0), 1.0)


def _first_present(data: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return None


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _component_count(binary: np.ndarray) -> int:
    remaining = set(zip(*np.where(binary), strict=True))
    count = 0
    while remaining:
        count += 1
        start = remaining.pop()
        queue = [start]
        while queue:
            row, col = queue.pop()
            for neighbor in ((row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    queue.append(neighbor)
    return count


def _eccentricity(xs: np.ndarray, ys: np.ndarray) -> float:
    if xs.size <= 1:
        return 0.0
    coords = np.stack([xs, ys])
    covariance = np.cov(coords)
    eigenvalues = np.linalg.eigvalsh(covariance)
    largest = float(max(eigenvalues))
    smallest = float(min(eigenvalues))
    if largest <= 0:
        return 0.0
    return float((1.0 - max(0.0, smallest) / largest) ** 0.5)
