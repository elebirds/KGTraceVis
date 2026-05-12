"""Run a local real-model pipeline from public inputs to KGTracePipeline."""

from __future__ import annotations

import argparse
import json
import shutil
import tarfile
from pathlib import Path

import cv2
from huggingface_hub import hf_hub_download

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


def parse_args() -> argparse.Namespace:
    """Parse real pipeline run options."""
    parser = argparse.ArgumentParser(
        description=(
            "Download ready-to-run public models and public inputs, then run the "
            "full producer/adaptor/pipeline path."
        )
    )
    parser.add_argument("--output-root", default="runs/real_model_pipeline", type=Path)
    parser.add_argument("--mvtec-repo", default=DEFAULT_MVTEC_REPO)
    parser.add_argument("--mvtec-checkpoint", default=DEFAULT_MVTEC_CHECKPOINT)
    parser.add_argument("--mvtec-image-repo", default=DEFAULT_MVTEC_IMAGE_REPO)
    parser.add_argument("--mvtec-image", default=DEFAULT_MVTEC_IMAGE)
    parser.add_argument("--wm811k-repo", default=DEFAULT_WM811K_REPO)
    parser.add_argument("--wm811k-checkpoint", default=DEFAULT_WM811K_CHECKPOINT)
    parser.add_argument("--wm811k-input-repo", default=DEFAULT_WM811K_INPUT_REPO)
    parser.add_argument("--wm811k-input-file", default=DEFAULT_WM811K_INPUT_FILE)
    parser.add_argument("--wm811k-input-repo-type", default=DEFAULT_WM811K_INPUT_REPO_TYPE)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    """Run the real-data path and print a compact artifact summary."""
    args = parse_args()
    output_root: Path = args.output_root
    assets_root = output_root / "assets"
    mvtec_assets = assets_root / "mvtec"
    wm811k_assets = assets_root / "wm811k"
    mvtec_assets.mkdir(parents=True, exist_ok=True)
    wm811k_assets.mkdir(parents=True, exist_ok=True)

    mvtec_checkpoint = _download_openvino_checkpoint(
        args.mvtec_repo,
        args.mvtec_checkpoint,
        mvtec_assets / "checkpoints",
    )
    mvtec_image = _download_hf_file(
        args.mvtec_image_repo,
        args.mvtec_image,
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

    wm811k_checkpoint_summary = download_wm811k_resnet(
        repo_id=args.wm811k_repo,
        filename=args.wm811k_checkpoint,
        destination_dir=wm811k_assets / "checkpoints",
        force=args.overwrite,
    )
    wm811k_checkpoint = Path(str(wm811k_checkpoint_summary["checkpoint"]))
    wm811k_input_summary = download_wm811k_input_table(
        repo_id=args.wm811k_input_repo,
        filename=args.wm811k_input_file,
        repo_type=args.wm811k_input_repo_type,
        destination_dir=wm811k_assets / "input_tables",
        force=args.overwrite,
    )
    wm811k_input = Path(str(wm811k_input_summary["input_table"]))
    wm811k_predictor = TorchWM811KBackend(
        checkpoint=wm811k_checkpoint,
        device="auto",
        model_source=args.wm811k_repo,
        model_file=args.wm811k_checkpoint,
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

    summary = {
        "artifact_type": "real_model_pipeline_v0",
        "output_root": str(output_root),
        "mvtec": {
            "checkpoint": str(mvtec_checkpoint),
            "image": str(mvtec_input_image),
            "records": str(mvtec_records_path),
            "adapter_summary": str(mvtec_pipeline.summary_path),
            "adapter_table": str(mvtec_pipeline.table_path),
            "case_count": mvtec_pipeline.summary["case_count"],
        },
        "wm811k": {
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
        },
        "claim_boundary": (
            "real-model pipeline path produces candidate/plausible explanation outputs; "
            "it does not claim verified root cause"
        ),
    }
    summary_path = output_root / "summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


def _download_hf_file(
    repo_id: str,
    filename: str,
    destination_dir: Path,
    *,
    repo_type: str | None = None,
) -> Path:
    """Download one file from the Hugging Face Hub into a local asset directory."""
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
    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError(f"failed to read image for resizing: {image_path}")
    resized = cv2.resize(image, size, interpolation=cv2.INTER_AREA)
    if not cv2.imwrite(str(image_path), resized):
        raise ValueError(f"failed to write resized image: {image_path}")


if __name__ == "__main__":
    main()
