"""Visual evidence artifact preparation for RootLens run details."""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal, cast

import numpy as np
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field

VisualEvidenceKind = Literal["image", "mask", "heatmap", "wafer_map"]

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
ARRAY_SUFFIXES = {".json", ".npy"}
PROJECT_ROOT = Path.cwd().resolve()


class VisualEvidenceItem(BaseModel):
    """One browser-renderable visual artifact attached to a run case."""

    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    case_id: str
    dataset: str
    kind: VisualEvidenceKind
    title: str
    source_key: str
    source_path: str | None = None
    url: str | None = None
    preview_path: str | None = None
    available: bool
    note: str
    metadata: dict[str, Any] = Field(default_factory=dict)


def build_visual_evidence_artifacts(
    records: Sequence[Mapping[str, Any]],
    *,
    run_id: str,
    run_dir: str | Path,
) -> list[dict[str, Any]]:
    """Create safe preview artifacts for producer records and return API payloads."""
    artifact_dir = Path(run_dir) / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    items: list[VisualEvidenceItem] = []
    used_filenames: set[str] = set()
    for record in records:
        items.extend(
            _record_visual_items(
                record,
                run_id=run_id,
                run_dir=Path(run_dir),
                artifact_dir=artifact_dir,
                used_filenames=used_filenames,
            )
        )
    return [item.model_dump(mode="json") for item in items]


def _record_visual_items(
    record: Mapping[str, Any],
    *,
    run_id: str,
    run_dir: Path,
    artifact_dir: Path,
    used_filenames: set[str],
) -> list[VisualEvidenceItem]:
    case_id = _text(_first_value(record, ("case_id",))) or "case"
    dataset = _text(_first_value(record, ("dataset",))) or "unknown"
    items: list[VisualEvidenceItem] = []
    for kind, title, keys in (
        ("image", "Source image", ("source_path", "image_path")),
        ("mask", "Predicted / reference mask", ("mask_path", "gt_mask_path", "segmentation_path")),
        ("heatmap", "Anomaly heatmap", ("heatmap_path", "anomaly_map_path")),
    ):
        value, source_key = _first_path_value(record, keys)
        if value:
            items.append(
                _path_item(
                    case_id=case_id,
                    dataset=dataset,
                    kind=cast(VisualEvidenceKind, kind),
                    title=title,
                    source_key=source_key,
                    source_path=value,
                    run_id=run_id,
                    run_dir=run_dir,
                    artifact_dir=artifact_dir,
                    used_filenames=used_filenames,
                )
            )

    wafer_map, source_key = _first_value_with_key(
        record,
        ("wafer_map", "wafer_map_path", "map_path"),
    )
    if wafer_map is not None:
        items.append(
            _wafer_map_item(
                case_id=case_id,
                dataset=dataset,
                source_key=source_key,
                value=wafer_map,
                run_id=run_id,
                run_dir=run_dir,
                artifact_dir=artifact_dir,
                used_filenames=used_filenames,
            )
        )
    return items


def _path_item(
    *,
    case_id: str,
    dataset: str,
    kind: VisualEvidenceKind,
    title: str,
    source_key: str,
    source_path: str,
    run_id: str,
    run_dir: Path,
    artifact_dir: Path,
    used_filenames: set[str],
) -> VisualEvidenceItem:
    artifact_id = _artifact_id(case_id, kind, source_path)
    source = _resolve_safe_path(source_path, run_dir=run_dir)
    if source is None:
        return _unavailable_item(
            artifact_id=artifact_id,
            case_id=case_id,
            dataset=dataset,
            kind=kind,
            title=title,
            source_key=source_key,
            source_path=source_path,
            note="Source path is missing or outside the project/run artifact boundary.",
        )

    destination = _unique_destination(artifact_dir, artifact_id, ".png", used_filenames)
    try:
        if source.suffix.lower() in IMAGE_SUFFIXES:
            _copy_image_as_png(source, destination)
        elif source.suffix.lower() in ARRAY_SUFFIXES:
            array = _load_array(source)
            _save_array_preview(array, destination, kind=kind)
        else:
            return _unavailable_item(
                artifact_id=artifact_id,
                case_id=case_id,
                dataset=dataset,
                kind=kind,
                title=title,
                source_key=source_key,
                source_path=str(source),
                note=f"Unsupported visual artifact format: {source.suffix or 'none'}.",
            )
        metadata = _array_metadata(destination)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return _unavailable_item(
            artifact_id=artifact_id,
            case_id=case_id,
            dataset=dataset,
            kind=kind,
            title=title,
            source_key=source_key,
            source_path=str(source),
            note=f"Failed to prepare preview: {exc}",
        )

    return VisualEvidenceItem(
        artifact_id=artifact_id,
        case_id=case_id,
        dataset=dataset,
        kind=kind,
        title=title,
        source_key=source_key,
        source_path=str(source),
        url=f"/api/runs/{run_id}/artifacts/{destination.name}",
        preview_path=str(destination),
        available=True,
        note="Observed visual evidence preview prepared for browser inspection.",
        metadata=metadata,
    )


def _wafer_map_item(
    *,
    case_id: str,
    dataset: str,
    source_key: str,
    value: Any,
    run_id: str,
    run_dir: Path,
    artifact_dir: Path,
    used_filenames: set[str],
) -> VisualEvidenceItem:
    artifact_id = _artifact_id(case_id, "wafer_map", source_key)
    source_path = value if isinstance(value, str) else None
    try:
        if isinstance(value, str):
            source = _resolve_safe_path(value, run_dir=run_dir)
            if source is None:
                return _unavailable_item(
                    artifact_id=artifact_id,
                    case_id=case_id,
                    dataset=dataset,
                    kind="wafer_map",
                    title="Wafer map",
                    source_key=source_key,
                    source_path=value,
                    note="Wafer map path is missing or outside the project/run artifact boundary.",
                )
            wafer_map = _load_array(source)
            source_path = str(source)
        else:
            wafer_map = np.asarray(value, dtype=float)
        destination = _unique_destination(artifact_dir, artifact_id, ".png", used_filenames)
        _save_wafer_map_preview(wafer_map, destination)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return _unavailable_item(
            artifact_id=artifact_id,
            case_id=case_id,
            dataset=dataset,
            kind="wafer_map",
            title="Wafer map",
            source_key=source_key,
            source_path=source_path,
            note=f"Failed to prepare wafer-map preview: {exc}",
        )

    return VisualEvidenceItem(
        artifact_id=artifact_id,
        case_id=case_id,
        dataset=dataset,
        kind="wafer_map",
        title="Wafer map",
        source_key=source_key,
        source_path=source_path,
        url=f"/api/runs/{run_id}/artifacts/{destination.name}",
        preview_path=str(destination),
        available=True,
        note="Observed wafer-map evidence preview prepared for browser inspection.",
        metadata=_array_metadata(destination),
    )


def _first_path_value(record: Mapping[str, Any], keys: Sequence[str]) -> tuple[str | None, str]:
    value, key = _first_value_with_key(record, keys)
    return (_text(value) if value is not None else None, key)


def _first_value_with_key(record: Mapping[str, Any], keys: Sequence[str]) -> tuple[Any | None, str]:
    candidates = [record]
    raw = record.get("raw_evidence")
    if isinstance(raw, Mapping):
        candidates.append(raw)
        extra = raw.get("extra")
        if isinstance(extra, Mapping):
            candidates.append(extra)
            wm811k = extra.get("wm811k")
            if isinstance(wm811k, Mapping):
                candidates.append(wm811k)
    extra = record.get("extra")
    if isinstance(extra, Mapping):
        candidates.append(extra)

    for key in keys:
        for candidate in candidates:
            if key in candidate and candidate[key] not in (None, ""):
                return candidate[key], key
    return None, keys[0] if keys else ""


def _first_value(record: Mapping[str, Any], keys: Sequence[str]) -> Any | None:
    value, _key = _first_value_with_key(record, keys)
    return value


def _resolve_safe_path(value: str, *, run_dir: Path) -> Path | None:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    try:
        resolved = path.resolve()
        resolved.relative_to(PROJECT_ROOT)
    except ValueError:
        try:
            resolved.relative_to(run_dir.resolve())
        except ValueError:
            return None
    return resolved if resolved.is_file() else None


