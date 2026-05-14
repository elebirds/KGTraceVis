"""Tests for the example validation script."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


def test_run_examples_cli_accepts_kg_overlays(tmp_path: Path) -> None:
    """Explicit KG overlays should run examples without the Neo4j runtime backend."""
    example_dir = tmp_path / "examples"
    example_dir.mkdir()
    shutil.copy("data/examples/tep_example.json", example_dir / "tep_example.json")
    nodes_path, edges_path = _write_overlay_csv(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_examples.py",
            "--example-dir",
            str(example_dir),
            "--kg-node-path",
            str(nodes_path),
            "--kg-edge-path",
            str(edges_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout[result.stdout.rfind("{") :])
    assert payload == {"validated": 1, "kg_backend": "explicit_seed_overlay"}


def _write_overlay_csv(tmp_path: Path) -> tuple[Path, Path]:
    nodes_path = tmp_path / "overlay_nodes.csv"
    edges_path = tmp_path / "overlay_edges.csv"
    nodes_path.write_text(
        "\n".join(
            [
                "id,name,label,scenario,aliases,description",
                "OverlaySensor,Overlay Sensor,Variable,tep,overlay_sensor,test sensor",
                "OverlayUnit,Overlay Unit,Equipment,tep,overlay_unit,test equipment",
            ]
        ),
        encoding="utf-8",
    )
    edges_path.write_text(
        "\n".join(
            [
                "head,relation,tail,scenario,source,evidence,confidence,weight,"
                "review_status,feedback_count,accepted_count,rejected_count",
                "OverlaySensor,OBSERVED_BY,OverlayUnit,tep,test_source,"
                "test source row,0.8,0.2,auto,0,0,0",
            ]
        ),
        encoding="utf-8",
    )
    return nodes_path, edges_path
