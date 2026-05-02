"""Tests for Streamlit demo helper functions."""

from __future__ import annotations

from pathlib import Path

from kgtracevis.app.streamlit_app import (
    _collect_edges,
    adapter_boundary_rows,
    adapter_output_payload,
    adapter_output_rows,
    build_what_if_evidence,
    case_label,
    consistency_check_rows,
    correction_summary_rows,
    demo_case_notes,
    evidence_with_analysis,
    link_summary_rows,
    load_example_cases,
    observed_evidence_rows,
    parse_list_text,
    path_edge_rows,
    path_graphviz_source,
    path_mermaid_source,
    path_summary_rows,
    source_provenance_rows,
)
from kgtracevis.core import KGTracePipeline
from kgtracevis.kg.consistency_checker import check_consistency


def test_load_example_cases_loads_checked_in_evidence() -> None:
    """The demo should expose all checked-in example evidence files."""
    cases = load_example_cases()

    case_ids = {evidence.case_id for evidence in cases.values()}

    assert case_ids == {"mvtec_0001", "mvtec_noisy_0001", "tep_0001", "wafer_0001"}


def test_example_metadata_keeps_demo_analysis_boundary_explicit() -> None:
    """Examples should be evidence inputs, not precomputed RCA claims."""
    for evidence in load_example_cases().values():
        description = evidence.raw_evidence.description or ""
        extra = evidence.raw_evidence.extra
        demo_scope = str(extra["demo_scope"])
        analysis_boundary = str(extra["analysis_boundary"])

        assert "观测到的" in description
        assert "anomaly evidence only" in description
        assert "不包含 root-cause label" in description
        assert "observed anomaly evidence only" in demo_scope
        assert (
            "KGTracePipeline computes linking/consistency/corrections/"
            "candidate RCA paths at runtime"
        ) in analysis_boundary
        assert evidence.kg_analysis.linked_entities == []
        assert evidence.kg_analysis.correction_candidates == []
        assert evidence.kg_analysis.top_k_paths == []


def test_case_labels_identify_scenario_without_calling_paths_placeholders() -> None:
    """Labels should make scenarios clear without implying static RCA output."""
    cases = load_example_cases()
    labels = {
        evidence.case_id: case_label(Path(label.rsplit(" - ", maxsplit=1)[1]), evidence)
        for label, evidence in cases.items()
    }

    assert labels["mvtec_0001"].startswith("MVTEC: mvtec_0001 - ")
    assert labels["mvtec_noisy_0001"].startswith("MVTEC: mvtec_noisy_0001 噪声演示 - ")
    assert all("placeholder" not in label.lower() for label in labels.values())


def test_build_what_if_evidence_validates_edits_without_mutating_base() -> None:
    """What-if edits should produce a valid Evidence copy with fresh observations."""
    base = next(
        evidence for evidence in load_example_cases().values() if evidence.case_id == "mvtec_0001"
    )
    before = base.model_dump(mode="json")

    edited = build_what_if_evidence(
        base,
        anomaly_type=" scratch ",
        location=" reactor ",
        morphology="",
        variables_text="XMEAS_1, XMEAS_2\n XMEAS_3 ",
        log_events_text="alarm_a\nalarm_b",
    )

    assert edited.anomaly_type == "scratch"
    assert edited.location == "reactor"
    assert edited.morphology is None
    assert edited.raw_evidence.variables == ["XMEAS_1", "XMEAS_2", "XMEAS_3"]
    assert edited.raw_evidence.log_events == ["alarm_a", "alarm_b"]
    assert {observation.name for observation in edited.observations} >= {
        "scratch",
        "reactor",
        "XMEAS_1",
        "alarm_a",
    }
    assert all(observation.source_ref == "what-if editor" for observation in edited.observations)
    assert edited.kg_analysis.linked_entities == []
    assert base.model_dump(mode="json") == before


