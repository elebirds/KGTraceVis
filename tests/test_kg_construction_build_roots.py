"""Tests for default construction build root discovery."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from kgtracevis.service import kg_construction


def test_list_kg_construction_builds_uses_source_kg_build_root_by_default(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """The default build registry should discover directories under runs/source_kg_build."""
    monkeypatch.chdir(tmp_path)
    build_dir = tmp_path / "runs" / "source_kg_build" / "wafer_user_study"
    build_dir.mkdir(parents=True)

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
                "description": "fixture",
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
    (build_dir / "source_kg_build_summary.json").write_text(
        json.dumps(
            {
                "run_id": "wafer_user_study:nearfull",
                "status": "built",
                "created_at": "2026-05-17T00:00:00+00:00",
                "source_count": 1,
                "source_ids": ["fixture_source"],
                "node_count": 1,
                "edge_count": 1,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (build_dir / "source_kg_build_manifest.json").write_text(
        json.dumps({"run": {"run_id": "wafer_user_study:nearfull"}}, indent=2),
        encoding="utf-8",
    )

    payload = kg_construction.list_kg_construction_builds()

    assert payload.build_root == "runs/source_kg_build"
    assert [build.run_id for build in payload.builds] == ["wafer_user_study:nearfull"]


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
