"""Trusted public producer asset download helpers."""

from __future__ import annotations

import os
import shutil
import tarfile
from pathlib import Path
from typing import Any, Literal

from kgtracevis.producers.backends import (
    TORCH_RESNET_BACKEND,
    WM811K_CLASSES,
    WM811K_RESNET_MODEL_FILE,
    WM811K_RESNET_MODEL_SOURCE,
)

ModelAsset = Literal["mvtec-efficientad", "mvtec-patchcore", "mvtec-stfpm", "wm811k-resnet"]

DEFAULT_MODEL_ASSETS_ROOT = Path("runs/real_model_pipeline/assets")
DEFAULT_MVTEC_EFFICIENTAD_REPO = ""
DEFAULT_MVTEC_EFFICIENTAD_FILE = "mvtec_efficientad.pt"
DEFAULT_MVTEC_PATCHCORE_REPO = "NTHoang2103/patchcore-mvtec-models"
DEFAULT_MVTEC_PATCHCORE_FILE = (
    "clean/capsule/Patchcore/mvtec/capsule/v0/weights/lightning/model.ckpt"
)
DEFAULT_MVTEC_STFPM_REPO = "alexsu52/stfpm_mvtec_capsule"
DEFAULT_MVTEC_STFPM_FILE = "openvino_model.tar"
DEFAULT_WM811K_REPO = WM811K_RESNET_MODEL_SOURCE
DEFAULT_WM811K_FILE = WM811K_RESNET_MODEL_FILE
DEFAULT_WM811K_INPUT_REPO = "lslattery/wafer-defect-detection"
DEFAULT_WM811K_INPUT_FILE = "test.pkl"
DEFAULT_WM811K_INPUT_REPO_TYPE = "dataset"
MODEL_ASSET_CHOICES: tuple[ModelAsset, ...] = (
    "mvtec-efficientad",
    "mvtec-patchcore",
    "mvtec-stfpm",
    "wm811k-resnet",
)
DEFAULT_DOWNLOAD_MODEL_ASSETS: tuple[ModelAsset, ...] = (
    "mvtec-patchcore",
    "mvtec-stfpm",
    "wm811k-resnet",
)


def download_selected_model_assets(
    *,
    models: tuple[ModelAsset, ...] = DEFAULT_DOWNLOAD_MODEL_ASSETS,
    assets_root: str | Path = DEFAULT_MODEL_ASSETS_ROOT,
    force: bool = False,
    mvtec_efficientad_repo: str = DEFAULT_MVTEC_EFFICIENTAD_REPO,
    mvtec_efficientad_file: str = DEFAULT_MVTEC_EFFICIENTAD_FILE,
    mvtec_patchcore_repo: str = DEFAULT_MVTEC_PATCHCORE_REPO,
    mvtec_patchcore_file: str = DEFAULT_MVTEC_PATCHCORE_FILE,
    mvtec_stfpm_repo: str = DEFAULT_MVTEC_STFPM_REPO,
    mvtec_stfpm_file: str = DEFAULT_MVTEC_STFPM_FILE,
    wm811k_repo: str = DEFAULT_WM811K_REPO,
    wm811k_file: str = DEFAULT_WM811K_FILE,
    include_wm811k_data: bool = False,
    wm811k_input_repo: str = DEFAULT_WM811K_INPUT_REPO,
    wm811k_input_file: str = DEFAULT_WM811K_INPUT_FILE,
    wm811k_input_repo_type: str = DEFAULT_WM811K_INPUT_REPO_TYPE,
) -> dict[str, Any]:
    """Download selected trusted public producer assets and return a JSON-safe summary."""
    root = Path(assets_root)
    selected = _dedupe_models(models)
    summary: dict[str, Any] = {
        "artifact_type": "model_asset_download_v0",
        "assets_root": str(root),
        "assets": {},
        "data_assets": {},
    }

    if "mvtec-efficientad" in selected:
        summary["assets"]["mvtec_efficientad"] = download_mvtec_torch_checkpoint(
            preset="efficientad",
            repo_id=mvtec_efficientad_repo,
            filename=mvtec_efficientad_file,
            destination_dir=root / "mvtec" / "checkpoints",
            default_filename="mvtec_efficientad.pt",
            env="KGTRACEVIS_MVTEC_EFFICIENTAD_CHECKPOINT",
            force=force,
        )

    if "mvtec-patchcore" in selected:
        summary["assets"]["mvtec_patchcore"] = download_mvtec_torch_checkpoint(
            preset="patchcore",
            repo_id=mvtec_patchcore_repo,
            filename=mvtec_patchcore_file,
            destination_dir=root / "mvtec" / "checkpoints",
            default_filename="mvtec_patchcore.ckpt",
            env="KGTRACEVIS_MVTEC_PATCHCORE_CHECKPOINT",
            force=force,
        )

    if "mvtec-stfpm" in selected:
        summary["assets"]["mvtec_stfpm"] = download_mvtec_stfpm(
            repo_id=mvtec_stfpm_repo,
            filename=mvtec_stfpm_file,
            destination_dir=root / "mvtec" / "checkpoints",
            force=force,
        )

    if "wm811k-resnet" in selected:
        summary["assets"]["wm811k_resnet"] = download_wm811k_resnet(
            repo_id=wm811k_repo,
            filename=wm811k_file,
            destination_dir=root / "wm811k" / "checkpoints",
            force=force,
        )

    if include_wm811k_data:
        summary["data_assets"]["wm811k_input_table"] = download_wm811k_input_table(
            repo_id=wm811k_input_repo,
            filename=wm811k_input_file,
            repo_type=wm811k_input_repo_type,
            destination_dir=root / "wm811k" / "input_tables",
            force=force,
        )

    return summary


