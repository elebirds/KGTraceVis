"""Workflow for running public real-model assets through KGTracePipeline."""

from __future__ import annotations

import json
import shutil
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kgtracevis.experiments.adapter_pipeline import run_adapter_pipeline
from kgtracevis.producers import (
    ANOMALIB_OPENVINO_BACKEND,
    TORCH_RESNET_BACKEND,
    AnomalibMVTecBackend,
    TorchWM811KBackend,
    build_mvtec_records,
    build_wm811k_records,
    write_jsonl_records,
)
from kgtracevis.producers.model_assets import (
    DEFAULT_WM811K_INPUT_FILE,
    DEFAULT_WM811K_INPUT_REPO,
    DEFAULT_WM811K_INPUT_REPO_TYPE,
    download_wm811k_input_table,
    download_wm811k_resnet,
)

DEFAULT_MVTEC_REPO = "alexsu52/stfpm_mvtec_capsule"
DEFAULT_MVTEC_CHECKPOINT = "openvino_model.tar"
DEFAULT_MVTEC_IMAGE_REPO = "NTHoang2103/patchcore-mvtec-models"
DEFAULT_MVTEC_IMAGE = "clean/capsule/Patchcore/mvtec/capsule/v0/images/crack/000.png"
DEFAULT_WM811K_REPO = "radai-agent/radai-wm811k-defect-detection"
DEFAULT_WM811K_CHECKPOINT = "best_radai_resnet.pt"


@dataclass(frozen=True)
class RealModelPipelineConfig:
    """Configuration for the public real-model pipeline workflow."""

    output_root: Path = Path("runs/real_model_pipeline")
    mvtec_repo: str = DEFAULT_MVTEC_REPO
    mvtec_checkpoint: str = DEFAULT_MVTEC_CHECKPOINT
    mvtec_image_repo: str = DEFAULT_MVTEC_IMAGE_REPO
    mvtec_image: str = DEFAULT_MVTEC_IMAGE
    wm811k_repo: str = DEFAULT_WM811K_REPO
    wm811k_checkpoint: str = DEFAULT_WM811K_CHECKPOINT
    wm811k_input_repo: str = DEFAULT_WM811K_INPUT_REPO
    wm811k_input_file: str = DEFAULT_WM811K_INPUT_FILE
    wm811k_input_repo_type: str = DEFAULT_WM811K_INPUT_REPO_TYPE
    overwrite: bool = False


@dataclass(frozen=True)
class RealModelPipelineResult:
    """Structured result for a real-model pipeline workflow run."""

    output_path: Path
    output_root: Path
    summary: dict[str, Any]


def run_real_model_pipeline(config: RealModelPipelineConfig) -> RealModelPipelineResult:
    """Run public MVTec and WM811K model assets through the adapter pipeline."""
    output_root = config.output_root
    assets_root = output_root / "assets"
    mvtec_assets = assets_root / "mvtec"
    wm811k_assets = assets_root / "wm811k"
    mvtec_assets.mkdir(parents=True, exist_ok=True)
    wm811k_assets.mkdir(parents=True, exist_ok=True)

    mvtec_summary = _run_mvtec_pipeline(config, mvtec_assets=mvtec_assets)
    wm811k_summary = _run_wm811k_pipeline(config, wm811k_assets=wm811k_assets)

    summary = {
        "artifact_type": "real_model_pipeline_v0",
        "output_root": str(output_root),
        "mvtec": mvtec_summary,
        "wm811k": wm811k_summary,
        "claim_boundary": (
            "real-model pipeline path produces candidate/plausible explanation outputs; "
            "it does not claim verified root cause"
        ),
    }
    summary_path = output_root / "summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return RealModelPipelineResult(
        output_path=summary_path,
        output_root=output_root,
        summary=summary,
    )


def _run_mvtec_pipeline(
    config: RealModelPipelineConfig,
    *,
    mvtec_assets: Path,
) -> dict[str, Any]:
    mvtec_checkpoint = _download_openvino_checkpoint(
        config.mvtec_repo,
        config.mvtec_checkpoint,
        mvtec_assets / "checkpoints",
    )
    mvtec_image = _download_hf_file(
        config.mvtec_image_repo,
        config.mvtec_image,
        mvtec_assets / "images",
    )
    mvtec_input_root = mvtec_assets / "input_root"
    shutil.rmtree(mvtec_input_root, ignore_errors=True)
    mvtec_input_image = mvtec_input_root / "capsule" / "test" / "crack" / "000.png"
    mvtec_input_image.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(mvtec_image, mvtec_input_image)
    _resize_image(mvtec_input_image, (256, 256))

    mvtec_predictor = AnomalibMVTecBackend(
        backend=ANOMALIB_OPENVINO_BACKEND,
        checkpoint=mvtec_checkpoint,
        device="CPU",
    )
    mvtec_records = build_mvtec_records(
        mvtec_input_root,
        mvtec_predictor,
        output_dir=mvtec_assets / "generated_records",
        model_backend=ANOMALIB_OPENVINO_BACKEND,
        checkpoint=mvtec_checkpoint,
        threshold=0.5,
        max_cases=1,
        include_good=False,
    )
    mvtec_records_path = write_jsonl_records(
        mvtec_records,
        mvtec_assets / "mvtec_records.jsonl",
        overwrite=True,
    )
    mvtec_pipeline = run_adapter_pipeline(
        mvtec_records_path,
        mvtec_assets / "adapter_pipeline",
        dataset="mvtec",
        top_k=3,
        overwrite=True,
    )
    return {
        "checkpoint": str(mvtec_checkpoint),
        "image": str(mvtec_input_image),
        "records": str(mvtec_records_path),
        "adapter_summary": str(mvtec_pipeline.summary_path),
        "adapter_table": str(mvtec_pipeline.table_path),
        "case_count": mvtec_pipeline.summary["case_count"],
    }


