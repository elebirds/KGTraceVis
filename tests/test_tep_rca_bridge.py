"""Tests for bridge-mode TEP RCA artifact mapping."""

from __future__ import annotations

from pathlib import Path

from kgtracevis.adapters.tep_adapter import evidence_from_tep_record
from kgtracevis.core import KGTracePipeline
from kgtracevis.kg.graph import KnowledgeGraph
from kgtracevis.schema.validators import load_evidence_json
from kgtracevis.workflows.tep_rca import (
    TepRcaArtifactConfig,
    TepRcaArtifactProvider,
    run_tep_rca_bridge,
    tep_scenario_selector,
)

FIXTURE_DIR = Path("tests/fixtures/tep_rca")


def test_tep_rca_artifact_provider_maps_rows_to_ranked_root_causes() -> None:
    """TEP ranking artifacts should map into the unified RCA contract."""
    evidence = load_evidence_json("data/examples/tep_example.json")
    provider = TepRcaArtifactProvider(FIXTURE_DIR)

    ranked = provider.rank_root_causes(evidence, top_k=1)

    assert len(ranked) == 1
    root_cause = ranked[0]
    assert root_cause.ranking_id == "rca_tep_0001_reactorcoolingfault"
    assert root_cause.rank == 1
    assert root_cause.candidate_id == "ReactorCoolingFault"
    assert root_cause.candidate_name == "Reactor cooling fault"
    assert root_cause.candidate_label == "FaultType"
    assert root_cause.candidate_role == "root_cause_anchor"
    assert root_cause.score == 0.88
    assert root_cause.confidence == 0.91
    assert root_cause.scoring_method == "tep_artifact_bridge"
    assert root_cause.review_status == "auto"
    assert root_cause.explanation_paths[0]["path_id"] == "tep_support_1"
    assert root_cause.supporting_evidence
    assert root_cause.scoring_details["scenario_id"] == "tep_0001"
    assert root_cause.scoring_details["fault_number"] == 1
    assert root_cause.scoring_details["simulation_run"] == 3
    assert root_cause.scoring_details["top_affected_variables"] == ["XMEAS_1", "XMEAS_4"]


def test_tep_rca_bridge_returns_structured_result() -> None:
    """The workflow entry point should return an RCA ranking result envelope."""
    evidence = load_evidence_json("data/examples/tep_example.json")

    result = run_tep_rca_bridge(evidence, FIXTURE_DIR, top_k=2)

    assert result.case_id == "tep_0001"
    assert result.scoring_method == "tep_artifact_bridge"
    assert result.metadata["scenario_selector"]["scenario_ids"] == ["tep_0001"]
    assert [item.candidate_id for item in result.ranked_root_causes] == [
        "ReactorCoolingFault",
        "FeedCompositionShift",
    ]


def test_tep_scenario_selector_collects_fault_and_run_metadata() -> None:
    """TEP selector keys should be explicit rather than ad hoc string matching."""
    evidence = evidence_from_tep_record(
        {
            "case_id": "tep_fault7_run2",
            "fault_number": 7,
            "simulation_run": 2,
            "variables": ["XMEAS_2"],
            "variable_contributions": {"XMEAS_2": 0.37},
        }
    )

    selector = tep_scenario_selector(evidence)

    assert selector.scenario_ids == ("tep_fault7_run2",)
    assert selector.fault_numbers == (7,)
    assert selector.simulation_runs == (2,)


