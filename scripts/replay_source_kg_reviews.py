"""Replay source-to-KG construction review decisions through the build pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kgtracevis.workflows.kg_construction_replay import (
    ReplayKGConstructionReviewsConfig,
    replay_kg_construction_reviews,
)


def parse_args() -> argparse.Namespace:
    """Parse review replay arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--build-dir",
        type=Path,
        required=True,
        help="Directory containing source-to-KG construction artifacts.",
    )
    parser.add_argument("--run-id", help="Optional run ID override for replay output.")
    return parser.parse_args()


def main() -> None:
    """Replay review decisions and print a JSON summary."""
    args = parse_args()
    try:
        result = replay_kg_construction_reviews(
            ReplayKGConstructionReviewsConfig(
                output_dir=args.build_dir,
                run_id=args.run_id,
            )
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(
        json.dumps(
            {
                "run_id": result.run_id,
                "output_dir": str(result.output_dir),
                "decision_count": result.decision_count,
                "replayed_target_type_counts": result.replayed_target_type_counts,
                "summary_path": str(result.build_result.summary_path),
                "manifest_path": str(result.build_result.manifest_path),
                "nodes_path": str(result.build_result.nodes_path),
                "edges_path": str(result.build_result.edges_path),
                "review_queue_path": str(result.build_result.review_queue_path),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
