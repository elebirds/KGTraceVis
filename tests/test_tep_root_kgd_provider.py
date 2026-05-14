"""Tests for the TEP Root-KGD RCA provider."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from kgtracevis.adapters.tep_adapter import evidence_from_tep_record
from kgtracevis.core import KGTracePipeline
from kgtracevis.kg.graph import KnowledgeGraph
from kgtracevis.workflows.tep_root_kgd import (
    TepRootKgdRcaProvider,
    extract_root_kgd_dynamic_features,
    extract_root_kgd_graph_contributions,
)


def test_root_kgd_provider_ranks_from_current_evidence_contributions(
    tmp_path: Path,
) -> None:
    """Runtime Evidence contributions should determine Root-KGD candidate order."""
    asset_dir = _write_root_kgd_assets(tmp_path / "assets")
    provider = TepRootKgdRcaProvider(asset_dir)
    evidence = evidence_from_tep_record(
        {
            "case_id": "tep_root_kgd_case_1",
            "variables": ["XMEAS_1", "XMEAS_2"],
            "variable_contributions": {"XMEAS_1": 0.9, "XMEAS_2": 0.1},
        }
    )

    ranked = provider.rank_root_causes(evidence, top_k=2)

    assert [item.candidate_id for item in ranked] == [
        "faultanchor:cooling_fault",
        "faultanchor:feed_fault",
    ]
    assert ranked[0].scoring_method == "tep_root_kgd"
    assert ranked[0].explanation_paths[0]["nodes"] == [
        "faultanchor:cooling_fault",
        "variable:xmeas_1",
    ]


def test_root_kgd_provider_order_changes_without_precomputed_rank_rows(
    tmp_path: Path,
) -> None:
    """Changing Evidence contributions should change ranking from runtime scoring."""
    asset_dir = _write_root_kgd_assets(tmp_path / "assets")
    provider = TepRootKgdRcaProvider(asset_dir)
    evidence = evidence_from_tep_record(
        {
            "case_id": "tep_root_kgd_case_2",
            "variables": ["XMEAS_1", "XMEAS_2"],
            "variable_contributions": {"XMEAS_1": 0.1, "XMEAS_2": 0.9},
        }
    )

    ranked = provider.rank_root_causes(evidence, top_k=2)

    assert [item.candidate_id for item in ranked] == [
        "faultanchor:feed_fault",
        "faultanchor:cooling_fault",
    ]
    assert not (asset_dir / "baseline_root_scores.csv").exists()
    assert not (asset_dir / "topk_subgraphs.json").exists()
    assert not (asset_dir / "rbc_contributions.jsonl").exists()


def test_root_kgd_provider_extracts_graph_contributions_and_dynamic_features(
    tmp_path: Path,
) -> None:
    """Evidence extra should expose Root-KGD variable ids and current-window features."""
    provider = TepRootKgdRcaProvider(_write_root_kgd_assets(tmp_path / "assets"))
    evidence = evidence_from_tep_record(
        {
            "case_id": "tep_root_kgd_extract",
            "variables": ["XMEAS_1"],
            "variable_contributions": {"XMEAS_1": 0.2},
            "extra": {
                "graph_contributions": {"variable:xmeas_2": 0.7},
                "root_kgd_dynamic_features": {
                    "features": {"xmeas_2__std": 1.25},
                },
            },
        }
    )

    contributions = extract_root_kgd_graph_contributions(
        evidence,
        provider.assets.variable_mapping,
    )
    features = extract_root_kgd_dynamic_features(evidence)

    assert contributions["variable:xmeas_1"] == 0.2
    assert contributions["variable:xmeas_2"] == 0.7
    assert features == {"xmeas_2__std": 1.25}


def test_pipeline_uses_root_kgd_reasoner_outputs(tmp_path: Path) -> None:
    """KGTracePipeline should preserve Root-KGD candidates and explanation paths."""
    provider = TepRootKgdRcaProvider(_write_root_kgd_assets(tmp_path / "assets"))
    evidence = evidence_from_tep_record(
        {
            "case_id": "tep_root_kgd_pipeline",
            "variables": ["XMEAS_1", "XMEAS_2"],
            "variable_contributions": {"XMEAS_1": 0.8, "XMEAS_2": 0.2},
        }
    )
    pipeline = KGTracePipeline(
        graph=KnowledgeGraph([], []),
        root_cause_reasoner=provider,
    )

    result = pipeline.analyze(evidence, top_k=2)

    assert result.ranked_root_causes
    assert result.ranked_root_causes[0].candidate_id == "faultanchor:cooling_fault"
    assert result.ranked_root_causes[0].scoring_method == "tep_root_kgd"
    assert result.top_k_paths[0]["path_id"] == (
        result.ranked_root_causes[0].explanation_paths[0]["path_id"]
    )


def test_root_kgd_candidate_paths_are_subset_of_returned_top_k_paths(
    tmp_path: Path,
) -> None:
    """Ranked candidate explanations should only reference returned paths."""
    provider = TepRootKgdRcaProvider(_write_root_kgd_assets(tmp_path / "assets"))
    evidence = evidence_from_tep_record(
        {
            "case_id": "tep_root_kgd_path_alignment",
            "variables": ["XMEAS_1", "XMEAS_2", "XMEAS_3"],
            "variable_contributions": {
                "XMEAS_1": 0.45,
                "XMEAS_2": 0.45,
                "XMEAS_3": 0.10,
            },
        }
    )

    result = provider.reason_root_causes(
        evidence,
        graph=KnowledgeGraph([], []),
        linked_entities=[],
        top_k=2,
    )

    returned_path_ids = {str(path["path_id"]) for path in result.top_k_paths}
    candidate_path_ids = {
        str(path["path_id"])
        for candidate in result.ranked_root_causes
        for path in candidate.explanation_paths
    }
    assert len(result.top_k_paths) == 2
    assert candidate_path_ids <= returned_path_ids


def test_real_tepkg_root_kgd_parity_smoke() -> None:
    """Guarded smoke check: local TEP_KG rank_scenario matches the ported function."""
    tepkg_root = Path("/Users/hhm/code/TEP_KG")
    if not tepkg_root.exists():
        pytest.skip("local TEP_KG checkout is absent")
    sys.path.insert(0, str(tepkg_root / "src"))
    try:
        from tep_kg.propagation import build_propagation_graph as tepkg_graph
        from tep_kg.root_kgd import rank_scenario as tepkg_rank_scenario
    finally:
        sys.path.pop(0)

    from kgtracevis.workflows.tep_root_kgd.root_kgd import rank_scenario

    scenario = {
        "scenario_id": "parity_smoke",
        "fault_number": 0,
        "simulation_run": 0,
        "graph_contributions": {
            "variable:xmeas_22": 0.7,
            "variable:xmeas_11": 0.3,
        },
    }
    graph = tepkg_graph(tepkg_root)
    ordered_variables = ["variable:xmeas_11", "variable:xmeas_22"]

    expected = tepkg_rank_scenario(graph, scenario, ordered_variables)[:3]
    actual = rank_scenario(graph, scenario, ordered_variables)[:3]

    assert [row["candidate_id"] for row in actual] == [
        row["candidate_id"] for row in expected
    ]


def _write_root_kgd_assets(asset_dir: Path) -> Path:
    asset_dir.mkdir(parents=True)
    _write_jsonl(
        asset_dir / "nodes.jsonl",
        [
            _node("faultanchor:cooling_fault", "Cooling fault", "FaultAnchor", True),
            _node("faultanchor:feed_fault", "Feed fault", "FaultAnchor", True),
            _node("variable:xmeas_1", "XMEAS_1", "Variable", False),
            _node("variable:xmeas_2", "XMEAS_2", "Variable", False),
            _node("variable:xmeas_3", "XMEAS_3", "Variable", False),
        ],
    )
    _write_jsonl(
        asset_dir / "edges.jsonl",
        [
            _edge("edge_cooling_xmeas_1", "faultanchor:cooling_fault", "variable:xmeas_1"),
            _edge("edge_cooling_xmeas_3", "faultanchor:cooling_fault", "variable:xmeas_3"),
            _edge("edge_feed_xmeas_2", "faultanchor:feed_fault", "variable:xmeas_2"),
        ],
    )
    _write_jsonl(
        asset_dir / "tep_variable_mapping.jsonl",
        [
            _mapping("xmeas_1", "variable:xmeas_1", 1),
            _mapping("xmeas_2", "variable:xmeas_2", 2),
            _mapping("xmeas_3", "variable:xmeas_3", 3),
        ],
    )
    _write_json(asset_dir / "anchor_discriminators.json", {"anchor_count": 0, "anchors": []})
    _write_json(
        asset_dir / "relation_family_params.json",
        {
            "families": {
                "OBSERVATION": {"sigma": 0.32, "priority": 1},
                "FAULT_SOURCE": {"sigma": 0.1, "priority": 7},
            }
        },
    )
    _write_jsonl(
        asset_dir / "rca_edge_weights.jsonl",
        [
            {"edge_id": "edge_cooling_xmeas_1", "edge_weight": 0.95},
            {"edge_id": "edge_cooling_xmeas_3", "edge_weight": 0.95},
            {"edge_id": "edge_feed_xmeas_2", "edge_weight": 0.95},
        ],
    )
    _write_json(asset_dir / "anchor_memory_profiles.json", {"anchor_count": 0, "anchors": []})
    return asset_dir


def _node(
    node_id: str,
    name: str,
    entity_type: str,
    root_cause_candidate: bool,
) -> dict[str, Any]:
    return {
        "entity_id": node_id,
        "node_id": node_id,
        "name": name,
        "entity_type": entity_type,
        "candidate_role": "root_cause_anchor" if root_cause_candidate else "",
        "root_cause_candidate": root_cause_candidate,
        "variable_role": "sensor" if entity_type == "Variable" else "",
        "provenance_ids": [],
    }


def _edge(edge_id: str, head_id: str, tail_id: str) -> dict[str, Any]:
    return {
        "edge_id": edge_id,
        "head_id": head_id,
        "tail_id": tail_id,
        "relation": "OBSERVED_BY",
        "relation_family": "OBSERVATION",
        "confidence": 0.9,
        "support_count": 1,
        "source_types": ["test"],
        "provenance_ids": [f"prov_{edge_id}"],
        "propagation_enabled": True,
        "review_status": "auto",
    }


def _mapping(channel: str, entity_id: str, index: int) -> dict[str, Any]:
    return {
        "sequence_column": channel,
        "tep_channel": channel,
        "kg_entity_id": entity_id,
        "tep_variable_family": "xmeas",
        "tep_variable_index": index,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