def _run_wm811k_pipeline(
    config: RealModelPipelineConfig,
    *,
    wm811k_assets: Path,
) -> dict[str, Any]:
    wm811k_checkpoint_summary = download_wm811k_resnet(
        repo_id=config.wm811k_repo,
        filename=config.wm811k_checkpoint,
        destination_dir=wm811k_assets / "checkpoints",
        force=config.overwrite,
    )
    wm811k_checkpoint = Path(str(wm811k_checkpoint_summary["checkpoint"]))
    wm811k_input_summary = download_wm811k_input_table(
        repo_id=config.wm811k_input_repo,
        filename=config.wm811k_input_file,
        repo_type=config.wm811k_input_repo_type,
        destination_dir=wm811k_assets / "input_tables",
        force=config.overwrite,
    )
    wm811k_input = Path(str(wm811k_input_summary["input_table"]))
    wm811k_predictor = TorchWM811KBackend(
        checkpoint=wm811k_checkpoint,
        device="auto",
        model_source=config.wm811k_repo,
        model_file=config.wm811k_checkpoint,
    )
    wm811k_records = build_wm811k_records(
        wm811k_input,
        wm811k_predictor,
        output_dir=wm811k_assets / "generated_records",
        model_backend=TORCH_RESNET_BACKEND,
        checkpoint=wm811k_checkpoint,
        threshold=0.5,
        max_cases=1,
        include_unlabeled=False,
    )
    wm811k_records_path = write_jsonl_records(
        wm811k_records,
        wm811k_assets / "wm811k_records.jsonl",
        overwrite=True,
    )
    wm811k_pipeline = run_adapter_pipeline(
        wm811k_records_path,
        wm811k_assets / "adapter_pipeline",
        dataset="wafer",
        top_k=3,
        overwrite=True,
    )
    return {
        "checkpoint": str(wm811k_checkpoint),
        "checkpoint_source": {
            "repo_id": wm811k_checkpoint_summary["repo_id"],
            "filename": wm811k_checkpoint_summary["filename"],
            "backend": wm811k_checkpoint_summary["backend"],
        },
        "input_table": str(wm811k_input),
        "input_source": {
            "source_repo": wm811k_input_summary["source_repo"],
            "filename": wm811k_input_summary["filename"],
            "repo_type": wm811k_input_summary["repo_type"],
        },
        "records": str(wm811k_records_path),
        "adapter_summary": str(wm811k_pipeline.summary_path),
        "adapter_table": str(wm811k_pipeline.table_path),
        "case_count": wm811k_pipeline.summary["case_count"],
    }


def _download_hf_file(
    repo_id: str,
    filename: str,
    destination_dir: Path,
    *,
    repo_type: str | None = None,
) -> Path:
    """Download one file from the Hugging Face Hub into a local asset directory."""
    from huggingface_hub import hf_hub_download

    destination_dir.mkdir(parents=True, exist_ok=True)
    cached_path = Path(
        hf_hub_download(repo_id=repo_id, filename=filename, repo_type=repo_type)
    )
    destination = destination_dir / filename.replace("/", "__")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(cached_path, destination)
    return destination


def _download_openvino_checkpoint(repo_id: str, filename: str, destination_dir: Path) -> Path:
    """Download and extract an OpenVINO tarball, returning the XML checkpoint path."""
    tar_path = _download_hf_file(repo_id, filename, destination_dir)
    extract_dir = destination_dir / tar_path.stem
    extract_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tar_path) as archive:
        archive.extractall(extract_dir)
    xml_files = sorted(extract_dir.rglob("*.xml"))
    if not xml_files:
        raise FileNotFoundError(f"no OpenVINO XML checkpoint found in {tar_path}")
    return xml_files[0]


def _resize_image(image_path: Path, size: tuple[int, int]) -> None:
    """Resize a sample image in place for model input compatibility."""
    import cv2

    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError(f"failed to read image for resizing: {image_path}")
    resized = cv2.resize(image, size, interpolation=cv2.INTER_AREA)
    if not cv2.imwrite(str(image_path), resized):
        raise ValueError(f"failed to write resized image: {image_path}")