def download_mvtec_torch_checkpoint(
    *,
    preset: Literal["efficientad", "patchcore"],
    repo_id: str,
    filename: str,
    destination_dir: str | Path = DEFAULT_MODEL_ASSETS_ROOT / "mvtec" / "checkpoints",
    default_filename: str,
    env: str,
    force: bool = False,
) -> dict[str, Any]:
    """Download a configurable Anomalib-compatible MVTec torch checkpoint."""
    resolved_repo = _required_source(
        repo_id,
        env_name=f"KGTRACEVIS_DOWNLOAD_MVTEC_{preset.upper()}_REPO",
        preset=preset,
    )
    resolved_filename = (
        os.environ.get(f"KGTRACEVIS_DOWNLOAD_MVTEC_{preset.upper()}_FILE")
        or filename
        or default_filename
    )
    checkpoint = _download_hf_file(
        resolved_repo,
        resolved_filename,
        Path(destination_dir),
        force=force,
        output_name=default_filename,
    )
    return {
        "repo_id": resolved_repo,
        "filename": resolved_filename,
        "checkpoint": str(checkpoint),
        "env": env,
        "preset": preset,
        "backend": "anomalib-engine" if preset == "patchcore" else "anomalib-torch",
    }


def download_mvtec_stfpm(
    *,
    repo_id: str = DEFAULT_MVTEC_STFPM_REPO,
    filename: str = DEFAULT_MVTEC_STFPM_FILE,
    destination_dir: str | Path = DEFAULT_MODEL_ASSETS_ROOT / "mvtec" / "checkpoints",
    force: bool = False,
) -> dict[str, Any]:
    """Download and extract the default STFPM OpenVINO MVTec checkpoint."""
    destination = Path(destination_dir)
    tar_path = destination / filename.replace("/", "__")
    extract_dir = destination / tar_path.stem
    xml_path = extract_dir / "stfpm_capsule.xml"

    if force or not xml_path.is_file():
        downloaded = _download_hf_file(repo_id, filename, destination, force=force)
        if downloaded != tar_path:
            tar_path = downloaded
            extract_dir = destination / tar_path.stem
            xml_path = extract_dir / "stfpm_capsule.xml"
        if force and extract_dir.exists():
            shutil.rmtree(extract_dir)
        extract_dir.mkdir(parents=True, exist_ok=True)
        _safe_extract_tar(tar_path, extract_dir)

    if not xml_path.is_file():
        xml_files = sorted(extract_dir.rglob("*.xml"))
        if not xml_files:
            raise FileNotFoundError(f"no OpenVINO XML checkpoint found in {extract_dir}")
        xml_path = xml_files[0]

    return {
        "repo_id": repo_id,
        "archive": str(tar_path),
        "checkpoint": str(xml_path),
        "env": "KGTRACEVIS_MVTEC_STFPM_CHECKPOINT",
        "preset": "stfpm",
    }