def _copy_image_as_png(source: Path, destination: Path) -> None:
    if source.suffix.lower() == ".png":
        shutil.copy2(source, destination)
        return
    with Image.open(source) as image:
        image.convert("RGB").save(destination)


def _load_array(source: Path) -> np.ndarray:
    if source.suffix.lower() == ".npy":
        return np.asarray(np.load(source, allow_pickle=False), dtype=float)
    return np.asarray(json.loads(source.read_text(encoding="utf-8")), dtype=float)


def _save_array_preview(
    array: np.ndarray,
    destination: Path,
    *,
    kind: VisualEvidenceKind,
) -> None:
    if array.ndim == 3:
        array = array[:, :, 0]
    if array.ndim != 2:
        raise ValueError(f"expected 2D array, got shape {array.shape}")
    if kind == "heatmap":
        image = Image.fromarray(_heatmap_rgb(array), mode="RGB")
    else:
        image = Image.fromarray(_grayscale(array), mode="L").convert("RGB")
    image.save(destination)


def _save_wafer_map_preview(array: np.ndarray, destination: Path) -> None:
    if array.ndim != 2:
        raise ValueError(f"expected 2D wafer map, got shape {array.shape}")
    rgb = np.zeros((*array.shape, 3), dtype=np.uint8)
    rgb[:, :] = (235, 241, 245)
    rgb[array == 1] = (82, 139, 112)
    rgb[array == 2] = (201, 69, 58)
    rgb[(array != 0) & (array != 1) & (array != 2)] = (68, 115, 178)
    image = Image.fromarray(rgb, mode="RGB")
    scale = max(5, min(18, 360 // max(array.shape)))
    image = image.resize((array.shape[1] * scale, array.shape[0] * scale), Image.Resampling.NEAREST)
    image.save(destination)


def _heatmap_rgb(array: np.ndarray) -> np.ndarray:
    normalized = _normalized(array)
    red = (255 * normalized).astype(np.uint8)
    green = (180 * (1 - np.abs(normalized - 0.5) * 2)).astype(np.uint8)
    blue = (255 * (1 - normalized)).astype(np.uint8)
    return np.stack([red, green, blue], axis=2)


def _grayscale(array: np.ndarray) -> np.ndarray:
    return (255 * _normalized(array)).astype(np.uint8)


def _normalized(array: np.ndarray) -> np.ndarray:
    finite = np.asarray(array, dtype=float)
    if finite.size == 0:
        raise ValueError("empty array")
    minimum = float(np.nanmin(finite))
    maximum = float(np.nanmax(finite))
    if maximum <= minimum:
        return np.zeros(finite.shape, dtype=float)
    return np.nan_to_num((finite - minimum) / (maximum - minimum), nan=0.0)


def _array_metadata(path: Path) -> dict[str, Any]:
    with Image.open(path) as image:
        width, height = image.size
    return {"preview_width": width, "preview_height": height}


def _artifact_id(case_id: str, kind: str, source: str) -> str:
    suffix = Path(source).stem if source else kind
    return f"{_slug(case_id)}_{kind}_{_slug(suffix)}"


def _unique_destination(
    artifact_dir: Path,
    artifact_id: str,
    suffix: str,
    used_filenames: set[str],
) -> Path:
    filename = f"{artifact_id}{suffix}"
    index = 2
    while filename in used_filenames:
        filename = f"{artifact_id}_{index}{suffix}"
        index += 1
    used_filenames.add(filename)
    return artifact_dir / filename


def _unavailable_item(
    *,
    artifact_id: str,
    case_id: str,
    dataset: str,
    kind: VisualEvidenceKind,
    title: str,
    source_key: str,
    source_path: str | None,
    note: str,
) -> VisualEvidenceItem:
    return VisualEvidenceItem(
        artifact_id=artifact_id,
        case_id=case_id,
        dataset=dataset,
        kind=kind,
        title=title,
        source_key=source_key,
        source_path=source_path,
        available=False,
        note=note,
    )


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return slug or "artifact"


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()
