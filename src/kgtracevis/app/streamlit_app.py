"""Lightweight Streamlit demo for local KGTraceVis evidence analysis."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from kgtracevis.core import KGTracePipeline
from kgtracevis.core.result import AnalysisResult
from kgtracevis.kg.consistency_checker import check_consistency
from kgtracevis.schema.evidence_schema import Evidence, KGAnalysis
from kgtracevis.schema.validators import load_evidence_json

DEFAULT_EXAMPLE_DIR = Path("data/examples")
OBSERVED_FIELD_NAMES = [
    "case_id",
    "dataset",
    "source",
    "object",
    "anomaly_type",
    "location",
    "morphology",
    "severity",
    "confidence",
    "timestamp",
]


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
        raise ValueError(f"未找到 example JSON files: {Path(example_dir)}")
    return cases


def case_label(path: Path, evidence: Evidence) -> str:
    """Return a compact label for selecting an example case."""
    noisy = " 噪声演示" if _is_noisy_demo(evidence) else ""
    return f"{evidence.dataset.upper()}: {evidence.case_id}{noisy} - {path.name}"


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
    payload["normalized_evidence"] = {}
    payload["kg_analysis"] = KGAnalysis().model_dump(mode="json")

    raw_evidence = dict(cast(dict[str, Any], payload["raw_evidence"]))
    raw_evidence["variables"] = parse_list_text(variables_text)
    raw_evidence["log_events"] = parse_list_text(log_events_text)
    payload["raw_evidence"] = raw_evidence
    payload["observations"] = _what_if_observation_payloads(payload)

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


def observed_evidence_rows(evidence: Evidence) -> list[dict[str, Any]]:
    """Return observation-first display rows for observed anomaly evidence."""
    if evidence.observations:
        return [
            {
                "obs_id": observation.obs_id,
                "facet": observation.facet,
                "name": observation.name,
                "display_name": observation.display_name or "",
                "value": _display_value(observation.value),
                "confidence": observation.confidence,
                "source_ref": observation.source_ref or "",
                "raw_ref": observation.raw_ref or "",
            }
            for observation in evidence.observations
        ]
    return _legacy_observed_evidence_rows(evidence)


def _legacy_observed_evidence_rows(evidence: Evidence) -> list[dict[str, Any]]:
    """Return observation-shaped fallback rows for legacy evidence payloads."""
    rows: list[dict[str, Any]] = [
        {
            "obs_id": "",
            "facet": field,
            "name": str(getattr(evidence, field) or ""),
            "display_name": "",
            "value": _display_value(getattr(evidence, field)),
            "confidence": evidence.confidence,
            "source_ref": "legacy top-level field",
            "raw_ref": field,
        }
        for field in OBSERVED_FIELD_NAMES
    ]
    for facet, values in (
        ("variable", evidence.raw_evidence.variables),
        ("log_event", evidence.raw_evidence.log_events),
    ):
        rows.extend(
            {
                "obs_id": "",
                "facet": facet,
                "name": str(value),
                "display_name": "",
                "value": str(value),
                "confidence": evidence.confidence,
                "source_ref": "legacy raw_evidence field",
                "raw_ref": f"raw_evidence.{facet}s",
            }
            for value in values
        )
    if evidence.raw_evidence.description:
        rows.append(
            {
                "obs_id": "",
                "facet": "description",
                "name": "description",
                "display_name": "",
                "value": evidence.raw_evidence.description,
                "confidence": evidence.confidence,
                "source_ref": "legacy raw_evidence field",
                "raw_ref": "raw_evidence.description",
            }
        )
    return rows


def adapter_boundary_rows(evidence: Evidence) -> list[dict[str, Any]]:
    """Return rows explaining the observed-evidence boundary."""
    adapter = evidence.adapter
    adapter_name = adapter.name if adapter is not None else _annotation_source(evidence)
    adapter_version = adapter.version if adapter is not None and adapter.version else "unknown"
    produces_root_cause = adapter.produces_root_cause if adapter is not None else False
    return [
        {"项目": "selected case", "值": evidence.case_id},
        {"项目": "adapter id", "值": adapter_name},
        {"项目": "adapter version", "值": adapter_version},
        {
            "项目": "produces_root_cause",
            "值": f"{str(produces_root_cause).lower()}（adapter 不输出 root cause）",
        },
        {"项目": "source", "值": evidence.source},
        {"项目": "observation count", "值": len(evidence.observations)},
        {"项目": "demo boundary", "值": "v0 curated demo evidence + CSV KG"},
        {"项目": "adapter/manual annotation source", "值": _annotation_source(evidence)},
        {
            "项目": "root cause in input?",
            "值": "否。输入只包含 observed anomaly evidence。",
        },
    ]


def adapter_output_payload(evidence: Evidence) -> dict[str, Any]:
    """Return the structured adapter output before runtime KG analysis."""
    payload = evidence.model_dump(mode="json")
    payload["kg_analysis"] = KGAnalysis().model_dump(mode="json")
    return payload


def adapter_output_rows(evidence: Evidence) -> list[dict[str, Any]]:
    """Return a compact summary of the adapter output contract."""
    kg_analysis = adapter_output_payload(evidence)["kg_analysis"]
    return [
        {
            "字段": "observations",
            "状态": "structured",
            "说明": f"{len(evidence.observations)} 条 observed evidence item",
        },
        {
            "字段": "adapter.produces_root_cause",
            "状态": False if evidence.adapter is None else evidence.adapter.produces_root_cause,
            "说明": "adapter 边界：不产生 root cause",
        },
        {"字段": "root_cause", "状态": "not present", "说明": "输入不提供根因标签"},
        {
            "字段": "kg_analysis.linked_entities",
            "状态": kg_analysis["linked_entities"],
            "说明": "运行前为空",
        },
        {
            "字段": "kg_analysis.correction_candidates",
            "状态": kg_analysis["correction_candidates"],
            "说明": "运行前为空",
        },
        {
            "字段": "kg_analysis.top_k_paths",
            "状态": kg_analysis["top_k_paths"],
            "说明": "运行前为空",
        },
    ]


def link_summary_rows(links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return display rows for linked entity results."""
    rows: list[dict[str, Any]] = []
    for link in links:
        candidates = cast(list[dict[str, Any]], link.get("candidates", []))
        rows.append(
            {
                "link_id": link.get("link_id"),
                "obs_id": link.get("obs_id", ""),
                "facet": link.get("facet", link.get("field")),
                "字段": link.get("field"),
                "文本提及": link.get("mention"),
                "selected_entity_id": link.get("selected_entity_id"),
                "分数": link.get("score"),
                "匹配类型": link.get("match_type"),
                "是否歧义": link.get("ambiguous"),
                "候选 KG nodes": _candidate_list_text(candidates),
                "候选数量": len(cast(list[Any], link.get("candidates", []))),
            }
        )
    return rows


