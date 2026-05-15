"""Tests for RCA-KG construction acceptance smoke workflow."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from kgtracevis.workflows.kg_construction_smoke import (
    KGConstructionSmokeConfig,
    run_kg_construction_acceptance_smoke,
)


def test_kg_construction_smoke_builds_toy_and_tep_paths(tmp_path: Path) -> None:
    """Smoke workflow should verify both acceptance paths with TEP fixtures."""
    tep_root = tmp_path / "TEP_KG"
    _write_tep_fixture(tep_root)

    result = run_kg_construction_acceptance_smoke(
        KGConstructionSmokeConfig(
            output_dir=tmp_path / "smoke",
            tep_kg_root=tep_root,
            require_tep=True,
        )
    )
    payload = result.payload()
    paths = {path["name"]: path for path in payload["paths"]}

    assert payload["passed"] == 2
    assert payload["skipped"] == 0
    assert paths["toy_generic"]["status"] == "passed"
    assert paths["toy_generic"]["metadata"]["source_ids"] == ["toy_generic_source"]
    assert paths["toy_generic"]["artifacts"]["source_library_manifest"].endswith(
        "source_library_manifest.json"
    )
    assert paths["tep"]["status"] == "passed"
    assert paths["tep"]["metadata"]["source_ids"] == [
        "tep_semantic_lift",
        "tep_variable_mapping",
        "tep_rca_graph",
    ]
    assert paths["tep"]["metadata"]["fault_anchor_count"] == 1
    assert paths["tep"]["metadata"]["propagation_edge_count"] >= 1
    assert result.summary_path.is_file()


def test_kg_construction_smoke_requires_tep_when_requested(tmp_path: Path) -> None:
    """Missing TEP artifacts should fail when require_tep is enabled."""
    with pytest.raises(ValueError, match="missing TEP_KG smoke artifacts"):
        run_kg_construction_acceptance_smoke(
            KGConstructionSmokeConfig(
                output_dir=tmp_path / "smoke",
                tep_kg_root=tmp_path / "missing_tep",
                require_tep=True,
            )
        )


def test_smoke_rca_kg_construction_cli_builds_fixture_paths(tmp_path: Path) -> None:
    """The smoke CLI should run both acceptance paths and print a summary."""
    tep_root = tmp_path / "TEP_KG"
    _write_tep_fixture(tep_root)
    output_dir = tmp_path / "cli_smoke"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/smoke_rca_kg_construction.py",
            "--output-dir",
            str(output_dir),
            "--tep-kg-root",
            str(tep_root),
            "--require-tep",
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        text=True,
        capture_output=True,
    )

    payload = json.loads(completed.stdout)
    paths = {path["name"]: path for path in payload["paths"]}
    assert payload["artifact_type"] == "rca_kg_construction_smoke_result_v1"
    assert payload["passed"] == 2
    assert paths["toy_generic"]["status"] == "passed"
    assert paths["tep"]["status"] == "passed"
    assert Path(payload["summary_path"]).is_file()
    assert Path(paths["tep"]["artifacts"]["review_queue"]).is_file()


def _write_tep_fixture(tep_root: Path) -> None:
    kg_dir = tep_root / "data" / "processed" / "kg"
    rca_dir = tep_root / "data" / "processed" / "rca"
    kg_dir.mkdir(parents=True)
    rca_dir.mkdir(parents=True)
    _write_jsonl(
        kg_dir / "semantic_lift_nodes.jsonl",
        [
            {
                "node_id": "stream:steam",
                "entity_id": "stream:steam",
                "entity_type": "Stream",
                "name": "Steam",
                "provenance_ids": ["ev_steam"],
            },
            {
                "node_id": "variable:xmeas_19",
                "entity_id": "variable:xmeas_19",
                "entity_type": "Variable",
                "name": "XMEAS_19",
                "provenance_ids": ["ev_xmeas_19"],
                "tep_channel": "xmeas_19",
            },
        ],
    )
    _write_jsonl(
        kg_dir / "semantic_lift_edges.jsonl",
        [
            {
                "edge_id": "edge_steam_observed_by",
                "head_id": "stream:steam",
                "relation": "OBSERVED_BY",
                "tail_id": "variable:xmeas_19",
                "confidence": 0.82,
                "relation_family": "OBSERVATION",
            }
        ],
    )
    _write_jsonl(
        kg_dir / "tep_variable_mapping.jsonl",
        [
            {
                "tep_channel": "xmeas_19",
                "sequence_column": "xmeas_19",
                "kg_entity_id": "variable:xmeas_19",
                "alternate_entity_ids": "variable:xmeas_19_sensor",
                "mapping_source": "explicit_fixture_mapping",
            }
        ],
    )
    _write_jsonl(
        rca_dir / "nodes.jsonl",
        [
            {
                "node_id": "component:steam_valve",
                "entity_id": "component:steam_valve",
                "entity_type": "Component",
                "name": "Steam valve",
                "root_cause_candidate": True,
                "provenance_ids": ["ev_valve"],
            },
            {
                "node_id": "fault_anchor:fault_06",
                "entity_id": "fault_anchor:fault_06",
                "entity_type": "FaultAnchor",
                "name": "Fault 06 anchor",
                "provenance_ids": ["ev_fault"],
            },
        ],
    )
    _write_jsonl(
        rca_dir / "edges.jsonl",
        [
            {
                "edge_id": "rca_edge_steam_valve",
                "head_id": "component:steam_valve",
                "relation": "CAUSES",
                "tail_id": "fault_anchor:fault_06",
                "confidence": 0.74,
                "relation_family": "FAULT_SOURCE",
                "propagation_enabled": True,
                "review_status": "accept",
                "provenance_ids": ["ev_rca_edge"],
            }
        ],
    )


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )
