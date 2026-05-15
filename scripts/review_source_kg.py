"""Apply one review decision to source-to-KG construction artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kgtracevis.workflows.kg_construction_review import (
    ReviewKGConstructionEdgeConfig,
    review_kg_construction_edge_artifact,
)


def parse_args() -> argparse.Namespace:
    """Parse source-KG review arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--build-dir",
        type=Path,
        required=True,
        help="Directory containing source-to-KG construction artifacts.",
    )
    parser.add_argument(
        "--action",
        choices=("accept", "reject"),
        required=True,
        help="Review action to apply.",
    )
    parser.add_argument(
        "--target-key",
        help="Stable edge target key: head|relation|tail|scenario.",
    )
    parser.add_argument("--head")
    parser.add_argument("--relation")
    parser.add_argument("--tail")
    parser.add_argument("--scenario")
    parser.add_argument("--reviewer")
    parser.add_argument("--note")
    return parser.parse_args()


def main() -> None:
    """Apply one review decision and print a concise JSON summary."""
    args = parse_args()
    try:
        result = review_kg_construction_edge_artifact(
            ReviewKGConstructionEdgeConfig(
                output_dir=args.build_dir,
                action=args.action,
                target_key=args.target_key,
                head=args.head,
                relation=args.relation,
                tail=args.tail,
                scenario=args.scenario,
                reviewer=args.reviewer,
                note=args.note,
            )
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    print(
        json.dumps(
            {
                "run_id": result.run_id,
                "action": result.decision.action,
                "target_key": result.decision.target_key,
                "edge_review_status": result.edge.get("review_status"),
                "review_decisions_path": str(result.review_decisions_path),
                "published_nodes_path": str(result.published_nodes_path),
                "published_edges_path": str(result.published_edges_path),
                "publish_report_path": str(result.publish_report_path),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