def consistency_check_rows(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return display rows for field-pair KG consistency checks."""
    return [
        {
            "检查字段对": f"{check.get('source_field')} -> {check.get('target_field')}",
            "source_entity_id": check.get("source_entity_id"),
            "target_entity_id": check.get("target_entity_id"),
            "检查关系": " / ".join(cast(list[str], check.get("relations", []))),
            "结果": "通过" if check.get("passed") else "失败",
            "matched_relation": check.get("matched_relation") or "",
        }
        for check in checks
    ]


def correction_summary_rows(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return display rows for correction candidates."""
    return [
        {
            "candidate_id": candidate.get("candidate_id"),
            "字段": candidate.get("field"),
            "原值": candidate.get("original_value"),
            "建议值": candidate.get("suggested_value"),
            "分数": candidate.get("score"),
            "原因": candidate.get("reason"),
            "supporting KG edge": _edge_list_text(
                cast(list[dict[str, Any]], candidate.get("supporting_edges", []))
            ),
        }
        for candidate in candidates
    ]


def path_summary_rows(paths: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return display rows for candidate RCA paths ranked by the pipeline."""
    return [
        {
            "path_id": path.get("path_id"),
            "source_entity_id": path.get("source_entity_id"),
            "target_entity_id": path.get("target_entity_id"),
            "分数": path.get("score"),
            "置信度": path.get("confidence"),
            "证据匹配": path.get("evidence_match"),
            "路径长度": path.get("length"),
            "关系序列": " -> ".join(cast(list[str], path.get("relations", []))),
            "节点序列": " -> ".join(cast(list[str], path.get("node_names", []))),
            "source_edge_ids": _display_value(path.get("source_edge_ids", [])),
        }
        for path in paths
    ]


def path_edge_rows(paths: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return flattened source-edge provenance rows for ranked paths."""
    rows: list[dict[str, Any]] = []
    for path in paths:
        path_id = path.get("path_id")
        for edge in cast(list[dict[str, Any]], path.get("source_edges", [])):
            row = {"path_id": path_id}
            row.update(edge_summary_rows([edge])[0])
            rows.append(row)
    return rows


def path_graphviz_source(path: dict[str, Any]) -> str:
    """Return a Graphviz DOT diagram for one ranked path."""
    path_id = _dot_id(str(path.get("path_id") or "path"))
    node_ids = [str(node_id) for node_id in cast(list[Any], path.get("nodes", []))]
    node_names = [str(name) for name in cast(list[Any], path.get("node_names", []))]
    relations = [str(relation) for relation in cast(list[Any], path.get("relations", []))]
    if not node_names:
        node_names = node_ids
    lines = [
        f"digraph {path_id} {{",
        "  rankdir=LR;",
        '  graph [bgcolor="transparent"];',
        '  node [shape=box, style="rounded,filled", fillcolor="#f8fafc", color="#64748b"];',
        '  edge [color="#475569", fontcolor="#334155"];',
    ]
    for index, node_name in enumerate(node_names):
        node_id = node_ids[index] if index < len(node_ids) else node_name
        label = f"{node_name}\n({node_id})" if node_id != node_name else node_name
        lines.append(f'  n{index} [label="{_dot_escape(label)}"];')
    for index, relation in enumerate(relations):
        if index + 1 >= len(node_names):
            break
        lines.append(f'  n{index} -> n{index + 1} [label="{_dot_escape(relation)}"];')
    lines.append("}")
    return "\n".join(lines)


def path_mermaid_source(path: dict[str, Any]) -> str:
    """Return a Mermaid fallback diagram for one ranked path."""
    node_names = [str(name) for name in cast(list[Any], path.get("node_names", []))]
    relations = [str(relation) for relation in cast(list[Any], path.get("relations", []))]
    if not node_names:
        node_names = [str(node_id) for node_id in cast(list[Any], path.get("nodes", []))]
    lines = ["```mermaid", "flowchart LR"]
    for index, node_name in enumerate(node_names):
        lines.append(f'  n{index}["{_mermaid_escape(node_name)}"]')
    for index, relation in enumerate(relations):
        if index + 1 >= len(node_names):
            break
        lines.append(f'  n{index} -- "{_mermaid_escape(relation)}" --> n{index + 1}')
    lines.append("```")
    return "\n".join(lines)


def source_provenance_rows(
    evidence: Evidence, paths: list[dict[str, Any]], corrections: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Return source references from observations, corrections, and ranked paths."""
    rows = [
        {
            "来源类型": "observation",
            "引用": str(row.get("source_ref") or ""),
            "raw_ref": str(row.get("raw_ref") or ""),
            "关联 ID": str(row.get("obs_id") or ""),
            "说明": f"{row.get('facet')}: {row.get('name')}",
        }
        for row in observed_evidence_rows(evidence)
    ]
    for row in path_edge_rows(paths):
        rows.append(
            {
                "来源类型": "path_edge",
                "引用": str(row.get("source") or ""),
                "raw_ref": str(row.get("edge_id") or ""),
                "关联 ID": str(row.get("path_id") or ""),
                "说明": (
                    f"{row.get('head')} {row.get('relation')} {row.get('tail')} | "
                    f"{row.get('evidence')}"
                ),
            }
        )
    for edge in _collect_edges(corrections, "supporting_edges"):
        edge_row = edge_summary_rows([edge])[0]
        rows.append(
            {
                "来源类型": "correction_edge",
                "引用": str(edge_row.get("source") or ""),
                "raw_ref": str(edge_row.get("edge_id") or ""),
                "关联 ID": str(edge_row.get("edge_id") or ""),
                "说明": (
                    f"{edge_row.get('head')} {edge_row.get('relation')} "
                    f"{edge_row.get('tail')} | {edge_row.get('evidence')}"
                ),
            }
        )
    return rows


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


def demo_case_notes(evidence: Evidence) -> list[str]:
    """Return short live-demo notes derived from evidence metadata."""
    notes = [
        f"场景：{evidence.dataset}",
        "输入边界：adapters/manual demo annotations provide observed anomaly evidence only。",
        "运行时分析：KGTracePipeline computes linking/consistency/corrections/"
        "candidate RCA paths at runtime。",
        "范围：仓库内 v0 demo evidence 与 source-constrained CSV KG。",
    ]
    if _is_noisy_demo(evidence):
        corrupted = evidence.raw_evidence.extra.get("corrupted_fields", [])
        notes.append(
            "噪声演示案例：intentionally corrupted fields="
            f"{_format_field_list(corrupted)}。"
        )
        clean_reference = evidence.raw_evidence.extra.get("clean_reference", {})
        if isinstance(clean_reference, dict):
            clean_fields = _clean_reference_fields(clean_reference, corrupted)
            if clean_fields:
                notes.append(f"干净参考：{clean_fields}。")
    if evidence.dataset == "mvtec":
        notes.append(
            "MVTec RCA source edges 是 curated plausible references；展示的 paths "
            "是 KGTracePipeline runtime candidates，不是原生 factory RCA labels。"
        )
    return notes


def main() -> None:
    """Run the Streamlit demo."""
    import streamlit as st
    from pydantic import ValidationError

    st.set_page_config(page_title="KGTraceVis Demo", layout="wide")
    st.title("KGTraceVis Runtime Demo")
    st.caption(
        "输入 observed evidence；KGTracePipeline 在运行时计算 "
        "linking、consistency/corrections 与 candidate RCA paths，并展示 source edge provenance。"
    )

    try:
        cases = load_example_cases()
    except ValueError as exc:
        st.error(str(exc))
        return

    selected_label = cast(str, st.sidebar.selectbox("案例", list(cases)))
    base_evidence = cases[selected_label]
    st.sidebar.caption("\n".join(f"- {note}" for note in demo_case_notes(base_evidence)))

    st.sidebar.header("What-if 编辑")
    anomaly_type = st.sidebar.text_input("anomaly_type", value=base_evidence.anomaly_type)
    location = st.sidebar.text_input("location", value=base_evidence.location or "")
    morphology = st.sidebar.text_input("morphology", value=base_evidence.morphology or "")
    variables_text = st.sidebar.text_area(
        "variables",
        value=format_list_text(base_evidence.raw_evidence.variables),
    )
    log_events_text = st.sidebar.text_area(
        "log_events",
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
        st.error("编辑后的 evidence 未通过 schema validation。")
        st.json(exc.errors())
        return

    pipeline = KGTracePipeline()
    result = pipeline.analyze(evidence)
    # Reuse the core checker only to expose per-field display details.
    consistency_detail = check_consistency(evidence, pipeline.graph, result.linked_entities)
    analyzed_payload = evidence_with_analysis(evidence, result)

    score = "n/a" if result.consistency_score is None else f"{result.consistency_score:.4f}"
    col_case, col_dataset, col_score, col_links, col_paths = st.columns(5)
    col_case.metric("案例", evidence.case_id)
    col_dataset.metric("场景", evidence.dataset)
    col_score.metric("一致性", score)
    col_links.metric("链接实体", len(result.linked_entities))
    col_paths.metric("Top-k 路径", len(result.top_k_paths))

    st.header("可视分析工作台")

    st.subheader("Adapter 输出 / Observed Evidence")
    st.caption(
        "Adapter/manual annotation 只输出 observations；`produces_root_cause=false`，"
        "`kg_analysis` 在进入 KGTracePipeline 前为空。"
    )
    adapter_cols = st.columns(3)
    adapter = evidence.adapter
    adapter_cols[0].metric("adapter id", adapter.name if adapter is not None else "manual")
    adapter_cols[1].metric(
        "adapter version",
        adapter.version if adapter is not None and adapter.version else "unknown",
    )
    adapter_cols[2].metric(
        "produces_root_cause",
        str(False if adapter is None else adapter.produces_root_cause).lower(),
    )
    _render_table_or_empty(st, adapter_output_rows(evidence), "暂无 adapter 输出。")

    st.subheader("Evidence Item Board / 证据项看板")
    st.caption("每行是一个可审阅 observation item，保留 obs_id、facet、原始引用和 adapter 来源。")
    board_left, board_right = st.columns([1, 2])
    with board_left:
        _render_table_or_empty(st, adapter_boundary_rows(evidence), "暂无输入边界信息。")
    with board_right:
        _render_table_or_empty(st, observed_evidence_rows(evidence), "暂无 observed evidence。")

    st.subheader("Linking Map / 实体链接映射")
    st.caption(
        "KGTracePipeline 运行时把 observation mention 链接到 CSV KG nodes，"
        "并保留候选与歧义信息。"
    )
    _render_table_or_empty(
        st,
        link_summary_rows(result.linked_entities),
        "暂无 linked entities。",
    )
    _render_link_candidates(st, result.linked_entities)

    st.subheader("Consistency Check Table / 一致性检查表")
    st.caption("一致性分数来自实体链接覆盖率与字段对关系检查；失败字段会进入修正候选生成。")
    consistency_cols = st.columns(2)
    consistency_cols[0].metric("consistency_score", score)
    consistency_cols[1].metric("inconsistent_fields", len(result.inconsistent_fields))
    _render_table_or_empty(
        st,
        consistency_check_rows(cast(list[dict[str, Any]], consistency_detail.get("checks", []))),
        "暂无可检查的 field-pair relations。",
    )
    st.write({"inconsistent_fields": result.inconsistent_fields})

    st.subheader("Correction Candidate Panel / 修正候选面板")
    st.caption("修正候选只针对检测到的不一致字段，保留原值、建议值和 supporting KG edge。")
    _render_table_or_empty(
        st,
        correction_summary_rows(result.correction_candidates),
        "暂无 correction candidates。",
    )
    _render_correction_details(st, result.correction_candidates)

    st.subheader("Candidate Path Explorer / 候选路径探索器")
    st.caption(
        "这些是 KGTracePipeline runtime candidates。对 MVTec，它们是 plausible explanations，"
        "不是 verified factory RCA labels。"
    )
    _render_table_or_empty(
        st,
        path_summary_rows(result.top_k_paths),
        "暂无 candidate RCA paths。",
    )
    _render_path_details(st, result.top_k_paths)

    st.subheader("Source Provenance Panel / 来源追溯面板")
    st.caption(
        "汇总 observation source_ref/raw_ref、path source edges 与 "
        "correction supporting edges。"
    )
    _render_table_or_empty(
        st,
        source_provenance_rows(evidence, result.top_k_paths, result.correction_candidates),
        "暂无 provenance rows。",
    )

    st.subheader("JSON / Debug")
    st.caption("完整 JSON 仅作为调试核查视图；主流程以上面的分析视图为准。")
    with st.expander("查看 adapter output JSON"):
        st.json(adapter_output_payload(evidence))
    with st.expander("查看带运行时分析结果的 evidence payload"):
        st.json(analyzed_payload)


def _required_text(value: str) -> str:
    stripped = value.strip()
    return stripped or "unknown"


def _optional_text(value: str) -> str | None:
    stripped = value.strip()
    return stripped or None


def _is_noisy_demo(evidence: Evidence) -> bool:
    return bool(evidence.raw_evidence.extra.get("is_noisy"))


def _format_field_list(values: Any) -> str:
    if not isinstance(values, list):
        return "unknown"
    fields = [str(value) for value in values if str(value).strip()]
    return ", ".join(fields) if fields else "none"


def _clean_reference_fields(clean_reference: dict[str, Any], fields: Any) -> str:
    if not isinstance(fields, list):
        return ""
    parts = [
        f"{field}={clean_reference[field]}"
        for field in fields
        if isinstance(field, str) and field in clean_reference
    ]
    return ", ".join(parts)


def _annotation_source(evidence: Evidence) -> str:
    demo_scope = evidence.raw_evidence.extra.get("demo_scope")
    if demo_scope:
        return str(demo_scope)
    return f"{evidence.dataset} adapter/manual annotation"


def _what_if_observation_payloads(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Build simple edited observations so the linker consumes fresh values."""
    case_id = str(payload["case_id"])
    confidence = payload.get("confidence")
    source_ref = "what-if editor"
    rows: list[dict[str, Any]] = []
    occurrences: dict[tuple[str, str], int] = {}
    for facet in ("object", "anomaly_type", "location", "morphology"):
        value = payload.get(facet)
        if value is None or str(value).strip() == "":
            continue
        rows.append(
            _what_if_observation_payload(
                case_id,
                facet,
                str(value),
                confidence=confidence,
                source_ref=source_ref,
                raw_ref=facet,
                occurrence=_next_observation_occurrence(occurrences, facet, str(value)),
            )
        )
    raw_evidence = cast(dict[str, Any], payload.get("raw_evidence", {}))
    for variable in cast(list[Any], raw_evidence.get("variables", [])):
        rows.append(
            _what_if_observation_payload(
                case_id,
                "variable",
                str(variable),
                confidence=confidence,
                source_ref=source_ref,
                raw_ref="raw_evidence.variables",
                occurrence=_next_observation_occurrence(occurrences, "variable", str(variable)),
            )
        )
    for event in cast(list[Any], raw_evidence.get("log_events", [])):
        rows.append(
            _what_if_observation_payload(
                case_id,
                "log_event",
                str(event),
                confidence=confidence,
                source_ref=source_ref,
                raw_ref="raw_evidence.log_events",
                occurrence=_next_observation_occurrence(occurrences, "log_event", str(event)),
            )
        )
    severity = payload.get("severity")
    if severity is not None:
        rows.append(
            _what_if_observation_payload(
                case_id,
                "severity",
                "severity",
                value=severity,
                value_type="float",
                confidence=confidence,
                source_ref=source_ref,
                raw_ref="severity",
                occurrence=_next_observation_occurrence(occurrences, "severity", "severity"),
            )
        )
    return rows


def _what_if_observation_payload(
    case_id: str,
    facet: str,
    name: str,
    *,
    value: Any | None = None,
    value_type: str | None = None,
    confidence: Any | None = None,
    source_ref: str,
    raw_ref: str,
    occurrence: int = 1,
) -> dict[str, Any]:
    obs_id = f"obs_{_stable_token(case_id)}_{_stable_token(facet)}_{_stable_token(name)}"
    if occurrence > 1:
        obs_id = f"{obs_id}_{occurrence:02d}"
    payload: dict[str, Any] = {
        "obs_id": obs_id,
        "facet": facet,
        "name": name,
        "confidence": confidence,
        "source_ref": source_ref,
        "raw_ref": raw_ref,
        "metadata": {"what_if": True},
    }
    if value is not None:
        payload["value"] = value
    if value_type is not None:
        payload["value_type"] = value_type
    return payload


def _display_value(value: Any) -> Any:
    if value is None:
        return "unknown"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else "[]"
    if isinstance(value, dict):
        return value if value else "{}"
    return value


def _candidate_list_text(candidates: list[dict[str, Any]]) -> str:
    if not candidates:
        return "[]"
    parts = []
    for candidate in candidates:
        entity_id = candidate.get("entity_id")
        score = candidate.get("score")
        match_type = candidate.get("match_type")
        parts.append(f"{entity_id}({score}, {match_type})")
    return "; ".join(parts)


def _edge_list_text(edges: list[dict[str, Any]]) -> str:
    if not edges:
        return "[]"
    return "; ".join(_edge_reference(edge) for edge in edges)


def _edge_reference(edge: dict[str, Any]) -> str:
    edge_id = edge.get("edge_id")
    if edge_id:
        return str(edge_id)
    head = edge.get("head")
    relation = edge.get("relation")
    tail = edge.get("tail")
    if head and relation and tail:
        return f"{head}|{relation}|{tail}"
    return str(edge)


def _collect_edges(items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item_index, item in enumerate(items):
        for edge in cast(list[dict[str, Any]], item.get(key, [])):
            edge_id = _edge_dedupe_key(edge, item_index, len(edges))
            if edge_id in seen:
                continue
            seen.add(edge_id)
            edges.append(edge)
    return edges


def _edge_dedupe_key(edge: dict[str, Any], item_index: int, edge_index: int) -> str:
    edge_id = edge.get("edge_id")
    if edge_id:
        return str(edge_id)
    parts = [edge.get(name) for name in ("head", "relation", "tail", "scenario")]
    if all(parts):
        return "|".join(str(part) for part in parts)
    return f"missing-edge-id:{item_index}:{edge_index}"


def _next_observation_occurrence(
    occurrences: dict[tuple[str, str], int],
    facet: str,
    name: str,
) -> int:
    key = (facet, name)
    occurrences[key] = occurrences.get(key, 0) + 1
    return occurrences[key]


def _stable_token(value: str) -> str:
    return "_".join("".join(ch.lower() if ch.isalnum() else " " for ch in value).split())


def _dot_id(value: str) -> str:
    token = _stable_token(value)
    if not token:
        return "kgtracevis_path"
    if token[0].isdigit():
        return f"path_{token}"
    return token


def _dot_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _mermaid_escape(value: str) -> str:
    return value.replace('"', "'").replace("\n", " ")


def _render_table_or_empty(st: Any, rows: list[dict[str, Any]], empty_message: str) -> None:
    if rows:
        st.dataframe(rows, width="stretch", hide_index=True)
    else:
        st.info(empty_message)


def _render_link_candidates(st: Any, links: list[dict[str, Any]]) -> None:
    for link in links:
        candidates = cast(list[dict[str, Any]], link.get("candidates", []))
        if not candidates:
            continue
        label = f"{link.get('field')}: {link.get('mention')}"
        with st.expander(label):
            st.dataframe(candidates, width="stretch", hide_index=True)


def _render_correction_details(st: Any, candidates: list[dict[str, Any]]) -> None:
    for candidate in candidates:
        label = str(candidate.get("candidate_id", "candidate"))
        with st.expander(label):
            st.json(candidate)


def _render_path_details(st: Any, paths: list[dict[str, Any]]) -> None:
    for path in paths:
        label = str(path.get("path_id", "path"))
        with st.expander(label):
            if hasattr(st, "graphviz_chart"):
                st.graphviz_chart(path_graphviz_source(path), use_container_width=True)
            else:
                st.markdown(path_mermaid_source(path))
            st.json(path)


if __name__ == "__main__":
    main()