def test_build_what_if_evidence_keeps_repeated_observation_ids_unique() -> None:
    """What-if edits can duplicate variables/events without duplicate obs_ids."""
    base = next(
        evidence for evidence in load_example_cases().values() if evidence.case_id == "mvtec_0001"
    )

    edited = build_what_if_evidence(
        base,
        anomaly_type="scratch",
        location="surface",
        morphology="linear",
        variables_text="XMEAS_1\nXMEAS_1",
        log_events_text="alarm_a\nalarm_a",
    )

    obs_ids = [observation.obs_id for observation in edited.observations]

    assert len(obs_ids) == len(set(obs_ids))
    assert "obs_mvtec_0001_variable_xmeas_1_02" in obs_ids
    assert "obs_mvtec_0001_log_event_alarm_a_02" in obs_ids


def test_build_what_if_evidence_keeps_required_text_valid() -> None:
    """Blank required text should stay schema-compatible for local editing."""
    base = next(iter(load_example_cases().values()))

    edited = build_what_if_evidence(
        base,
        anomaly_type=" ",
        location="",
        morphology="",
        variables_text="",
        log_events_text="",
    )

    assert edited.anomaly_type == "unknown"
    assert edited.location is None
    assert edited.morphology is None
    assert edited.raw_evidence.variables == []
    assert edited.raw_evidence.log_events == []
    assert any(
        observation.facet == "anomaly_type" and observation.name == "unknown"
        for observation in edited.observations
    )


def test_build_what_if_evidence_clears_stale_analysis_outputs() -> None:
    """What-if edits should not retain stale observations or analysis output."""
    base = next(
        evidence
        for evidence in load_example_cases().values()
        if evidence.case_id == "mvtec_noisy_0001"
    )
    payload = base.model_dump(mode="json")
    payload["normalized_evidence"] = {"stale": "analysis"}
    base = base.__class__.model_validate(payload)

    edited = build_what_if_evidence(
        base,
        anomaly_type=base.anomaly_type,
        location=base.location or "",
        morphology="linear",
        variables_text="",
        log_events_text="",
    )

    assert edited.normalized_evidence == {}
    assert edited.kg_analysis.linked_entities == []
    assert edited.kg_analysis.top_k_paths == []
    assert not any(
        observation.facet == "morphology" and observation.name == "surface"
        for observation in edited.observations
    )
    assert any(
        observation.facet == "morphology" and observation.name == "linear"
        for observation in edited.observations
    )


def test_pipeline_steps_explain_input_and_adapter_boundary() -> None:
    """Step 0/1 helpers should show observed evidence without precomputed KG output."""
    base = next(
        evidence for evidence in load_example_cases().values() if evidence.case_id == "mvtec_0001"
    )

    boundary_rows = adapter_boundary_rows(base)
    observed_rows = observed_evidence_rows(base)
    output_rows = adapter_output_rows(base)
    output_payload = adapter_output_payload(base)

    assert {"项目": "selected case", "值": "mvtec_0001"} in boundary_rows
    assert {"项目": "adapter id", "值": "mvtec"} in boundary_rows
    assert any(
        row["项目"] == "produces_root_cause" and str(row["值"]).startswith("false")
        for row in boundary_rows
    )
    assert any(row["项目"] == "root cause in input?" and "否" in row["值"] for row in boundary_rows)
    assert {
        "obs_id": "obs_mvtec_0001_anomaly_type_scratch",
        "facet": "anomaly_type",
        "name": "scratch",
        "display_name": "",
        "value": "unknown",
        "confidence": 0.8,
        "source_ref": "adapter:mvtec",
        "raw_ref": "anomaly_type",
    } in observed_rows
    assert any(row["字段"] == "observations" and row["状态"] == "structured" for row in output_rows)
    assert any(
        row["字段"] == "adapter.produces_root_cause" and row["状态"] is False
        for row in output_rows
    )
    assert any(row["字段"] == "root_cause" and row["状态"] == "not present" for row in output_rows)
    assert output_payload["adapter"]["produces_root_cause"] is False
    assert output_payload["observations"][0]["obs_id"] == "obs_mvtec_0001_object_bottle"
    assert output_payload["kg_analysis"]["linked_entities"] == []
    assert output_payload["kg_analysis"]["correction_candidates"] == []
    assert output_payload["kg_analysis"]["top_k_paths"] == []


