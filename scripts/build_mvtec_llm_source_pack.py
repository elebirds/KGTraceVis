"""Build a raw-material MVTec source pack for LLM KG construction."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kgtracevis.workflows.mvtec_llm_source_pack import (
    DEFAULT_DEFECT_SPECTRUM_DIR,
    DEFAULT_MVTEC_SOURCE_BUNDLE_DIR,
    MVTecLLMSourcePackConfig,
    build_mvtec_llm_source_pack,
)


def parse_args() -> argparse.Namespace:
    """Parse source-pack build arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("runs/mvtec_llm_source_pack"),
        help="Directory where copied source materials and manifests are written.",
    )
    parser.add_argument(
        "--mvtec-source-bundle-dir",
        type=Path,
        default=DEFAULT_MVTEC_SOURCE_BUNDLE_DIR,
        help="Directory containing downloaded MVTec/PatchCore source snapshots.",
    )
    parser.add_argument(
        "--defect-spectrum-dir",
        type=Path,
        default=DEFAULT_DEFECT_SPECTRUM_DIR,
        help="Defect Spectrum root containing DS-MVTec/DS-MVTec.md.",
    )
    parser.add_argument(
        "--no-patchcore",
        action="store_true",
        help="Exclude PatchCore abstract/model-boundary material from the pack.",
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    """Build the source pack and print a compact summary."""
    args = parse_args()
    result = build_mvtec_llm_source_pack(
        MVTecLLMSourcePackConfig(
            output_dir=args.output_dir,
            mvtec_source_bundle_dir=args.mvtec_source_bundle_dir,
            defect_spectrum_dir=args.defect_spectrum_dir,
            include_patchcore=not args.no_patchcore,
            overwrite=args.overwrite,
        )
    )
    print(
        json.dumps(
            {
                "artifact_type": "mvtec_llm_source_pack_result_v1",
                "source_pack_path": str(result.source_pack_path),
                "material_manifest_path": str(result.material_manifest_path),
                "copied_source_dir": str(result.copied_source_dir),
                "material_count": result.material_count,
                "material_ids": [
                    item["material_id"] for item in result.manifest["materials"]
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
