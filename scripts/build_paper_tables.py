"""Build paper-facing grouped manifests from generated v0 experiment artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kgtracevis.experiments.paper_tables import (
    DEFAULT_ADAPTER_SUMMARY_PATHS,
    DEFAULT_NOISE_SUMMARY_PATH,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_SUITE_SUMMARY_PATH,
    build_paper_tables,
)


def parse_args() -> argparse.Namespace:
    """Parse paper table builder arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        type=Path,
        help="Directory for generated paper-facing manifests.",
    )
    parser.add_argument(
        "--adapter-summary",
        dest="adapter_summaries",
        action="append",
        type=Path,
        help=(
            "Adapter pipeline summary JSON. May be passed multiple times; defaults "
            "to the current v0 suite MVTec and WM811K outputs."
        ),
    )
    parser.add_argument(
        "--noise-summary",
        default=DEFAULT_NOISE_SUMMARY_PATH,
        type=Path,
        help="Noise experiment summary JSON.",
    )
    parser.add_argument(
        "--suite-summary",
        default=DEFAULT_SUITE_SUMMARY_PATH,
        type=Path,
        help="Consolidated experiment suite summary JSON for command provenance.",
    )
    parser.add_argument(
        "--examples-dir",
        default=Path("data/examples"),
        type=Path,
        help="Checked-in example Evidence JSON directory used to infer noise datasets.",
    )
    parser.add_argument(
        "--references-dir",
        default=Path("data/references"),
        type=Path,
        help="Reference CSV directory used to infer annotation/reference types.",
    )
    parser.add_argument("--overwrite", action="store_true", help="Replace existing outputs.")
    return parser.parse_args()


def main() -> None:
    """Build grouped manifests and print compact output paths."""
    args = parse_args()
    adapter_summaries = args.adapter_summaries or list(DEFAULT_ADAPTER_SUMMARY_PATHS)
    output = build_paper_tables(
        output_dir=args.output_dir,
        adapter_summary_paths=adapter_summaries,
        noise_summary_path=args.noise_summary,
        suite_summary_path=args.suite_summary,
        examples_dir=args.examples_dir,
        references_dir=args.references_dir,
        overwrite=args.overwrite,
    )
    print(
        json.dumps(
            {
                "output_dir": str(output.output_dir),
                "manifest_path": str(output.manifest_path),
                "command_manifest_path": str(output.command_manifest_path),
                "summary_path": str(output.summary_path),
                "manifest_row_count": len(output.manifest_rows),
                "command_row_count": len(output.command_rows),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