def test_observed_evidence_rows_fall_back_to_legacy_fields_after_observations_removed() -> None:
    """Legacy evidence payloads should still render as observation-shaped rows."""
    base = next(
        evidence for evidence in load_example_cases().values() if evidence.case_id == "mvtec_0001"
    )
    payload = base.model_dump(mode="json")
    payload["observations"] = []
    legacy = base.__class__.model_validate(payload)

    rows = observed_evidence_rows(legacy)

    assert {
        "obs_id": "",
        "facet": "anomaly_type",
        "name": "scratch",
        "display_name": "",
        "value": "scratch",
        "confidence": 0.8,
        "source_ref": "legacy top-level field",
        "raw_ref": "anomaly_type",
    } in rows


def test_parse_list_text_accepts_commas_and_newlines() -> None:
    """List editors should accept compact and multiline input."""
    assert parse_list_text("a, b\nc\n\n d ") == ["a", "b", "c", "d"]


def test_analysis_payload_and_summaries_include_provenance_contracts() -> None:
    """Display helpers should preserve stable IDs and KG source provenance."""
    base = next(
        evidence for evidence in load_example_cases().values() if evidence.case_id == "mvtec_0001"
    )
    result = KGTracePipeline().analyze(base)

    payload = evidence_with_analysis(base, result)
    link_rows = link_summary_rows(result.linked_entities)
    path_rows = path_summary_rows(result.top_k_paths)
    path_edges = path_edge_rows(result.top_k_paths)
    correction_rows = correction_summary_rows(result.correction_candidates)

    assert payload["kg_analysis"]["linked_entities"]
    assert payload["kg_analysis"]["top_k_paths"][0]["source_edges"]
    assert link_rows[0]["obs_id"] == "obs_mvtec_0001_object_bottle"
    assert link_rows[0]["facet"] == "object"
    assert link_rows[0]["候选 KG nodes"]
    assert "BottleObject" in link_rows[0]["候选 KG nodes"]
    assert path_rows[0]["path_id"] == "path_mvtec_0001_742df5e1c9"
    assert path_rows[0]["节点序列"] == "Scratch defect -> Mechanical contact"
    assert path_rows[0]["source_edge_ids"] == (
        "ScratchDefect|HAS_PLAUSIBLE_CAUSE|MechanicalContact|mvtec"
    )
    assert path_edges[0]["path_id"] == "path_mvtec_0001_742df5e1c9"
    assert path_edges[0]["relation"] == "HAS_PLAUSIBLE_CAUSE"
    assert path_edges[0]["source"] == "manual_curation"
    assert correction_rows == []


def test_path_diagram_helpers_show_node_sequence_and_relation_labels() -> None:
    """The path explorer should have a lightweight visual representation."""
    base = next(
        evidence for evidence in load_example_cases().values() if evidence.case_id == "mvtec_0001"
    )
    path = KGTracePipeline().analyze(base).top_k_paths[0]

    graphviz = path_graphviz_source(path)
    mermaid = path_mermaid_source(path)

    assert "digraph path_mvtec_0001_742df5e1c9" in graphviz
    assert "Scratch defect\\n(ScratchDefect)" in graphviz
    assert "HAS_PLAUSIBLE_CAUSE" in graphviz
    assert "flowchart LR" in mermaid
    assert "Scratch defect" in mermaid
    assert 'n0 -- "HAS_PLAUSIBLE_CAUSE" --> n1' in mermaid