def test_tep_rca_provider_matches_opaque_scenario_by_fault_and_run(tmp_path: Path) -> None:
    """Evidence can call the provider without knowing TEP_KG's opaque scenario_id."""
    ranking_path = tmp_path / "root_kgd_rankings.jsonl"
    ranking_path.write_text(
        "\n".join(
            [
                (
                    '{"scenario_id":"scenario_opaque_7_2","fault_number":7,'
                    '"simulation_run":2,"rank":1,"candidate_id":"FaultSeven",'
                    '"candidate_name":"Fault seven","candidate_type":"FaultAnchor",'
                    '"candidate_role":"root_cause_anchor","ranking_score":0.73}'
                ),
                (
                    '{"scenario_id":"scenario_other","fault_number":8,'
                    '"simulation_run":2,"rank":1,"candidate_id":"FaultEight",'
                    '"candidate_name":"Fault eight","ranking_score":0.99}'
                ),
            ]
        ),
        encoding="utf-8",
    )
    contributions_path = tmp_path / "rbc_contributions.jsonl"
    contributions_path.write_text(
        (
            '{"scenario_id":"scenario_opaque_7_2","fault_number":7,'
            '"simulation_run":2,"top_variables":["XMEAS_2"],'
            '"graph_contributions":{"variable:xmeas_2":0.37}}\n'
        ),
        encoding="utf-8",
    )
    evidence = evidence_from_tep_record(
        {
            "case_id": "tep_fault7_run2",
            "fault_number": 7,
            "simulation_run": 2,
            "variables": ["XMEAS_2"],
            "variable_contributions": {"XMEAS_2": 0.37},
        }
    )
    provider = TepRcaArtifactProvider(
        TepRcaArtifactConfig(
            ranking_path=ranking_path,
            contributions_path=contributions_path,
        )
    )

    ranked = provider.rank_root_causes(evidence, top_k=5)

    assert [item.candidate_id for item in ranked] == ["FaultSeven"]
    root_cause = ranked[0]
    assert root_cause.scoring_details["scenario_id"] == "scenario_opaque_7_2"
    assert root_cause.scoring_details["scenario_selector"]["fault_numbers"] == [7]
    assert root_cause.scoring_details["scenario_selector"]["simulation_runs"] == [2]
    assert root_cause.supporting_evidence[1]["payload"]["scenario_id"] == "scenario_opaque_7_2"


def test_tep_rca_provider_does_not_leak_unscoped_global_rankings(tmp_path: Path) -> None:
    """Rows without TEP scenario keys should not attach to every TEP case by default."""
    ranking_path = tmp_path / "root_cause_rankings.jsonl"
    ranking_path.write_text(
        (
            '{"rank":1,"candidate_id":"GlobalCandidate",'
            '"candidate_name":"Global candidate","ranking_score":0.99}\n'
        ),
        encoding="utf-8",
    )
    evidence = evidence_from_tep_record({"case_id": "tep_fault9_run1"})

    strict_provider = TepRcaArtifactProvider(TepRcaArtifactConfig(ranking_path=ranking_path))
    permissive_provider = TepRcaArtifactProvider(
        TepRcaArtifactConfig(ranking_path=ranking_path, allow_global_rankings=True)
    )

    assert strict_provider.rank_root_causes(evidence) == []
    assert permissive_provider.rank_root_causes(evidence)[0].candidate_id == "GlobalCandidate"


def test_tep_rca_provider_does_not_match_by_simulation_run_only(tmp_path: Path) -> None:
    """A simulation run without a fault key is not a case-specific artifact scope."""
    ranking_path = tmp_path / "root_cause_rankings.jsonl"
    ranking_path.write_text(
        (
            '{"simulation_run":2,"rank":1,"candidate_id":"RunOnlyCandidate",'
            '"candidate_name":"Run-only candidate","ranking_score":0.99}\n'
        ),
        encoding="utf-8",
    )
    evidence = evidence_from_tep_record(
        {
            "case_id": "tep_fault7_run2",
            "fault_number": 7,
            "simulation_run": 2,
            "variables": ["XMEAS_2"],
        }
    )
    provider = TepRcaArtifactProvider(TepRcaArtifactConfig(ranking_path=ranking_path))

    assert provider.rank_root_causes(evidence) == []


def test_pipeline_can_use_optional_tep_rca_provider() -> None:
    """The generic pipeline should optionally fill RCA rankings from a TEP provider."""
    evidence = load_evidence_json("data/examples/tep_example.json")
    pipeline = KGTracePipeline(
        graph=KnowledgeGraph.from_default_paths(),
        root_cause_provider=TepRcaArtifactProvider(FIXTURE_DIR),
    )

    result = pipeline.analyze(evidence, top_k=1)

    assert isinstance(result.top_k_paths, list)
    assert result.ranked_root_causes[0].candidate_id == "ReactorCoolingFault"
    assert result.ranked_root_causes[0].scoring_method == "tep_artifact_bridge"
