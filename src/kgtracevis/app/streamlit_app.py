"""Lightweight Streamlit demo for local KGTraceVis evidence analysis."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from kgtracevis.core import KGTracePipeline
from kgtracevis.core.result import AnalysisResult
from kgtracevis.schema.evidence_schema import Evidence, KGAnalysis
from kgtracevis.schema.validators import load_evidence_json

DEFAULT_EXAMPLE_DIR = Path("data/examples")


def iter_example_files(example_dir: str | Path = DEFAULT_EXAMPLE_DIR) -> list[Path]:
    """Return sorted checked-in example evidence JSON files."""
    return sorted(Path(example_dir).glob("*.json"))


def load_example_cases(example_dir: str | Path = DEFAULT_EXAMPLE_DIR) -> dict[str, Evidence]:
    """Load example evidence files keyed by a stable UI label."""
    cases: dict[str, Evidence] = {}
    for path in iter_example_files(example_dir):
        evidence = load_evidence_json(path)
        cases[case_label(path, evidence)] = evidence
    if not cases:
        raise ValueError(f"no example JSON files found in {Path(example_dir)}")
    return cases


def case_label(path: Path, evidence: Evidence) -> str:
    """Return a compact label for selecting an example case."""
    return f"{evidence.case_id} ({evidence.dataset}) - {path.name}"


def format_list_text(values: list[str]) -> str:
    """Format editable list values for a text area."""
    return "\n".join(values)


def parse_list_text(value: str) -> list[str]:
    """Parse newline- or comma-separated editor text into stable list values."""
    normalized = value.replace(",", "\n")
    return [part.strip() for part in normalized.splitlines() if part.strip()]


def build_what_if_evidence(
    evidence: Evidence,
    *,
    anomaly_type: str,
    location: str,
    morphology: str,
    variables_text: str,
    log_events_text: str,
) -> Evidence:
    """Return a validated evidence copy with editable what-if fields applied."""
    payload = evidence.model_dump(mode="json")
    payload["anomaly_type"] = _required_text(anomaly_type)
    payload["location"] = _optional_text(location)
    payload["morphology"] = _optional_text(morphology)
    payload["kg_analysis"] = KGAnalysis().model_dump(mode="json")

    raw_evidence = dict(cast(dict[str, Any], payload["raw_evidence"]))
    raw_evidence["variables"] = parse_list_text(variables_text)
    raw_evidence["log_events"] = parse_list_text(log_events_text)
    payload["raw_evidence"] = raw_evidence

    return Evidence.model_validate(payload)


def evidence_with_analysis(evidence: Evidence, result: AnalysisResult) -> dict[str, Any]:
    """Return an evidence-shaped payload with the latest KG analysis attached."""
    payload = evidence.model_dump(mode="json")
    payload["kg_analysis"] = {
        "linked_entities": result.linked_entities,
        "consistency_score": result.consistency_score,
        "inconsistent_fields": result.inconsistent_fields,
        "correction_candidates": result.correction_candidates,
        "top_k_paths": result.top_k_paths,
    }
    return payload


def link_summary_rows(links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return display rows for linked entity results."""
    rows: list[dict[str, Any]] = []
    for link in links:
        rows.append(
            {
                "link_id": link.get("link_id"),
                "field": link.get("field"),
                "mention": link.get("mention"),
                "selected_entity_id": link.get("selected_entity_id"),
                "score": link.get("score"),
                "match_type": link.get("match_type"),
                "ambiguous": link.get("ambiguous"),
                "candidate_count": len(cast(list[Any], link.get("candidates", []))),
            }
        )
    return rows


