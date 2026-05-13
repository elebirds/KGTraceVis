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


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

