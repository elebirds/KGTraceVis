"""Build a wafer/WM811K source pack for LLM-assisted KG construction."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kgtracevis.workflows.wafer_llm_source_pack import (
    WaferLLMSourcePackConfig,
    build_wafer_llm_source_pack,
)


def parse_args() -> argparse.Namespace:
    """Parse wafer source-pack build arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("runs/wafer_llm_source_pack"),
    )
    parser.add_argument(
        "--wm811k-records",
        type=Path,
        default=Path("data/examples/records/wm811k_records.jsonl"),
    )
    parser.add_argument("--exclude-wm811k-records", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    """Build the source pack and print a compact JSON result."""
    args = parse_args()
    result = build_wafer_llm_source_pack(
        WaferLLMSourcePackConfig(
            output_dir=args.output_dir,
            wm811k_records_path=args.wm811k_records,
            include_wm811k_records=not args.exclude_wm811k_records,
            overwrite=bool(args.overwrite),
        )
    )
    print(
        json.dumps(
            {
                "artifact_type": "wafer_llm_source_pack_result_v1",
                "output_dir": str(result.output_dir),
                "source_pack_path": str(result.source_pack_path),
                "material_manifest_path": str(result.material_manifest_path),
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
