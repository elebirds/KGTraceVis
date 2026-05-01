"""Tests for Streamlit demo helper functions."""

from __future__ import annotations

from kgtracevis.app.streamlit_app import (
    build_what_if_evidence,
    correction_summary_rows,
    evidence_with_analysis,
    load_example_cases,
    parse_list_text,
    path_summary_rows,
)
from kgtracevis.core import KGTracePipeline


def test_load_example_cases_loads_checked_in_evidence() -> None:
    """The demo should expose all checked-in example evidence files."""
    cases = load_example_cases()

    case_ids = {evidence.case_id for evidence in cases.values()}

    assert case_ids == {"mvtec_0001", "tep_0001", "wafer_0001"}


def test_build_what_if_evidence_validates_edits_without_mutating_base() -> None:
    """What-if edits should produce a valid Evidence copy."""
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
    assert edited.kg_analysis.linked_entities == []
    assert base.model_dump(mode="json") == before


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
    path_rows = path_summary_rows(result.top_k_paths)
    correction_rows = correction_summary_rows(result.correction_candidates)

    assert payload["kg_analysis"]["linked_entities"]
    assert payload["kg_analysis"]["top_k_paths"][0]["source_edges"]
    assert path_rows[0]["path_id"] == "path_mvtec_0001_742df5e1c9"
    assert path_rows[0]["nodes"] == "Scratch defect -> Mechanical contact"
    assert correction_rows == []