def test_source_provenance_rows_include_observations_and_path_edges() -> None:
    """The provenance panel should combine adapter refs and KG source edges."""
    base = next(
        evidence for evidence in load_example_cases().values() if evidence.case_id == "mvtec_0001"
    )
    result = KGTracePipeline().analyze(base)

    rows = source_provenance_rows(base, result.top_k_paths, result.correction_candidates)

    assert {
        "来源类型": "observation",
        "引用": "adapter:mvtec",
        "raw_ref": "anomaly_type",
        "关联 ID": "obs_mvtec_0001_anomaly_type_scratch",
        "说明": "anomaly_type: scratch",
    } in rows
    assert any(
        row["来源类型"] == "path_edge"
        and row["引用"] == "manual_curation"
        and row["关联 ID"] == "path_mvtec_0001_742df5e1c9"
        for row in rows
    )


def test_source_provenance_rows_include_legacy_input_sources() -> None:
    """Legacy payloads without observations should still show where inputs came from."""
    base = next(
        evidence for evidence in load_example_cases().values() if evidence.case_id == "mvtec_0001"
    )
    payload = base.model_dump(mode="json")
    payload["observations"] = []
    legacy = base.__class__.model_validate(payload)

    rows = source_provenance_rows(legacy, [], [])

    assert {
        "来源类型": "observation",
        "引用": "legacy top-level field",
        "raw_ref": "anomaly_type",
        "关联 ID": "",
        "说明": "anomaly_type: scratch",
    } in rows


def test_consistency_step_rows_show_checked_relations() -> None:
    """Step 3 helper should expose field pairs, relations, pass/fail, and matches."""
    base = next(
        evidence for evidence in load_example_cases().values() if evidence.case_id == "mvtec_0001"
    )
    pipeline = KGTracePipeline()
    result = pipeline.analyze(base)
    consistency = check_consistency(base, pipeline.graph, result.linked_entities)

    rows = consistency_check_rows(consistency["checks"])

    assert rows
    assert {
        "检查字段对": "anomaly_type -> morphology",
        "source_entity_id": "ScratchDefect",
        "target_entity_id": "LinearMorphology",
        "检查关系": "HAS_MORPHOLOGY",
        "结果": "通过",
        "matched_relation": "HAS_MORPHOLOGY",
    } in rows


def test_noisy_demo_case_exposes_correction_story() -> None:
    """The live demo should include at least one visible inconsistency."""
    base = next(
        evidence
        for evidence in load_example_cases().values()
        if evidence.case_id == "mvtec_noisy_0001"
    )
    result = KGTracePipeline().analyze(base)
    correction_rows = correction_summary_rows(result.correction_candidates)

    assert result.consistency_score is not None
    assert result.consistency_score < 1.0
    assert result.inconsistent_fields == ["anomaly_type", "morphology"]
    assert correction_rows
    assert correction_rows[0]["candidate_id"] == (
        "corr_mvtec_noisy_0001_morphology_linearmorphology"
    )
    assert correction_rows[0]["建议值"] == "Linear morphology"
    notes = demo_case_notes(base)
    assert any("observed anomaly evidence only" in note for note in notes)
    assert any("KGTracePipeline computes linking/consistency/corrections" in note for note in notes)
    assert any("KGTracePipeline runtime candidates" in note for note in notes)
    assert any("噪声演示案例" in note and "morphology" in note for note in notes)
    assert any("干净参考：morphology=linear。" == note for note in notes)


def test_collect_edges_preserves_edges_without_ids() -> None:
    """Provenance display should not collapse malformed edges into one row."""
    rows = _collect_edges(
        [
            {
                "source_edges": [
                    {"head": "A", "relation": "REL", "tail": "B", "scenario": "shared"},
                    {"head": "C", "relation": "REL", "tail": "D", "scenario": "shared"},
                    {"source": "missing structured edge id"},
                ]
            },
            {
                "source_edges": [
                    {"head": "A", "relation": "REL", "tail": "B", "scenario": "shared"},
                    {"source": "second missing structured edge id"},
                ]
            },
        ],
        "source_edges",
    )

    assert rows == [
        {"head": "A", "relation": "REL", "tail": "B", "scenario": "shared"},
        {"head": "C", "relation": "REL", "tail": "D", "scenario": "shared"},
        {"source": "missing structured edge id"},
        {"source": "second missing structured edge id"},
    ]