def download_wm811k_resnet(
    *,
    repo_id: str = DEFAULT_WM811K_REPO,
    filename: str = DEFAULT_WM811K_FILE,
    destination_dir: str | Path = DEFAULT_MODEL_ASSETS_ROOT / "wm811k" / "checkpoints",
    force: bool = False,
) -> dict[str, Any]:
    """Download the default WM811K ResNet checkpoint."""
    checkpoint = _download_hf_file(repo_id, filename, Path(destination_dir), force=force)
    return {
        "preset": "wm811k-resnet",
        "repo_id": repo_id,
        "filename": filename,
        "checkpoint": str(checkpoint),
        "env": "KGTRACEVIS_WM811K_CHECKPOINT",
        "backend": TORCH_RESNET_BACKEND,
        "classes": list(WM811K_CLASSES),
        "task": "defect_pattern_classification",
        "produces_root_cause": False,
    }


def download_wm811k_input_table(
    *,
    repo_id: str = DEFAULT_WM811K_INPUT_REPO,
    filename: str = DEFAULT_WM811K_INPUT_FILE,
    repo_type: str = DEFAULT_WM811K_INPUT_REPO_TYPE,
    destination_dir: str | Path = DEFAULT_MODEL_ASSETS_ROOT / "wm811k" / "input_tables",
    force: bool = False,
) -> dict[str, Any]:
    """Download the default public WM811K pandas-readable input table."""
    input_table = _download_hf_file(
        repo_id,
        filename,
        Path(destination_dir),
        force=force,
        repo_type=repo_type,
    )
    return {
        "dataset": "wm811k",
        "source_repo": repo_id,
        "repo_id": repo_id,
        "filename": filename,
        "repo_type": repo_type,
        "input_table": str(input_table),
        "table_format": Path(filename).suffix.lstrip(".") or "unknown",
        "claim_boundary": (
            "WM811K input rows and classifier outputs provide observed wafer-map "
            "defect-pattern evidence only; they are not verified root-cause labels."
        ),
    }


def _dedupe_models(models: tuple[ModelAsset, ...]) -> tuple[ModelAsset, ...]:
    selected: list[ModelAsset] = []
    for model in models:
        if model not in MODEL_ASSET_CHOICES:
            supported = ", ".join(MODEL_ASSET_CHOICES)
            raise ValueError(f"model asset must be one of: {supported}")
        if model not in selected:
            selected.append(model)
    return tuple(selected)


def _download_hf_file(
    repo_id: str,
    filename: str,
    destination_dir: Path,
    *,
    force: bool,
    output_name: str | None = None,
    repo_type: str | None = None,
) -> Path:
    """Download one file from Hugging Face Hub into a local asset directory."""
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:  # pragma: no cover - depends on optional extra.
        raise RuntimeError(
            "huggingface-hub is required to download model assets. "
            "Install the ml extra with: uv sync --extra ml"
        ) from exc

    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / (output_name or filename.replace("/", "__"))
    if destination.is_file() and not force:
        return destination
    download_kwargs: dict[str, Any] = {"repo_id": repo_id, "filename": filename}
    if repo_type:
        download_kwargs["repo_type"] = repo_type
    cached_path = Path(hf_hub_download(**download_kwargs))
    shutil.copy2(cached_path, destination)
    return destination


def _required_source(repo_id: str, *, env_name: str, preset: str) -> str:
    resolved = (repo_id or os.environ.get(env_name) or "").strip()
    if not resolved:
        raise ValueError(
            f"No default public download source is configured for MVTec {preset}. "
            f"Pass a trusted Hugging Face repo or set {env_name}."
        )
    return resolved


def _safe_extract_tar(tar_path: Path, destination_dir: Path) -> None:
    """Extract a tar archive without allowing path traversal."""
    with tarfile.open(tar_path) as archive:
        root = destination_dir.resolve()
        for member in archive.getmembers():
            if member.issym() or member.islnk():
                raise ValueError(f"unsafe link in tar archive: {member.name}")
            target = (destination_dir / member.name).resolve()
            if not target.is_relative_to(root):
                raise ValueError(f"unsafe path in tar archive: {member.name}")
        archive.extractall(destination_dir)
