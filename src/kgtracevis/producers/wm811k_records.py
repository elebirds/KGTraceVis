"""WM811K model-aware producer-output records."""

from __future__ import annotations

import ast
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pandas as pd

from kgtracevis.mask.wafer_map_features import normalize_wafer_map_features
from kgtracevis.producers.common import (
    WM811KClassifier,
    deterministic_subset,
    filter_forbidden_outputs,
    model_metadata,
    write_array_json,
)

NONE_LABELS = {"", "none", "normal", "no label", "unlabeled", "unknown", "[]" }


def build_wm811k_records(
    input_path: str | Path,
    classifier: WM811KClassifier,
    *,
    output_dir: str | Path | None = None,
    model_backend: str = "local",
    checkpoint: str | Path | None = None,
    threshold: float | None = None,
    max_cases: int | None = None,
    max_per_label: int | None = None,
    seed: int | None = None,
    include_unlabeled: bool = False,
    wafer_map_inline_limit: int = 400,
) -> list[dict[str, Any]]:
    """Run a classifier over a pandas-readable WM811K table and return records."""
    table = load_wm811k_table(input_path)
    rows = [
        _row_context(row, index=index, input_path=Path(input_path))
        for index, row in table.iterrows()
    ]
    if not include_unlabeled:
        rows = [row for row in rows if row["native_failure_pattern"].lower() not in NONE_LABELS]
    selected = deterministic_subset(
        rows,
        label=lambda row: str(row["native_failure_pattern"]),
        sort_key=lambda row: str(row["case_id"]),
        max_cases=max_cases,
        max_per_label=max_per_label,
        seed=seed,
    )
    asset_dir = Path(output_dir) if output_dir is not None else None
    records = [
        _record_from_row(
            row,
            classifier.predict(row["wafer_map"], metadata=row),
            output_dir=asset_dir,
            model_backend=model_backend,
            checkpoint=checkpoint,
            threshold=threshold,
            wafer_map_inline_limit=wafer_map_inline_limit,
        )
        for row in selected
    ]
    return [filter_forbidden_outputs(record) for record in records]


