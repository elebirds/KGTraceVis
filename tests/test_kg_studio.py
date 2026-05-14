"""Tests for read-only KG Studio dashboard payloads."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from kgtracevis.service.kg_studio import kg_studio_payload


def test_kg_studio_payload_reads_candidate_graph(tmp_path: Path) -> None:
    """Candidate KG rows become bounded graph edges and review targets."""
    candidate_dir = tmp_path / "candidate"
    candidate_dir.mkdir()
    _write_csv(
        candidate_dir / "nodes_candidate.csv",
        ["id", "name", "label", "scenario", "aliases", "description"],
        [
            {
                "id": "ScratchDefect",
                "name": "Scratch defect",
                "label": "AnomalyType",
                "scenario": "mvtec",
                "aliases": "scratch",
                "description": "surface mark",
            },
            {
                "id": "MechanicalContact",
                "name": "Mechanical contact",
                "label": "RootCause",
                "scenario": "mvtec",
                "aliases": "contact",
                "description": "candidate mechanism",
            },
        ],
    )
    _write_csv(
        candidate_dir / "edges_candidate.csv",
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
                "head": "ScratchDefect",
                "relation": "SUGGESTS_PLAUSIBLE_MECHANISM",
                "tail": "MechanicalContact",
                "scenario": "mvtec",
                "source": "unit_source",
                "evidence": "scratch evidence",
                "confidence": "0.52",
                "weight": "0.48",
                "review_status": "auto",
                "feedback_count": "0",
                "accepted_count": "0",
                "rejected_count": "0",
            }
        ],
    )
    (candidate_dir / "validation_report.json").write_text(
        json.dumps({"summary": {"passed": True, "issue_count": 0}}),
        encoding="utf-8",
    )
    source_registry = tmp_path / "source_registry.csv"
    _write_csv(
        source_registry,
        ["source_id", "title", "type", "path_or_url", "used_for", "notes"],
        [
            {
                "source_id": "unit_source",
                "title": "Unit source",
                "type": "manual",
                "path_or_url": "docs/sources/unit.md",
                "used_for": "test",
                "notes": "candidate only",
            }
        ],
    )
    source_docs = tmp_path / "sources"
    source_docs.mkdir()
    (source_docs / "unit.md").write_text("# Unit Source\nEvidence note\n", encoding="utf-8")

    payload = kg_studio_payload(
        candidate_dirs=(candidate_dir,),
        source_registry_path=source_registry,
        source_docs_dir=source_docs,
    )

    assert payload.status == "ok"
    assert payload.node_count == 2
    assert payload.edge_count == 1
    assert payload.validation_summary == {"passed": True, "issue_count": 0}
    assert payload.graph_edges[0].target_key.startswith("edge:ScratchDefect|")
    assert payload.review_targets[0].target_id == payload.graph_edges[0].edge_id
    assert payload.sources[0].source_id == "unit_source"
    assert payload.source_documents[0].title == "Unit Source"


def test_kg_studio_payload_handles_missing_candidate_artifacts(tmp_path: Path) -> None:
    """Missing generated KG artifacts produce an empty payload instead of an error."""
    payload = kg_studio_payload(
        candidate_dirs=(tmp_path / "missing",),
        source_registry_path=tmp_path / "missing_sources.csv",
        source_docs_dir=tmp_path / "missing_docs",
    )

    assert payload.status == "empty"
    assert payload.node_count == 0
    assert payload.edge_count == 0
    assert payload.graph_edges == []
    assert payload.review_targets == []


def test_kg_studio_payload_reads_source_kg_build_artifacts(tmp_path: Path) -> None:
    """KG Studio can inspect source-to-KG build outputs without renamed CSVs."""
    candidate_dir = tmp_path / "source_kg_build"
    candidate_dir.mkdir()
    _write_csv(
        candidate_dir / "nodes.csv",
        ["id", "name", "label", "scenario", "aliases", "description"],
        [
            {
                "id": "SteamStream",
                "name": "Steam",
                "label": "Stream",
                "scenario": "tep",
                "aliases": "stream:steam",
                "description": "TEP semantic-lift stream",
            },
            {
                "id": "Xmeas19Variable",
                "name": "XMEAS_19",
                "label": "Variable",
                "scenario": "tep",
                "aliases": "variable:xmeas_19|xmeas_19",
                "description": "TEP measurement",
            },
        ],
    )
    _write_csv(
        candidate_dir / "edges.csv",
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
                "head": "SteamStream",
                "relation": "OBSERVED_BY",
                "tail": "Xmeas19Variable",
                "scenario": "tep",
                "source": "tep_semantic_lift_unit",
                "evidence": "TEP semantic-lift edge edge_steam_observed_by",
                "confidence": "0.82",
                "weight": "0.18",
                "review_status": "auto",
                "feedback_count": "0",
                "accepted_count": "0",
                "rejected_count": "0",
            }
        ],
    )
    (candidate_dir / "kg_construction_manifest.json").write_text(
        json.dumps(
            {
                "artifact_type": "source_to_kg_construction_manifest_v1",
                "run": {"run_id": "kgbuild_unit"},
                "summary": {"node_count": 2, "edge_count": 1},
                "sources": [],
                "artifacts": {},
                "draft_rows": [],
                "review_decisions": [],
            }
        ),
        encoding="utf-8",
    )

    payload = kg_studio_payload(
        candidate_dirs=(candidate_dir,),
        source_registry_path=tmp_path / "missing_sources.csv",
        source_docs_dir=tmp_path / "missing_docs",
    )

    assert payload.status == "ok"
    assert payload.nodes_path and payload.nodes_path.endswith("nodes.csv")
    assert payload.edges_path and payload.edges_path.endswith("edges.csv")
    assert payload.manifest_path and payload.manifest_path.endswith(
        "kg_construction_manifest.json"
    )
    assert payload.construction_manifest is not None
    assert payload.construction_manifest["run"]["run_id"] == "kgbuild_unit"
    assert payload.review_targets[0].target_id == (
        "SteamStream|OBSERVED_BY|Xmeas19Variable|tep"
    )


def test_kg_studio_payload_discovers_runtime_source_kg_child_build(
    tmp_path: Path,
) -> None:
    """KG Studio should find workflow build directories under a configured root."""
    build_root = tmp_path / "source_kg_build"
    candidate_dir = build_root / "unit_runtime"
    candidate_dir.mkdir(parents=True)
    _write_csv(
        candidate_dir / "nodes.csv",
        ["id", "name", "label", "scenario", "aliases", "description"],
        [
            {
                "id": "ManualSource",
                "name": "Manual source",
                "label": "Variable",
                "scenario": "tep",
                "aliases": "",
                "description": "manual runtime node",
            },
            {
                "id": "ManualTarget",
                "name": "Manual target",
                "label": "ProcessUnit",
                "scenario": "tep",
                "aliases": "",
                "description": "manual runtime node",
            },
        ],
    )
    _write_csv(
        candidate_dir / "edges.csv",
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
                "head": "ManualSource",
                "relation": "BELONGS_TO",
                "tail": "ManualTarget",
                "scenario": "tep",
                "source": "manual_unit",
                "evidence": "explicit source row",
                "confidence": "0.71",
                "weight": "0.29",
                "review_status": "auto",
                "feedback_count": "0",
                "accepted_count": "0",
                "rejected_count": "0",
            }
        ],
    )
    (candidate_dir / "kg_construction_manifest.json").write_text(
        json.dumps(
            {
                "artifact_type": "source_to_kg_construction_manifest_v1",
                "run": {"run_id": "kgbuild_runtime_child"},
                "summary": {"node_count": 2, "edge_count": 1},
                "sources": [],
                "artifacts": {},
                "draft_rows": [],
                "review_decisions": [],
            }
        ),
        encoding="utf-8",
    )

    payload = kg_studio_payload(
        candidate_dirs=(build_root,),
        source_registry_path=tmp_path / "missing_sources.csv",
        source_docs_dir=tmp_path / "missing_docs",
    )

    assert payload.status == "ok"
    assert payload.candidate_dir and payload.candidate_dir.endswith("unit_runtime")
    assert payload.construction_manifest is not None
    assert payload.construction_manifest["run"]["run_id"] == "kgbuild_runtime_child"


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