def correction_summary_rows(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return display rows for correction candidates."""
    return [
        {
            "candidate_id": candidate.get("candidate_id"),
            "field": candidate.get("field"),
            "original": candidate.get("original_value"),
            "suggested": candidate.get("suggested_value"),
            "score": candidate.get("score"),
            "reason": candidate.get("reason"),
        }
        for candidate in candidates
    ]


def path_summary_rows(paths: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return display rows for ranked RCA paths."""
    return [
        {
            "path_id": path.get("path_id"),
            "source_entity_id": path.get("source_entity_id"),
            "target_entity_id": path.get("target_entity_id"),
            "score": path.get("score"),
            "confidence": path.get("confidence"),
            "evidence_match": path.get("evidence_match"),
            "length": path.get("length"),
            "relations": " -> ".join(cast(list[str], path.get("relations", []))),
            "nodes": " -> ".join(cast(list[str], path.get("node_names", []))),
        }
        for path in paths
    ]


def edge_summary_rows(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return display rows for KG source edge provenance."""
    return [
        {
            "edge_id": edge.get("edge_id"),
            "head": edge.get("head"),
            "relation": edge.get("relation"),
            "tail": edge.get("tail"),
            "source": edge.get("source"),
            "evidence": edge.get("evidence"),
            "confidence": edge.get("confidence"),
            "review_status": edge.get("review_status"),
        }
        for edge in edges
    ]


def main() -> None:
    """Run the Streamlit demo."""
    import streamlit as st
    from pydantic import ValidationError

    st.set_page_config(page_title="KGTraceVis Demo", layout="wide")
    st.title("KGTraceVis Demo")

    try:
        cases = load_example_cases()
    except ValueError as exc:
        st.error(str(exc))
        return

    selected_label = cast(str, st.sidebar.selectbox("Case", list(cases)))
    base_evidence = cases[selected_label]

    st.sidebar.header("What-if")
    anomaly_type = st.sidebar.text_input("Anomaly type", value=base_evidence.anomaly_type)
    location = st.sidebar.text_input("Location", value=base_evidence.location or "")
    morphology = st.sidebar.text_input("Morphology", value=base_evidence.morphology or "")
    variables_text = st.sidebar.text_area(
        "Variables",
        value=format_list_text(base_evidence.raw_evidence.variables),
    )
    log_events_text = st.sidebar.text_area(
        "Log events",
        value=format_list_text(base_evidence.raw_evidence.log_events),
    )

    try:
        evidence = build_what_if_evidence(
            base_evidence,
            anomaly_type=anomaly_type,
            location=location,
            morphology=morphology,
            variables_text=variables_text,
            log_events_text=log_events_text,
        )
    except ValidationError as exc:
        st.error("Edited evidence is not valid.")
        st.json(exc.errors())
        return

    pipeline = KGTracePipeline()
    result = pipeline.analyze(evidence)
    analyzed_payload = evidence_with_analysis(evidence, result)

    score = "n/a" if result.consistency_score is None else f"{result.consistency_score:.4f}"
    col_case, col_score, col_links, col_paths = st.columns(4)
    col_case.metric("Case", evidence.case_id)
    col_score.metric("Consistency", score)
    col_links.metric("Linked entities", len(result.linked_entities))
    col_paths.metric("Top-k paths", len(result.top_k_paths))

    raw_tab, analysis_tab, provenance_tab = st.tabs(
        ["Evidence", "KG analysis", "Source provenance"]
    )

    with raw_tab:
        left, right = st.columns(2)
        with left:
            st.subheader("Core fields")
            st.json(
                {
                    "case_id": evidence.case_id,
                    "dataset": evidence.dataset,
                    "source": evidence.source,
                    "object": evidence.object,
                    "anomaly_type": evidence.anomaly_type,
                    "location": evidence.location,
                    "morphology": evidence.morphology,
                    "severity": evidence.severity,
                    "confidence": evidence.confidence,
                    "timestamp": evidence.timestamp,
                }
            )
        with right:
            st.subheader("Raw evidence")
            st.json(evidence.raw_evidence.model_dump(mode="json"))
        st.subheader("Evidence payload with analysis")
        st.json(analyzed_payload)

    with analysis_tab:
        st.subheader("Linked entities")
        _render_table_or_empty(st, link_summary_rows(result.linked_entities), "No linked entities.")
        _render_link_candidates(st, result.linked_entities)

        st.subheader("Consistency")
        st.json(
            {
                "consistency_score": result.consistency_score,
                "inconsistent_fields": result.inconsistent_fields,
            }
        )

        st.subheader("Correction candidates")
        _render_table_or_empty(
            st,
            correction_summary_rows(result.correction_candidates),
            "No correction candidates.",
        )
        _render_correction_details(st, result.correction_candidates)

        st.subheader("Top-k RCA paths")
        _render_table_or_empty(st, path_summary_rows(result.top_k_paths), "No RCA paths.")
        _render_path_details(st, result.top_k_paths)

    with provenance_tab:
        st.subheader("Correction source edges")
        correction_edges = _collect_edges(result.correction_candidates, "supporting_edges")
        _render_table_or_empty(st, edge_summary_rows(correction_edges), "No correction edges.")

        st.subheader("Path source edges")
        path_edges = _collect_edges(result.top_k_paths, "source_edges")
        _render_table_or_empty(st, edge_summary_rows(path_edges), "No path edges.")


def _required_text(value: str) -> str:
    stripped = value.strip()
    return stripped or "unknown"


def _optional_text(value: str) -> str | None:
    stripped = value.strip()
    return stripped or None


def _collect_edges(items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        for edge in cast(list[dict[str, Any]], item.get(key, [])):
            edge_id = str(edge.get("edge_id", ""))
            if edge_id in seen:
                continue
            seen.add(edge_id)
            edges.append(edge)
    return edges


def _render_table_or_empty(st: Any, rows: list[dict[str, Any]], empty_message: str) -> None:
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info(empty_message)


def _render_link_candidates(st: Any, links: list[dict[str, Any]]) -> None:
    for link in links:
        candidates = cast(list[dict[str, Any]], link.get("candidates", []))
        if not candidates:
            continue
        label = f"{link.get('field')}: {link.get('mention')}"
        with st.expander(label):
            st.dataframe(candidates, use_container_width=True, hide_index=True)


def _render_correction_details(st: Any, candidates: list[dict[str, Any]]) -> None:
    for candidate in candidates:
        label = str(candidate.get("candidate_id", "candidate"))
        with st.expander(label):
            st.json(candidate)


def _render_path_details(st: Any, paths: list[dict[str, Any]]) -> None:
    for path in paths:
        label = str(path.get("path_id", "path"))
        with st.expander(label):
            st.json(path)


if __name__ == "__main__":
    main()
