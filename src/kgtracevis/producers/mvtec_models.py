"""MVTec model preset resolution helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from kgtracevis.producers.backends import ANOMALIB_OPENVINO_BACKEND, ANOMALIB_TORCH_BACKEND

MVTecModelPreset = Literal["auto", "stfpm", "patchcore", "efficientad"]
MVTecResolvedPreset = Literal["stfpm", "patchcore", "efficientad"]

DEFAULT_MVTEC_MODEL_PRESET: MVTecModelPreset = "auto"
MVTEC_MODEL_PRESET_PRIORITY: tuple[MVTecResolvedPreset, ...] = (
    "efficientad",
    "patchcore",
    "stfpm",
)

DEFAULT_MVTEC_STFPM_CHECKPOINT = Path(
    "runs/real_model_pipeline/assets/mvtec/checkpoints/openvino_model/stfpm_capsule.xml"
)
DEFAULT_MVTEC_PATCHCORE_CHECKPOINT = Path("data/external/checkpoints/mvtec_patchcore.pt")
DEFAULT_MVTEC_EFFICIENTAD_CHECKPOINT = Path("data/external/checkpoints/mvtec_efficientad.pt")


@dataclass(frozen=True)
class MVTecModelPresetSpec:
    """Static information about one selectable MVTec model preset."""

    preset: MVTecResolvedPreset
    label: str
    description: str
    checkpoint_env: str
    default_checkpoint: Path
    backend_hint: str
    preferred_suffixes: tuple[str, ...]


@dataclass(frozen=True)
class MVTecModelSelection:
    """Resolved checkpoint/backend pair for one MVTec image-model preset."""

    preset: MVTecResolvedPreset
    label: str
    description: str
    backend: str
    checkpoint_path: Path
    available: bool
    checkpoint_hint: str


MVTEC_MODEL_PRESET_SPECS: dict[MVTecResolvedPreset, MVTecModelPresetSpec] = {
    "stfpm": MVTecModelPresetSpec(
        preset="stfpm",
        label="STFPM",
        description="当前内置 OpenVINO checkpoint，最容易开箱运行。",
        checkpoint_env="KGTRACEVIS_MVTEC_STFPM_CHECKPOINT",
        default_checkpoint=DEFAULT_MVTEC_STFPM_CHECKPOINT,
        backend_hint=ANOMALIB_OPENVINO_BACKEND,
        preferred_suffixes=(".xml", ".onnx"),
    ),
    "patchcore": MVTecModelPresetSpec(
        preset="patchcore",
        label="PatchCore",
        description="经典强基线，适合对比和离线评估。",
        checkpoint_env="KGTRACEVIS_MVTEC_PATCHCORE_CHECKPOINT",
        default_checkpoint=DEFAULT_MVTEC_PATCHCORE_CHECKPOINT,
        backend_hint=ANOMALIB_TORCH_BACKEND,
        preferred_suffixes=(".pt", ".pth", ".ckpt"),
    ),
    "efficientad": MVTecModelPresetSpec(
        preset="efficientad",
        label="EfficientAD",
        description="更偏实时 demo 的推荐模型，如果有可用权重优先选它。",
        checkpoint_env="KGTRACEVIS_MVTEC_EFFICIENTAD_CHECKPOINT",
        default_checkpoint=DEFAULT_MVTEC_EFFICIENTAD_CHECKPOINT,
        backend_hint=ANOMALIB_TORCH_BACKEND,
        preferred_suffixes=(".pt", ".pth", ".ckpt"),
    ),
}


def list_mvtec_model_presets() -> list[dict[str, Any]]:
    """Return all preset options for the web UI, including auto-selection."""
    resolved = {preset: _selection_for_preset(preset) for preset in MVTEC_MODEL_PRESET_PRIORITY}
    selected_auto = _best_available_selection(resolved)
    presets: list[dict[str, Any]] = [
        {
            "preset": "auto",
            "label": "自动",
            "description": "优先选择 EfficientAD，其次 PatchCore，再其次 STFPM。",
            "available": selected_auto is not None,
            "recommended": True,
            "backend": selected_auto.backend if selected_auto is not None else None,
            "checkpoint_path": (
                str(selected_auto.checkpoint_path) if selected_auto is not None else None
            ),
            "resolved_preset": selected_auto.preset if selected_auto is not None else None,
            "resolved_label": selected_auto.label if selected_auto is not None else None,
        }
    ]
    for preset in MVTEC_MODEL_PRESET_PRIORITY:
        selection = resolved[preset]
        presets.append(
            {
                "preset": selection.preset,
                "label": selection.label,
                "description": selection.description,
                "available": selection.available,
                "recommended": selection.preset == "efficientad",
                "backend": selection.backend,
                "checkpoint_path": str(selection.checkpoint_path) if selection.available else None,
                "checkpoint_hint": selection.checkpoint_hint,
            }
        )
    return presets


def resolve_mvtec_model_selection(model_preset: str | None = None) -> MVTecModelSelection:
    """Resolve a selectable MVTec model preset into a concrete checkpoint path."""
    normalized = _normalize_model_preset(model_preset)
    if normalized == "auto":
        resolved = {preset: _selection_for_preset(preset) for preset in MVTEC_MODEL_PRESET_PRIORITY}
        selected = _best_available_selection(resolved)
        if selected is not None:
            return selected
        raise FileNotFoundError(_missing_auto_message())

    selection = _selection_for_preset(cast(MVTecResolvedPreset, normalized))
    if not selection.available:
        raise FileNotFoundError(_missing_preset_message(selection))
    return selection


def _selection_for_preset(preset: MVTecResolvedPreset) -> MVTecModelSelection:
    spec = MVTEC_MODEL_PRESET_SPECS[preset]
    checkpoint_path = _resolve_checkpoint_path(spec)
    available = checkpoint_path.is_file()
    return MVTecModelSelection(
        preset=spec.preset,
        label=spec.label,
        description=spec.description,
        backend=_infer_backend(checkpoint_path, spec.backend_hint),
        checkpoint_path=checkpoint_path,
        available=available,
        checkpoint_hint=str(spec.default_checkpoint),
    )


def _resolve_checkpoint_path(spec: MVTecModelPresetSpec) -> Path:
    candidate = Path(os.environ.get(spec.checkpoint_env) or spec.default_checkpoint)
    if candidate.is_file():
        return candidate
    if candidate.is_dir():
        for suffix in spec.preferred_suffixes:
            matches = sorted(candidate.rglob(f"*{suffix}"))
            if matches:
                return matches[0]
    return candidate


def _infer_backend(checkpoint_path: Path, default_backend: str) -> str:
    if checkpoint_path.suffix.lower() == ".xml":
        return ANOMALIB_OPENVINO_BACKEND
    if checkpoint_path.suffix.lower() in {".pt", ".pth", ".ckpt"}:
        return ANOMALIB_TORCH_BACKEND
    return default_backend


def _best_available_selection(
    resolved: dict[MVTecResolvedPreset, MVTecModelSelection],
) -> MVTecModelSelection | None:
    for preset in MVTEC_MODEL_PRESET_PRIORITY:
        selection = resolved[preset]
        if selection.available:
            return selection
    return None


def _normalize_model_preset(value: str | None) -> MVTecModelPreset:
    normalized = (value or DEFAULT_MVTEC_MODEL_PRESET).strip().lower()
    if normalized == "":
        return DEFAULT_MVTEC_MODEL_PRESET
    if normalized == "auto":
        return "auto"
    if normalized in MVTEC_MODEL_PRESET_SPECS:
        return cast(MVTecModelPreset, normalized)
    supported = ", ".join(("auto", *MVTEC_MODEL_PRESET_PRIORITY))
    raise ValueError(f"model preset must be one of: {supported}")


def _missing_auto_message() -> str:
    hints = []
    for preset in MVTEC_MODEL_PRESET_PRIORITY:
        spec = MVTEC_MODEL_PRESET_SPECS[preset]
        hints.append(f"{spec.preset}: {spec.checkpoint_env} or {spec.default_checkpoint}")
    joined = "; ".join(hints)
    return (
        "No MVTec image model checkpoint is available. "
        f"Set one of the configured checkpoints, for example: {joined}."
    )


def _missing_preset_message(selection: MVTecModelSelection) -> str:
    spec = MVTEC_MODEL_PRESET_SPECS[selection.preset]
    return (
        f"MVTec model preset '{selection.preset}' is not available. "
        f"Set {spec.checkpoint_env} or place a checkpoint at {spec.default_checkpoint}."
    )
