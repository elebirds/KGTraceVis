"""Run a local real-model pipeline from public inputs to KGTracePipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kgtracevis.producers.model_assets import (
    DEFAULT_WM811K_INPUT_FILE,
    DEFAULT_WM811K_INPUT_REPO,
    DEFAULT_WM811K_INPUT_REPO_TYPE,
)
from kgtracevis.workflows.real_model_pipeline import (
    DEFAULT_MVTEC_CHECKPOINT,
    DEFAULT_MVTEC_IMAGE,
    DEFAULT_MVTEC_IMAGE_REPO,
    DEFAULT_MVTEC_REPO,
    DEFAULT_WM811K_CHECKPOINT,
    DEFAULT_WM811K_REPO,
    RealModelPipelineConfig,
    run_real_model_pipeline,
)


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
    result = run_real_model_pipeline(
        RealModelPipelineConfig(
            output_root=args.output_root,
            mvtec_repo=args.mvtec_repo,
            mvtec_checkpoint=args.mvtec_checkpoint,
            mvtec_image_repo=args.mvtec_image_repo,
            mvtec_image=args.mvtec_image,
            wm811k_repo=args.wm811k_repo,
            wm811k_checkpoint=args.wm811k_checkpoint,
            wm811k_input_repo=args.wm811k_input_repo,
            wm811k_input_file=args.wm811k_input_file,
            wm811k_input_repo_type=args.wm811k_input_repo_type,
            overwrite=args.overwrite,
        )
    )
    print(json.dumps(result.summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
