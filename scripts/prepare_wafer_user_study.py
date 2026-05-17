"""Prepare wafer user-study fixtures, candidate graph artifacts, and an optional test run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kgtracevis.workflows.wafer_user_study import (
    DEFAULT_WAFER_USER_STUDY_BASELINE_PATH,
    DEFAULT_WAFER_USER_STUDY_EVIDENCE_PATH,
    DEFAULT_WAFER_USER_STUDY_GRAPH_DIR,
    DEFAULT_WAFER_USER_STUDY_MANIFEST_PATH,
    WaferUserStudyConfig,
    prepare_wafer_user_study,
)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--evidence",
        type=Path,
        default=DEFAULT_WAFER_USER_STUDY_EVIDENCE_PATH,
        help="Wafer evidence JSON used to generate the user-study run.",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=DEFAULT_WAFER_USER_STUDY_BASELINE_PATH,
        help="Human-readable baseline dossier for manual RCA comparison.",
    )
    parser.add_argument(
        "--graph-output-dir",
        type=Path,
        default=DEFAULT_WAFER_USER_STUDY_GRAPH_DIR,
        help="Output directory for KG Studio wafer graph artifacts.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_WAFER_USER_STUDY_MANIFEST_PATH,
        help="Summary manifest describing the prepared user-study assets.",
    )
    parser.add_argument(
        "--run-artifact-root",
        type=Path,
        default=Path("runs/rootlens_sessions"),
        help="Directory used for persisted run artifact files.",
    )
    parser.add_argument("--top-k", type=int, default=5, help="Top-k RCA depth for the test run.")
    parser.add_argument(
        "--reasoning-profile-id",
        default=None,
        help="Optional explicit reasoning profile used when creating the test run.",
    )
    parser.add_argument(
        "--graph-scope",
        choices=["full_runtime", "focused_anomaly"],
        default="full_runtime",
        help="Graph materialization mode. full_runtime writes the full wafer runtime slice; focused_anomaly writes a smaller anomaly-centered graph.",
    )
    parser.add_argument(
        "--graph-hops",
        type=int,
        default=2,
        help="Neighborhood depth around the focused wafer anomaly node when --graph-scope=focused_anomaly.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing generated user-study graph artifacts and manifest.",
    )
    parser.add_argument(
        "--skip-runtime-kg-import",
        action="store_true",
        help="Do not import the default KG layers into Neo4j.",
    )
    parser.add_argument(
        "--skip-run",
        action="store_true",
        help="Do not create a persisted wafer test run in Postgres.",
    )
    return parser.parse_args()


def main() -> None:
    """Prepare wafer user-study assets and print a summary."""
    args = parse_args()
    config = WaferUserStudyConfig(
        evidence_path=args.evidence.expanduser(),
        baseline_path=args.baseline.expanduser(),
        graph_output_dir=args.graph_output_dir.expanduser(),
        manifest_path=args.manifest.expanduser(),
        run_artifact_root=args.run_artifact_root.expanduser(),
        top_k=args.top_k,
        overwrite=args.overwrite,
        create_run=not args.skip_run,
        import_runtime_kg=not args.skip_runtime_kg_import,
        reasoning_profile_id=args.reasoning_profile_id,
        graph_scope=args.graph_scope,
        graph_hops=args.graph_hops,
    )
    result = prepare_wafer_user_study(config)
    print(
        json.dumps(
            {
                "evidence_path": result.evidence_path.as_posix(),
                "baseline_path": result.baseline_path.as_posix(),
                "graph_output_dir": result.graph_output_dir.as_posix(),
                "manifest_path": result.manifest_path.as_posix(),
                "run_id": result.run_id,
                "graph_summary": result.graph_summary,
                "runtime_kg_import": result.runtime_kg_import,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