def load_wm811k_table(input_path: str | Path) -> pd.DataFrame:
    """Load a WM811K-like table from CSV, JSON, JSONL, pickle, or parquet."""
    path = Path(input_path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix == ".json":
        return pd.read_json(path)
    if suffix == ".jsonl":
        return pd.read_json(path, lines=True)
    if suffix in {".pkl", ".pickle"}:
        return pd.read_pickle(path)
    if suffix == ".parquet":
        return pd.read_parquet(path)
    raise ValueError(f"unsupported WM811K input format for {path}")


def _record_from_row(
    row: Mapping[str, Any],
    prediction: Mapping[str, Any],
    *,
    output_dir: Path | None,
    model_backend: str,
    checkpoint: str | Path | None,
    threshold: float | None,
    wafer_map_inline_limit: int,
) -> dict[str, Any]:
    wafer_map = row["wafer_map"]
    predicted_pattern = _text_or_unknown(
        prediction.get("pattern") or prediction.get("failure_pattern") or prediction.get("label")
    )
    confidence = _float_or_none(_first_present_mapping(prediction, ("confidence", "score")))
    descriptor_stats = normalize_wafer_map_features(
        prediction.get("descriptor_stats")
        if isinstance(prediction.get("descriptor_stats"), Mapping)
        else None,
        wafer_map=wafer_map,
        pattern=predicted_pattern,
    )
    saliency_path = _text_or_none(
        prediction.get("saliency_path") or prediction.get("attention_map_path")
    )
    has_saliency_map = prediction.get("saliency_map") is not None
    if saliency_path is None and output_dir is not None and has_saliency_map:
        saliency_path = str(
            write_array_json(
                output_dir / f"{row['case_id']}_saliency.json",
                prediction["saliency_map"],
            )
        )

    prediction_metadata = (
        prediction.get("metadata") if isinstance(prediction.get("metadata"), Mapping) else None
    )
    classifier_metadata = model_metadata(
        name="wm811k_classifier",
        backend=model_backend,
        checkpoint=checkpoint,
        threshold=threshold,
        extra=prediction_metadata,
    )
    if confidence is not None:
        classifier_metadata["confidence"] = confidence

    record: dict[str, Any] = {
        "dataset": "wafer",
        "adapter": "wm811k",
        "source_dataset": "wm811k",
        "case_id": row["case_id"],
        "wafer_id": row["wafer_id"],
        "failure_pattern": predicted_pattern,
        "predicted_pattern": predicted_pattern,
        "classification_confidence": confidence,
        "descriptor_stats": descriptor_stats,
        "defect_density": descriptor_stats.get("defect_density"),
        "native_failure_pattern": row["native_failure_pattern"],
        "annotation_type": (
            "native_ground_truth"
            if row["native_failure_pattern"].lower() not in NONE_LABELS
            else "unlabeled"
        ),
        "source_table": row["source_table"],
        "source_row_index": row["source_row_index"],
        "classifier": classifier_metadata,
        "model_name": classifier_metadata["name"],
    }
    if saliency_path is not None:
        record["saliency_path"] = saliency_path
    if _wafer_map_cell_count(wafer_map) <= wafer_map_inline_limit:
        record["wafer_map"] = wafer_map
    elif output_dir is not None:
        record["wafer_map_path"] = str(
            write_array_json(output_dir / f"{row['case_id']}_map.json", wafer_map)
        )
    else:
        record["map_shape"] = descriptor_stats.get("map_shape")
    return record


def _row_context(row: pd.Series, *, index: Any, input_path: Path) -> dict[str, Any]:
    wafer_map = _parse_wafer_map(_first_present(row, ("waferMap", "wafer_map", "map", "die_map")))
    native_label = _canonical_label(
        _first_present(row, ("failureType", "failure_pattern", "label", "pattern"))
    )
    wafer_id = _wafer_id(row, index)
    return {
        "case_id": _safe_token(f"wm811k_{wafer_id}"),
        "wafer_id": wafer_id,
        "wafer_map": wafer_map,
        "native_failure_pattern": native_label,
        "source_table": str(input_path),
        "source_row_index": int(index) if isinstance(index, int) else str(index),
    }


def _first_present(row: pd.Series, keys: Sequence[str]) -> Any:
    for key in keys:
        if key in row and row[key] is not None:
            value = row[key]
            if not _is_missing(value):
                return value
    return None


def _first_present_mapping(data: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return None


def _parse_wafer_map(value: Any) -> list[list[Any]]:
    if value is None or _is_missing(value):
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            value = ast.literal_eval(text)
    if hasattr(value, "tolist") and callable(value.tolist):
        value = value.tolist()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("wafer map must be a 2-dimensional sequence")
    rows = [
        list(row)
        for row in value
        if isinstance(row, Sequence) and not isinstance(row, (str, bytes))
    ]
    if len(rows) != len(value):
        raise ValueError("wafer map must be a 2-dimensional sequence")
    return rows


def _canonical_label(value: Any) -> str:
    if value is None or _is_missing(value):
        return "none"
    if hasattr(value, "tolist") and callable(value.tolist):
        value = value.tolist()
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        flattened = [_canonical_label(item) for item in value]
        for item in flattened:
            if item.lower() not in NONE_LABELS:
                return item
        return "none"
    text = str(value).strip()
    return text or "none"


def _wafer_id(row: pd.Series, index: Any) -> str:
    explicit = _first_present(row, ("wafer_id", "waferId", "id", "case_id"))
    if explicit is not None:
        return str(explicit)
    lot = _first_present(row, ("lotName", "lot_id", "lot"))
    wafer_index = _first_present(row, ("waferIndex", "wafer_index"))
    if lot is not None and wafer_index is not None:
        return f"{lot}-{wafer_index}"
    return f"row-{index}"


def _wafer_map_cell_count(wafer_map: Sequence[Sequence[Any]]) -> int:
    return sum(len(row) for row in wafer_map)


def _safe_token(value: str) -> str:
    return "_".join("".join(ch.lower() if ch.isalnum() else " " for ch in value).split())


def _text_or_unknown(value: Any) -> str:
    text = _text_or_none(value)
    return text or "unknown"


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _is_missing(value: Any) -> bool:
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False
