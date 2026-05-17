"""Tests for construction build discovery compatibility."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from kgtracevis.service.kg_construction import get_kg_construction_build, list_kg_construction_builds


def test_list_kg_construction_builds_discovers_kg_construction_manifest_dirs(
    tmp_path: Path,
) -> None:
    """User-study style graph directories should appear in the build registry list."""
    build_dir = tmp_path / "wafer_user_study"
    build_dir.mkdir()

    _write_csv(
        build_dir / "nodes.csv",
        ["id", "name", "label", "scenario", "aliases", "description"],
        [
            {
                "id": "NearfullDefect",
                "name": "Nearfull defect",
                "label": "AnomalyType",
                "scenario": "wafer",
                "aliases": "nearfull",
                "description": "fixture node",
            }
        ],
    )
    _write_csv(
        build_dir / "edges.csv",
        [
            "head",
            "relation",
            "tail",
            "scenario",
            "source",
            "evidence",
            "confidence",
            "weight",
            "review_status",
            "feedback_count",
            "accepted_count",
            "rejected_count",
        ],
        [
            {
                "head": "NearfullDefect",
                "relation": "HAS_PLAUSIBLE_CAUSE",
                "tail": "GlueRemovalInsufficient",
                "scenario": "wafer",
                "source": "fixture",
                "evidence": "fixture evidence",
                "confidence": "0.78",
                "weight": "0.22",
                "review_status": "reviewed",
                "feedback_count": "0",
                "accepted_count": "0",
                "rejected_count": "0",
            }
        ],
    )
    (build_dir / "kg_construction_summary.json").write_text(
        json.dumps(
            {
                "artifact_type": "wafer_user_study_graph_v1",
                "status": "ready",
                "created_at": "2026-05-17T00:00:00+00:00",
                "node_count": 1,
                "edge_count": 1,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (build_dir / "kg_construction_manifest.json").write_text(
        json.dumps(
            {
                "artifact_type": "wafer_user_study_graph_v1",
                "run": {"run_id": "wafer_user_study:nearfull"},
                "summary": {"node_count": 1, "edge_count": 1},
                "sources": [],
                "artifacts": {},
                "draft_rows": [],
                "review_decisions": [],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    payload = list_kg_construction_builds(build_root=tmp_path)

    assert [build.run_id for build in payload.builds] == ["wafer_user_study:nearfull"]
    build = payload.builds[0]
    assert build.summary_path.endswith("kg_construction_summary.json")
    assert build.manifest_path.endswith("kg_construction_manifest.json")
    assert build.edge_count == 1
    assert build.review_status_counts == {"reviewed": 1}

    detail = get_kg_construction_build("wafer_user_study:nearfull", build_root=tmp_path)
    assert detail.build.run_id == "wafer_user_study:nearfull"
    assert detail.summary["artifact_type"] == "wafer_user_study_graph_v1"


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
