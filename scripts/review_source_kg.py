"""Apply one review decision to source-to-KG construction artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kgtracevis.workflows.kg_construction_review import (
    ReviewKGConstructionEdgeConfig,
    ReviewKGConstructionItemConfig,
    review_kg_construction_edge_artifact,
    review_kg_construction_item_artifact,
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
        help=(
            "Stable review target key. Edge keys use head|relation|tail|scenario; "
            "non-edge keys come from review_queue.json."
        ),
    )
    parser.add_argument(
        "--item-type",
        default="edge",
        help="Review item type from review_queue.json; defaults to edge.",
    )
    parser.add_argument(
        "--proposed-payload-json",
        help="Optional JSON object to merge into the reviewed item candidate payload.",
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
        proposed_payload = _parse_payload(args.proposed_payload_json)
        if args.item_type == "edge":
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
                    proposed_payload=proposed_payload,
                )
            )
            payload = {
                "run_id": result.run_id,
                "action": result.decision.action,
                "target_key": result.decision.target_key,
                "item_type": "edge",
                "edge_review_status": result.edge.get("review_status"),
                "review_status": result.edge.get("review_status"),
                "review_decisions_path": str(result.review_decisions_path),
                "published_nodes_path": str(result.published_nodes_path),
                "published_edges_path": str(result.published_edges_path),
                "publish_report_path": str(result.publish_report_path),
                "diff_path": str(result.diff_path),
            }
        else:
            if args.target_key is None:
                raise ValueError("--target-key is required for non-edge review items")
            if any((args.head, args.relation, args.tail, args.scenario)):
                raise ValueError("edge parts are only supported when --item-type=edge")
            item_result = review_kg_construction_item_artifact(
                ReviewKGConstructionItemConfig(
                    output_dir=args.build_dir,
                    action=args.action,
                    target_key=args.target_key,
                    item_type=args.item_type,
                    reviewer=args.reviewer,
                    note=args.note,
                    proposed_payload=proposed_payload,
                )
            )
            payload = {
                "run_id": item_result.run_id,
                "action": item_result.decision.action,
                "target_key": item_result.decision.target_key,
                "item_type": item_result.decision.target_type,
                "review_status": item_result.item.get("review_status"),
                "review_decisions_path": str(item_result.review_decisions_path),
                "published_nodes_path": str(item_result.published_nodes_path),
                "published_edges_path": str(item_result.published_edges_path),
                "publish_report_path": str(item_result.publish_report_path),
                "diff_path": str(item_result.diff_path),
            }
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    print(json.dumps(payload, indent=2, sort_keys=True))


def _parse_payload(value: str | None) -> dict[str, object]:
    if not value:
        return {}
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("--proposed-payload-json must be a JSON object")
    return {str(key): item for key, item in payload.items()}


if __name__ == "__main__":
    main()
