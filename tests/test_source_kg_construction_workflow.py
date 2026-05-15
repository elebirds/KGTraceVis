"""Tests for the source-to-KG construction runtime workflow."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from kgtracevis.kg_construction import KGConstructionSource
from kgtracevis.workflows.source_kg_construction import (
    SourceKGConstructionWorkflowConfig,
    run_source_kg_construction_workflow,
)


def test_source_kg_construction_workflow_writes_candidate_artifacts(
    tmp_path: Path,
) -> None:
    """Structured source text should produce CSVs, summary, and manifest artifacts."""
    output_dir = tmp_path / "runtime_build"

    result = run_source_kg_construction_workflow(
        SourceKGConstructionWorkflowConfig(
            output_dir=output_dir,
            sources=(
                KGConstructionSource(
                    source_id="manual_unit",
                    source_type="manual_table",
                    scenario="tep",
                    text=_manual_source_csv(),
                    metadata={"source_format": "csv"},
                ),
            ),
            run_id="kgbuild_manual_unit",
        )
    )

    assert result.run_id == "kgbuild_manual_unit"
    assert result.nodes_path == output_dir / "nodes.csv"
    assert result.edges_path == output_dir / "edges.csv"
    assert result.summary_path == output_dir / "kg_construction_summary.json"
    assert result.manifest_path == output_dir / "kg_construction_manifest.json"
    assert result.summary["node_count"] == 2
    assert result.summary["edge_count"] == 1
    assert result.summary["output"]["manifest"].endswith("kg_construction_manifest.json")
    assert (output_dir / "_sources" / "manual_unit.csv").is_file()

    edge_rows = _read_csv_rows(result.edges_path)
    assert edge_rows[0]["source"] == "manual_unit"
    assert edge_rows[0]["evidence"] == "explicit manual source row"
    assert edge_rows[0]["confidence"] == "0.71"
    assert edge_rows[0]["review_status"] == "auto"

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["artifact_type"] == "source_to_kg_construction_manifest_v1"
    assert manifest["run"]["run_id"] == "kgbuild_manual_unit"
    assert len(manifest["draft_rows"]) == 3
    assert manifest["artifacts"]["nodes"].endswith("nodes.csv")


def test_source_kg_construction_workflow_writes_rca_layer_artifacts(
    tmp_path: Path,
) -> None:
    """A toy generic source should produce draft, semantic, RCA, and review artifacts."""
    output_dir = tmp_path / "generic_rca_build"

    result = run_source_kg_construction_workflow(
        SourceKGConstructionWorkflowConfig(
            output_dir=output_dir,
            sources=(
                KGConstructionSource(
                    source_id="toy_generic_source",
                    source_type="manual_table",
                    scenario="shared",
                    text=_toy_generic_source_csv(),
                    metadata={"source_format": "csv"},
                ),
            ),
            run_id="kgbuild_toy_generic",
        )
    )

    expected_files = [
        result.nodes_path,
        result.edges_path,
        result.draft_manifest_path,
        result.semantic_layer_manifest_path,
        result.rca_view_manifest_path,
        result.review_queue_path,
        output_dir / "kg_construction_summary.json",
    ]
    assert all(path.is_file() for path in expected_files)
    semantic_manifest = json.loads(result.semantic_layer_manifest_path.read_text())
    rca_manifest = json.loads(result.rca_view_manifest_path.read_text())
    review_queue = json.loads(result.review_queue_path.read_text())
    edge_rows = _read_csv_rows(result.edges_path)

    assert semantic_manifest["edge_count"] == 1
    assert rca_manifest["kg_build_id"] == "kgbuild_toy_generic"
    assert rca_manifest["propagation_edge_count"] == 1
    assert edge_rows[0]["relation"] == "OBSERVED_BY"
    assert edge_rows[0]["relation_family"] == "OBSERVATION"
    assert edge_rows[0]["propagation_enabled"] == "true"
    assert review_queue[0]["target_key"].endswith("|shared")


def test_source_kg_construction_workflow_protects_existing_outputs(
    tmp_path: Path,
) -> None:
    """Existing workflow artifacts should require explicit overwrite."""
    output_dir = tmp_path / "runtime_build"
    output_dir.mkdir()
    (output_dir / "nodes.csv").write_text("already here\n", encoding="utf-8")

    with pytest.raises(ValueError, match="overwrite=true"):
        run_source_kg_construction_workflow(
            SourceKGConstructionWorkflowConfig(
                output_dir=output_dir,
                sources=(
                    KGConstructionSource(
                        source_id="manual_unit",
                        source_type="manual_table",
                        scenario="tep",
                        text=_manual_source_csv(),
                        metadata={"source_format": "csv"},
                    ),
                ),
            )
        )


def _manual_source_csv() -> str:
    return "\n".join(
        [
            "id,name,label,head,relation,tail,scenario,evidence,confidence",
            "ManualSource,Manual source,Variable,,,,tep,manual source row,0.71",
            "ManualTarget,Manual target,ProcessUnit,,,,tep,manual target row,0.71",
            ",,,ManualSource,BELONGS_TO,ManualTarget,tep,explicit manual source row,0.71",
            "",
        ]
    )


def _toy_generic_source_csv() -> str:
    return "\n".join(
        [
            "id,name,label,head,relation,tail,scenario,evidence,confidence",
            "PumpA,Pump A,Equipment,,,,shared,pump row,0.82",
            "PressureSignal,Pressure signal,Variable,,,,shared,signal row,0.82",
            ",,,PumpA,MEASURES,PressureSignal,shared,pressure is observed by Pump A sensor,0.62",
            "",
        ]
    )


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))
