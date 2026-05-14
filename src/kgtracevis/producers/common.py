"""Shared utilities for model-aware producer-output records."""

from __future__ import annotations

import hashlib
import json
import random
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol, TypedDict, TypeVar

REASONING_OUTPUT_KEYS = {
    "root_cause",
    "root_causes",
    "candidate_root_cause",
    "candidate_root_causes",
    "ranked_causes",
    "ranked_root_causes",
    "top_k_paths",
    "kg_analysis",
}


class MVTecPrediction(TypedDict, total=False):
    """Typed shape returned by an MVTec anomaly predictor."""

    score: float
    confidence: float
    label: str
    anomaly_map: Sequence[Sequence[float]]
    anomaly_map_path: str
    heatmap_path: str
    mask: Sequence[Sequence[int | float | bool]]
    mask_path: str
    mask_stats: Mapping[str, Any]
    metadata: Mapping[str, Any]


class WM811KPrediction(TypedDict, total=False):
    """Typed shape returned by a WM811K wafer-map classifier."""

    pattern: str
    confidence: float
    score: float
    saliency_map: Sequence[Sequence[float]]
    saliency_path: str
    attention_map_path: str
    descriptor_stats: Mapping[str, Any]
    metadata: Mapping[str, Any]


class MVTecAnomalyPredictor(Protocol):
    """Protocol for image-level MVTec anomaly predictors."""

    def predict(self, image_path: Path) -> MVTecPrediction:
        """Return anomaly evidence for one image."""
        ...


class WM811KClassifier(Protocol):
    """Protocol for WM811K wafer-map classifiers."""

    def predict(
        self,
        wafer_map: Sequence[Sequence[Any]],
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> WM811KPrediction:
        """Return classifier evidence for one wafer map."""
        ...


T = TypeVar("T")


def write_jsonl_records(
    records: Iterable[Mapping[str, Any]],
    output_path: str | Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Write producer-output records to JSONL after filtering reasoning outputs."""
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not overwrite:
        raise FileExistsError(f"{destination} already exists; pass --overwrite to replace it")
    lines = [
        json.dumps(filter_forbidden_outputs(record), sort_keys=False, ensure_ascii=False)
        for record in records
    ]
    destination.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return destination


def deterministic_subset(
    items: Sequence[T],
    *,
    label: Callable[[T], str],
    sort_key: Callable[[T], str],
    max_cases: int | None = None,
    max_per_label: int | None = None,
    seed: int | None = None,
) -> list[T]:
    """Return a deterministic optionally class-balanced subset."""
    if max_cases is not None and max_cases < 0:
        raise ValueError("max_cases must be non-negative")
    if max_per_label is not None and max_per_label < 0:
        raise ValueError("max_per_label must be non-negative")

    rng = random.Random(seed) if seed is not None else None
    ordered = sorted(items, key=sort_key)
    if max_per_label is not None:
        grouped: dict[str, list[T]] = defaultdict(list)
        for item in ordered:
            grouped[label(item)].append(item)
        selected: list[T] = []
        for group_label in sorted(grouped):
            group = grouped[group_label]
            if rng is not None:
                rng.shuffle(group)
            selected.extend(sorted(group[:max_per_label], key=sort_key))
    else:
        selected = list(ordered)
        if rng is not None:
            rng.shuffle(selected)

    selected = sorted(selected, key=sort_key)
    if max_cases is not None:
        selected = selected[:max_cases]
    return selected


def filter_forbidden_outputs(value: Any) -> Any:
    """Return a JSON-safe copy with root-cause and path-ranking keys removed."""
    if isinstance(value, Mapping):
        return {
            str(key): filter_forbidden_outputs(nested)
            for key, nested in value.items()
            if str(key) not in REASONING_OUTPUT_KEYS
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [filter_forbidden_outputs(item) for item in value]
    return _json_safe_scalar(value)


def model_metadata(
    *,
    name: str,
    backend: str,
    checkpoint: str | Path | None = None,
    threshold: float | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a compact model/provenance metadata dictionary."""
    metadata: dict[str, Any] = {"name": name, "backend": backend}
    if checkpoint is not None:
        checkpoint_path = Path(checkpoint)
        metadata["checkpoint"] = str(checkpoint_path)
        checkpoint_hash = file_sha256(checkpoint_path)
        if checkpoint_hash is not None:
            metadata["checkpoint_sha256"] = checkpoint_hash
    if threshold is not None:
        metadata["threshold"] = threshold
    if extra:
        metadata.update(filter_forbidden_outputs(extra))
    return metadata


def file_sha256(path: Path) -> str | None:
    """Return the SHA-256 digest for an existing checkpoint-like file."""
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_array_json(path: str | Path, array: Sequence[Sequence[Any]]) -> Path:
    """Persist a small array-like output as JSON."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(filter_forbidden_outputs(array)), encoding="utf-8")
    return destination


def _json_safe_scalar(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "tolist") and callable(value.tolist):
        return filter_forbidden_outputs(value.tolist())
    if hasattr(value, "item") and callable(value.item):
        try:
            return filter_forbidden_outputs(value.item())
        except (TypeError, ValueError):
            pass
    return value
