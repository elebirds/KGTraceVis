"""Download source provenance files for MVTec candidate KG construction."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kgtracevis.kg_construction.mvtec_source_bundle import (
    DEFAULT_MVTEC_SOURCE_DIR,
    download_mvtec_source_bundle,
)


def parse_args() -> argparse.Namespace:
    """Parse source-bundle download arguments."""
    parser = argparse.ArgumentParser(
        description="Download MVTec source provenance files for candidate KG construction."
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_MVTEC_SOURCE_DIR)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--include-binary",
        action="store_true",
        help="Also download raw PDF sources into output-dir/raw/.",
    )
    parser.add_argument("--timeout-seconds", type=int, default=30)
    return parser.parse_args()


def main() -> None:
    """Download source files and print a compact manifest summary."""
    args = parse_args()
    manifest = download_mvtec_source_bundle(
        args.output_dir,
        overwrite=args.overwrite,
        include_binary=args.include_binary,
        timeout_seconds=args.timeout_seconds,
    )
    print(
        json.dumps(
            {
                "manifest_path": str(args.output_dir / "manifest.json"),
                "output_dir": manifest["output_dir"],
                "source_count": len(manifest["sources"]),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
