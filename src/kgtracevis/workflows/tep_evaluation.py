"""TEP RCA evaluation workflow over the unified adapter pipeline."""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kgtracevis.adapters.tep_adapter import evidence_from_tep_record
from kgtracevis.experiments.adapter_pipeline import run_adapter_pipeline
from kgtracevis.kg.graph import DEFAULT_EDGE_PATHS, DEFAULT_NODE_PATHS, KnowledgeGraph
from kgtracevis.metrics import mean_reciprocal_rank, top_k_root_cause_accuracy
from kgtracevis.producers import TEP_RBC_BACKEND
from kgtracevis.producers.tep_records import (
    DEFAULT_TEP_FAULT_FREE_MAX_ROWS,
    DEFAULT_TEP_N_COMPONENTS,
    DEFAULT_TEP_ROW_STRIDE,
    DEFAULT_TEP_WINDOW_SIZE,
)
from kgtracevis.workflows.dataset_records import DatasetRecordBuildConfig, build_dataset_records
from kgtracevis.workflows.root_cause_provider_selection import build_pipeline
from kgtracevis.workflows.tep_root_kgd import DEFAULT_ROOT_KGD_ASSET_DIR, load_root_kgd_assets

SUMMARY_FILENAME = "tep_rca_evaluation_summary.json"
TABLE_FILENAME = "tep_rca_evaluation_cases.csv"
RECORDS_FILENAME = "tep_records.jsonl"
ADAPTER_OUTPUT_DIRNAME = "adapter_pipeline"
ARTIFACT_TYPE = "tep_rca_evaluation_v1"
DEFAULT_TEP_NODE_PATHS = (Path("data/kg/tep_nodes.csv"),)
DEFAULT_TEP_EDGE_PATHS = (Path("data/kg/tep_edges.csv"),)


@dataclass(frozen=True)
class TepRcaEvaluationConfig:
    """Configuration for a TEP raw-record-to-RCA evaluation run."""

    output_dir: Path
    raw_data_dir: Path = Path("data/raw/tep")
    input_records_path: Path | None = None
    faults: tuple[int, ...] = (1, 2, 6)
    max_runs_per_fault: int = 2
    max_cases: int | None = None
    window_size: int = DEFAULT_TEP_WINDOW_SIZE
    row_stride: int = DEFAULT_TEP_ROW_STRIDE
    fault_free_max_rows: int | None = DEFAULT_TEP_FAULT_FREE_MAX_ROWS
    top_variables: int = 8
    n_components: int | None = DEFAULT_TEP_N_COMPONENTS
    top_k: int = 5
    kg_node_paths: tuple[Path, ...] = DEFAULT_TEP_NODE_PATHS
    kg_edge_paths: tuple[Path, ...] = DEFAULT_TEP_EDGE_PATHS
    use_neo4j_runtime: bool = False
    overwrite: bool = False


@dataclass(frozen=True)
class TepRcaEvaluationOutput:
    """Artifacts produced by a TEP RCA evaluation run."""

    summary_path: Path
    table_path: Path
    records_path: Path
    adapter_summary_path: Path
    summary: dict[str, Any]


