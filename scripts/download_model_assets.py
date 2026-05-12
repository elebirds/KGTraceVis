"""Download trusted public model assets for local KGTraceVis runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kgtracevis.producers.model_assets import (
    DEFAULT_DOWNLOAD_MODEL_ASSETS,
    DEFAULT_MVTEC_EFFICIENTAD_FILE,
    DEFAULT_MVTEC_EFFICIENTAD_REPO,
    DEFAULT_MVTEC_PATCHCORE_FILE,
    DEFAULT_MVTEC_PATCHCORE_REPO,
    DEFAULT_MVTEC_STFPM_FILE,
    DEFAULT_MVTEC_STFPM_REPO,
    DEFAULT_WM811K_FILE,
    DEFAULT_WM811K_REPO,
    MODEL_ASSET_CHOICES,
    ModelAsset,
    download_selected_model_assets,
)

DEFAULT_OUTPUT_ROOT = Path("runs/real_model_pipeline")


def parse_args() -> argparse.Namespace:
    """Parse model asset download options."""
    parser = argparse.ArgumentParser(
        description="Download the default public model weights used by KGTraceVis."
    )
    parser.add_argument("--output-root", default=DEFAULT_OUTPUT_ROOT, type=Path)
    parser.add_argument(
        "--model",
        choices=MODEL_ASSET_CHOICES,
        action="append",
        help=(
            "Model asset to download. Repeat to select multiple. Defaults to assets "
            "with built-in trusted sources."
        ),
    )
    parser.add_argument("--mvtec-efficientad-repo", default=DEFAULT_MVTEC_EFFICIENTAD_REPO)
    parser.add_argument("--mvtec-efficientad-file", default=DEFAULT_MVTEC_EFFICIENTAD_FILE)
    parser.add_argument("--mvtec-patchcore-repo", default=DEFAULT_MVTEC_PATCHCORE_REPO)
    parser.add_argument("--mvtec-patchcore-file", default=DEFAULT_MVTEC_PATCHCORE_FILE)
    parser.add_argument("--mvtec-stfpm-repo", default=DEFAULT_MVTEC_STFPM_REPO)
    parser.add_argument("--mvtec-stfpm-file", default=DEFAULT_MVTEC_STFPM_FILE)
    parser.add_argument("--wm811k-repo", default=DEFAULT_WM811K_REPO)
    parser.add_argument("--wm811k-file", default=DEFAULT_WM811K_FILE)
    parser.add_argument("--force", action="store_true", help="Re-download and replace assets.")
    return parser.parse_args()


def main() -> None:
    """Download selected assets and print a JSON summary."""
    args = parse_args()
    selected: tuple[ModelAsset, ...] = tuple(args.model or DEFAULT_DOWNLOAD_MODEL_ASSETS)
    output_root: Path = args.output_root
    summary = download_selected_model_assets(
        models=selected,
        assets_root=output_root / "assets",
        force=args.force,
        mvtec_efficientad_repo=args.mvtec_efficientad_repo,
        mvtec_efficientad_file=args.mvtec_efficientad_file,
        mvtec_patchcore_repo=args.mvtec_patchcore_repo,
        mvtec_patchcore_file=args.mvtec_patchcore_file,
        mvtec_stfpm_repo=args.mvtec_stfpm_repo,
        mvtec_stfpm_file=args.mvtec_stfpm_file,
        wm811k_repo=args.wm811k_repo,
        wm811k_file=args.wm811k_file,
    )
    summary["output_root"] = str(output_root)

    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