def run_tep_rca_evaluation(config: TepRcaEvaluationConfig) -> TepRcaEvaluationOutput:
    """Run TEP producer records through KGTracePipeline and compute RCA metrics."""
    if config.top_k < 1:
        raise ValueError("top_k must be >= 1")
    output_dir = config.output_dir
    summary_path = output_dir / SUMMARY_FILENAME
    table_path = output_dir / TABLE_FILENAME
    _ensure_can_write(summary_path, overwrite=config.overwrite)
    _ensure_can_write(table_path, overwrite=config.overwrite)
    output_dir.mkdir(parents=True, exist_ok=True)

    records_path = _prepare_records(config)
    kg_node_paths = None if config.use_neo4j_runtime else list(config.kg_node_paths)
    kg_edge_paths = None if config.use_neo4j_runtime else list(config.kg_edge_paths)
    adapter_output = run_adapter_pipeline(
        records_path,
        output_dir / ADAPTER_OUTPUT_DIRNAME,
        dataset="tep",
        top_k=config.top_k,
        overwrite=config.overwrite,
        kg_node_paths=kg_node_paths,
        kg_edge_paths=kg_edge_paths,
    )
    graph = (
        KnowledgeGraph.from_paths(
            [*DEFAULT_NODE_PATHS, *config.kg_node_paths],
            [*DEFAULT_EDGE_PATHS, *config.kg_edge_paths],
            skip_missing=True,
        )
        if not config.use_neo4j_runtime
        else KnowledgeGraph.from_default_paths()
    )
    records = _load_jsonl(records_path)
    records_by_case = {str(record.get("case_id")): record for record in records}
    fault_coverage = _fault_coverage(config, records)
    adapter_cases = [
        case for case in adapter_output.summary.get("cases", []) if isinstance(case, Mapping)
    ]
    label_ablation = _label_ablation_audit(
        adapter_cases,
        records_by_case=records_by_case,
        graph=graph,
        top_k=config.top_k,
        use_neo4j_runtime=config.use_neo4j_runtime,
    )
    cases = [
        _case_metrics(
            case,
            records_by_case=records_by_case,
            graph=graph,
            top_k=config.top_k,
            label_ablation=label_ablation["cases_by_id"].get(str(case.get("case_id") or "")),
        )
        for case in adapter_cases
    ]
    metrics = _aggregate_metrics(cases, top_k=config.top_k)
    metrics["explicit_fault_label_ablation_top1_stability"] = label_ablation["top1_stability"]
    summary = {
        "artifact_type": ARTIFACT_TYPE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "claim_boundary": (
            "TEP fault numbers are used only as evaluation references; RCA scoring "
            "uses the configured provider and does not treat labels as input causes."
        ),
        "config": _config_payload(config),
        "records_path": str(records_path),
        "adapter_summary_path": str(adapter_output.summary_path),
        "adapter_table_path": str(adapter_output.table_path),
        "case_count": len(cases),
        "fault_coverage": fault_coverage,
        "metrics": metrics,
        "explicit_fault_label_ablation": {
            key: value for key, value in label_ablation.items() if key != "cases_by_id"
        },
        "cases": cases,
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _write_case_table(cases, table_path)
    return TepRcaEvaluationOutput(
        summary_path=summary_path,
        table_path=table_path,
        records_path=records_path,
        adapter_summary_path=adapter_output.summary_path,
        summary=summary,
    )


def _fault_coverage(
    config: TepRcaEvaluationConfig,
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    observed_counter = Counter(
        fault_number for record in records if (fault_number := _fault_number(record)) is not None
    )
    observed_faults = sorted(observed_counter)
    requested_faults = None if config.input_records_path is not None else sorted(config.faults)
    return {
        "record_source": "input_records" if config.input_records_path is not None else "raw_tep",
        "record_count": len(records),
        "requested_faults": requested_faults,
        "observed_faults": observed_faults,
        "cases_per_fault": {
            str(fault_number): observed_counter[fault_number] for fault_number in observed_faults
        },
        "missing_requested_faults": (
            None
            if requested_faults is None
            else [
                fault_number
                for fault_number in requested_faults
                if fault_number not in observed_counter
            ]
        ),
    }


def _prepare_records(config: TepRcaEvaluationConfig) -> Path:
    if config.input_records_path is not None:
        path = config.input_records_path
        if not path.is_file():
            raise FileNotFoundError(f"TEP record file not found: {path}")
        return path
    records_path = config.output_dir / RECORDS_FILENAME
    build_dataset_records(
        DatasetRecordBuildConfig(
            dataset="tep",
            input_root=config.raw_data_dir,
            output_jsonl=records_path,
            model_backend=TEP_RBC_BACKEND,
            overwrite=config.overwrite,
            max_cases=config.max_cases,
            tep_faults=config.faults,
            tep_window_size=config.window_size,
            tep_row_stride=config.row_stride,
            tep_fault_free_max_rows=config.fault_free_max_rows,
            tep_max_runs_per_fault=config.max_runs_per_fault,
            tep_top_variables=config.top_variables,
            tep_n_components=config.n_components,
        )
    )
    return records_path


def _case_metrics(
    case: Mapping[str, Any],
    *,
    records_by_case: Mapping[str, Mapping[str, Any]],
    graph: KnowledgeGraph,
    top_k: int,
    label_ablation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    case_id = str(case.get("case_id") or "")
    record = records_by_case.get(case_id, {})
    fault_number = _fault_number(record, case)
    expected_id = _expected_fault_candidate_id(fault_number, graph=graph)
    ranked = _list_of_dicts(case.get("ranked_root_causes"))
    paths = _list_of_dicts(case.get("top_k_paths"))
    predicted_ids = [str(item.get("candidate_id") or "") for item in ranked]
    rank = _rank_of(expected_id, predicted_ids)
    return {
        "case_id": case_id,
        "fault_number": fault_number,
        "expected_root_cause_id": expected_id,
        "top1_candidate_id": predicted_ids[0] if predicted_ids else None,
        "explicit_fault_label_ablation_top1_candidate_id": (
            label_ablation.get("top1_candidate_id") if label_ablation else None
        ),
        "explicit_fault_label_ablation_top1_stable": (
            label_ablation.get("top1_stable") if label_ablation else None
        ),
        "rank": rank,
        "hit_at_1": rank == 1,
        "hit_at_3": rank is not None and rank <= 3,
        "hit_at_k": rank is not None and rank <= top_k,
        "reciprocal_rank": (1.0 / rank) if rank else 0.0,
        "path_hit_at_k": _path_hits_root(paths[:top_k], expected_id),
        "ranked_root_causes": ranked,
        "top_k_paths": paths[:top_k],
    }


def _label_ablation_audit(
    adapter_cases: Sequence[Mapping[str, Any]],
    *,
    records_by_case: Mapping[str, Mapping[str, Any]],
    graph: KnowledgeGraph,
    top_k: int,
    use_neo4j_runtime: bool,
) -> dict[str, Any]:
    """Rerun TEP RCA after removing explicit fault labels from producer records."""
    pipeline = build_pipeline() if use_neo4j_runtime else build_pipeline(graph=graph)
    cases_by_id: dict[str, dict[str, Any]] = {}
    changed_case_ids: list[str] = []
    audited_count = 0
    for case in adapter_cases:
        case_id = str(case.get("case_id") or "")
        record = records_by_case.get(case_id)
        if not record:
            continue
        original_top1 = _top1_candidate_id(case)
        scrubbed_record = _scrub_explicit_fault_labels(record)
        scrubbed_evidence = evidence_from_tep_record(scrubbed_record)
        scrubbed_ranked = pipeline.analyze(scrubbed_evidence, top_k=top_k).ranked_root_causes
        scrubbed_top1 = scrubbed_ranked[0].candidate_id if scrubbed_ranked else None
        stable = original_top1 == scrubbed_top1
        audited_count += 1
        if not stable:
            changed_case_ids.append(case_id)
        cases_by_id[case_id] = {
            "case_id": case_id,
            "top1_candidate_id": scrubbed_top1,
            "top1_stable": stable,
        }
    return {
        "scope": "explicit_fault_number_and_fault_id_removed_before_rerunning_rca",
        "case_count": audited_count,
        "top1_stability": (
            (audited_count - len(changed_case_ids)) / audited_count if audited_count else 0.0
        ),
        "changed_case_ids": changed_case_ids,
        "cases_by_id": cases_by_id,
    }


def _top1_candidate_id(case: Mapping[str, Any]) -> str | None:
    ranked = _list_of_dicts(case.get("ranked_root_causes"))
    if not ranked:
        return None
    return str(ranked[0].get("candidate_id") or "") or None


def _scrub_explicit_fault_labels(record: Mapping[str, Any]) -> dict[str, Any]:
    scrubbed = json.loads(json.dumps(record))
    for key in ("fault_number", "fault_id"):
        scrubbed.pop(key, None)
    for container_key in ("extra", "metadata"):
        container = scrubbed.get(container_key)
        if isinstance(container, dict):
            for key in ("fault_number", "fault_id"):
                container.pop(key, None)
    return scrubbed


def _aggregate_metrics(cases: Sequence[Mapping[str, Any]], *, top_k: int) -> dict[str, Any]:
    expected = [case.get("expected_root_cause_id") for case in cases]
    ranked = [case.get("ranked_root_causes", []) for case in cases]
    paths = [case.get("top_k_paths", []) for case in cases]
    count = len(cases)
    return {
        "case_count": count,
        "top1_root_cause_accuracy": top_k_root_cause_accuracy(expected, ranked, k=1),
        "top3_root_cause_accuracy": top_k_root_cause_accuracy(expected, ranked, k=3),
        f"top{top_k}_root_cause_accuracy": top_k_root_cause_accuracy(
            expected,
            ranked,
            k=top_k,
        ),
        "mrr": mean_reciprocal_rank(expected, ranked),
        "path_hit_rate": (
            sum(
                1
                for expected_id, case_paths in zip(expected, paths, strict=False)
                if _path_hits_root(_list_of_dicts(case_paths)[:top_k], str(expected_id))
            )
            / count
            if count
            else 0.0
        ),
    }


def _expected_fault_candidate_id(fault_number: int | None, *, graph: KnowledgeGraph) -> str | None:
    if fault_number is None:
        return None
    root_kgd_expected = _expected_root_kgd_anchor_id(fault_number)
    if root_kgd_expected is not None:
        return root_kgd_expected
    prefix = f"Fault{fault_number:02d}"
    candidates = sorted(
        node.id
        for node in graph.nodes.values()
        if node.scenario == "tep" and node.label == "FaultType" and node.id.startswith(prefix)
    )
    return candidates[0] if candidates else prefix


def _expected_root_kgd_anchor_id(fault_number: int) -> str | None:
    try:
        assets = load_root_kgd_assets(DEFAULT_ROOT_KGD_ASSET_DIR)
    except FileNotFoundError:
        return None
    candidates = sorted(
        str(node_id)
        for node_id, node in assets.graph["nodes"].items()
        if str(node.get("entity_type", "")) == "FaultAnchor"
        and int(fault_number) in {int(value) for value in node.get("fault_numbers", [])}
    )
    return candidates[0] if candidates else None


def _fault_number(*items: Mapping[str, Any]) -> int | None:
    for item in items:
        for key in ("fault_number", "fault_id"):
            value = item.get(key)
            if value not in (None, ""):
                return int(str(value))
        anomaly_type = str(item.get("anomaly_type") or "")
        match = re.search(r"fault[_ -]?(\d+)", anomaly_type, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def _path_hits_root(paths: Sequence[Mapping[str, Any]], expected_id: str | None) -> bool:
    if not expected_id:
        return False
    for path in paths:
        if path.get("root_cause_candidate_id") == expected_id:
            return True
        if path.get("source_entity_id") == expected_id:
            return True
        if expected_id in {str(node_id) for node_id in path.get("nodes") or []}:
            return True
    return False


def _rank_of(expected_id: str | None, predicted_ids: Sequence[str]) -> int | None:
    if not expected_id:
        return None
    for index, candidate_id in enumerate(predicted_ids, start=1):
        if candidate_id == expected_id:
            return index
    return None


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _write_case_table(cases: Sequence[Mapping[str, Any]], output_path: Path) -> None:
    columns = (
        "case_id",
        "fault_number",
        "expected_root_cause_id",
        "top1_candidate_id",
        "explicit_fault_label_ablation_top1_candidate_id",
        "explicit_fault_label_ablation_top1_stable",
        "rank",
        "hit_at_1",
        "hit_at_3",
        "hit_at_k",
        "reciprocal_rank",
        "path_hit_at_k",
    )
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for case in cases:
            writer.writerow({column: case.get(column, "") for column in columns})


def _config_payload(config: TepRcaEvaluationConfig) -> dict[str, Any]:
    return {
        "raw_data_dir": str(config.raw_data_dir),
        "input_records_path": str(config.input_records_path) if config.input_records_path else None,
        "faults": list(config.faults),
        "max_runs_per_fault": config.max_runs_per_fault,
        "max_cases": config.max_cases,
        "window_size": config.window_size,
        "row_stride": config.row_stride,
        "fault_free_max_rows": config.fault_free_max_rows,
        "top_variables": config.top_variables,
        "n_components": config.n_components,
        "top_k": config.top_k,
        "kg_node_paths": [str(path) for path in config.kg_node_paths],
        "kg_edge_paths": [str(path) for path in config.kg_edge_paths],
        "use_neo4j_runtime": config.use_neo4j_runtime,
        "tep_rca_reasoner": "tep_root_kgd",
    }


def _ensure_can_write(path: Path, *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"{path} already exists; pass --overwrite to replace it")
