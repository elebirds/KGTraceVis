"""Strict end-to-end interpretability audit artifacts."""

from __future__ import annotations

import json
import shlex
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kgtracevis.adapters.batch import load_records
from kgtracevis.kg_construction.case_kg_hardening import (
    CLAIM_BOUNDARY,
    audit_mvtec_cases,
    audit_wm811k_cases,
    write_candidate_kg_artifacts,
    write_case_audit_artifacts,
)
from kgtracevis.schema.evidence_schema import DatasetName

DEFAULT_MVTEC_RECORDS = Path("runs/mvtec_calibrated_pipeline/mvtec_calibrated_records.jsonl")
DEFAULT_MVTEC_TABLE = Path(
    "runs/mvtec_calibrated_pipeline/adapter_pipeline/adapter_pipeline_table.csv"
)
DEFAULT_WM811K_RECORDS = (
    Path("runs/wm811k_real_recognition_smoke/wm811k_records.jsonl"),
)
DEFAULT_WM811K_TABLES = (
    Path("runs/wm811k_real_recognition_smoke/adapter_pipeline/adapter_pipeline_table.csv"),
)
DEFAULT_OUTPUT_DIR = Path("runs/end_to_end_interpretability_audit")
SUMMARY_JSON = "end_to_end_interpretability_audit_summary.json"
SUMMARY_MD = "end_to_end_interpretability_audit_summary.md"


@dataclass(frozen=True)
class EndToEndInterpretabilityAuditOutput:
    """Paths produced by the strict interpretability audit."""

    summary_path: Path
    markdown_path: Path
    candidate_kg_dir: Path
    case_ranking_dir: Path
    summary: dict[str, Any]


def write_end_to_end_interpretability_audit(
    *,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    mvtec_records_path: str | Path = DEFAULT_MVTEC_RECORDS,
    mvtec_adapter_table_path: str | Path = DEFAULT_MVTEC_TABLE,
    wm811k_record_paths: Sequence[str | Path] = DEFAULT_WM811K_RECORDS,
    wm811k_adapter_table_paths: Sequence[str | Path] = DEFAULT_WM811K_TABLES,
    top_k: int = 5,
    top_n: int = 8,
    overwrite: bool = False,
    commands_run: Sequence[str] = (),
) -> EndToEndInterpretabilityAuditOutput:
    """Write reproducible end-to-end evidence-to-overlay audit artifacts."""
    destination = Path(output_dir)
    summary_path = destination / SUMMARY_JSON
    markdown_path = destination / SUMMARY_MD
    _ensure_can_write(summary_path, overwrite=overwrite)
    _ensure_can_write(markdown_path, overwrite=overwrite)
    _require_file(Path(mvtec_records_path), "MVTec records")
    _require_file(Path(mvtec_adapter_table_path), "MVTec adapter table")
    existing_wm811k_records = [Path(path) for path in wm811k_record_paths if Path(path).exists()]
    if not existing_wm811k_records:
        raise FileNotFoundError("at least one WM811K records path must exist")
    existing_wm811k_tables = [
        Path(path) for path in wm811k_adapter_table_paths if Path(path).exists()
    ]
    if not existing_wm811k_tables:
        raise FileNotFoundError("at least one WM811K adapter table path must exist")

    destination.mkdir(parents=True, exist_ok=True)
    case_ranking_dir = destination / "case_rankings"
    candidate_kg_dir = destination / "candidate_kg"

    mvtec_rows = audit_mvtec_cases(mvtec_records_path, mvtec_adapter_table_path)
    wm811k_rows = audit_wm811k_cases(existing_wm811k_records, existing_wm811k_tables)
    mvtec_ranking_paths = write_case_audit_artifacts(
        mvtec_rows,
        case_ranking_dir,
        prefix="mvtec",
        top_n=top_n,
    )
    wm811k_ranking_paths = write_case_audit_artifacts(
        wm811k_rows,
        case_ranking_dir,
        prefix="wm811k",
        top_n=top_n,
    )

    before_after_inputs = _before_after_inputs(Path(mvtec_records_path), existing_wm811k_records)
    candidate_output = write_candidate_kg_artifacts(
        output_dir=candidate_kg_dir,
        mvtec_records_path=mvtec_records_path,
        mvtec_adapter_table_path=mvtec_adapter_table_path,
        wm811k_record_paths=existing_wm811k_records,
        before_after_inputs=before_after_inputs,
        top_k=top_k,
        overwrite=overwrite,
    )

    datasets = [
        _dataset_provenance(
            label=label,
            dataset=dataset,
            records_path=records_path,
            candidate_kg_dir=candidate_kg_dir,
            candidate_nodes_path=candidate_output.nodes_path,
            candidate_edges_path=candidate_output.edges_path,
            case_ranking_paths=mvtec_ranking_paths if dataset == "mvtec" else wm811k_ranking_paths,
        )
        for records_path, dataset, label in before_after_inputs
    ]
    strict_findings = _strict_findings(datasets, candidate_output.validation_passed)
    summary = {
        "artifact_type": "strict_end_to_end_interpretability_audit_v0",
        "artifact_scope": "generated_reproducibility_output",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "claim_boundary": CLAIM_BOUNDARY,
        "strict_audit_passed": not strict_findings,
        "strict_findings": strict_findings,
        "commands_run": list(commands_run),
        "equivalent_reproduction_commands": _equivalent_commands(
            output_dir=destination,
            mvtec_records_path=Path(mvtec_records_path),
            mvtec_adapter_table_path=Path(mvtec_adapter_table_path),
            wm811k_record_paths=existing_wm811k_records,
            wm811k_adapter_table_paths=existing_wm811k_tables,
            top_k=top_k,
            top_n=top_n,
        ),
        "artifacts": {
            "summary_json": str(summary_path),
            "summary_markdown": str(markdown_path),
            "candidate_kg_dir": str(candidate_kg_dir),
            "case_ranking_dir": str(case_ranking_dir),
            "candidate_nodes": str(candidate_output.nodes_path),
            "candidate_edges": str(candidate_output.edges_path),
            "candidate_kg_summary": str(candidate_output.summary_path),
            "candidate_kg_validation": str(candidate_output.validation_path),
            "candidate_kg_before_after": str(candidate_output.before_after_path),
            "candidate_kg_top_explanations": str(candidate_output.explanations_path),
        },
        "candidate_kg": {
            "node_count": candidate_output.node_count,
            "edge_count": candidate_output.edge_count,
            "validation_passed": candidate_output.validation_passed,
        },
        "datasets": datasets,
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    markdown_path.write_text(_summary_markdown(summary), encoding="utf-8")
    return EndToEndInterpretabilityAuditOutput(
        summary_path=summary_path,
        markdown_path=markdown_path,
        candidate_kg_dir=candidate_kg_dir,
        case_ranking_dir=case_ranking_dir,
        summary=summary,
    )


def _before_after_inputs(
    mvtec_records_path: Path,
    wm811k_record_paths: Sequence[Path],
) -> list[tuple[Path, DatasetName, str]]:
    inputs: list[tuple[Path, DatasetName, str]] = [(mvtec_records_path, "mvtec", "mvtec")]
    inputs.extend(
        (path, "wafer", f"wm811k_{index}")
        for index, path in enumerate(wm811k_record_paths, 1)
    )
    return inputs


def _dataset_provenance(
    *,
    label: str,
    dataset: DatasetName,
    records_path: Path,
    candidate_kg_dir: Path,
    candidate_nodes_path: Path,
    candidate_edges_path: Path,
    case_ranking_paths: Mapping[str, str],
) -> dict[str, Any]:
    records = load_records(records_path)
    overlay_dir = candidate_kg_dir / f"{label}_before_after" / "overlay"
    base_dir = candidate_kg_dir / f"{label}_before_after" / "base"
    overlay_summary_path = overlay_dir / "adapter_pipeline_summary.json"
    overlay_summary = _load_json_object(overlay_summary_path)
    pipeline = overlay_summary.get("pipeline", {})
    output = overlay_summary.get("output", {})
    evidence_paths = output.get("evidence_paths", [])
    cases = overlay_summary.get("cases", [])
    return {
        "label": label,
        "dataset": dataset,
        "record_count": len(records),
        "records_path": str(records_path),
        "raw_dataset_or_model_producer": _producer_provenance(dataset, records),
        "adapter_evidence_path": str(output.get("evidence_dir", overlay_dir / "evidence")),
        "adapter_evidence_sample_paths": (
            evidence_paths[:5] if isinstance(evidence_paths, list) else []
        ),
        "adapter_evidence_count": len(evidence_paths) if isinstance(evidence_paths, list) else 0,
        "base_reasoning_path": str(base_dir / "adapter_pipeline_summary.json"),
        "overlay_reasoning_path": str(overlay_summary_path),
        "overlay_table_path": str(overlay_dir / "adapter_pipeline_table.csv"),
        "overlay_case_count": len(cases) if isinstance(cases, list) else 0,
        "overlay_kg_node_paths": pipeline.get("kg_node_paths", []),
        "overlay_kg_edge_paths": pipeline.get("kg_edge_paths", []),
        "candidate_kg_overlay": {
            "nodes_path": str(candidate_nodes_path),
            "edges_path": str(candidate_edges_path),
        },
        "case_ranking_paths": dict(case_ranking_paths),
        "stage_chain": [
            "raw dataset/model producer record",
            "Evidence adapter JSON",
            "KGTracePipeline with candidate KG overlay",
        ],
        "claim_boundary": CLAIM_BOUNDARY,
    }


def _producer_provenance(
    dataset: DatasetName,
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    first = records[0] if records else {}
    if dataset == "mvtec":
        complete_records = [
            record for record in records if _is_strict_mvtec_producer_record(record)
        ]
        incomplete_records = [
            record for record in records if not _is_strict_mvtec_producer_record(record)
        ]
        sample = complete_records[0] if complete_records else first
        raw_detector = sample.get("detector")
        detector: Mapping[str, Any] = raw_detector if isinstance(raw_detector, Mapping) else {}
        producer_name = sample.get("model_name") or detector.get("name")
        producer_backend = detector.get("backend") or detector.get("source_backend")
        source_path = sample.get("source_path") or sample.get("image_path")
        checkpoint = detector.get("checkpoint")
        return {
            "producer_provenance_level": (
                "model_producer_record"
                if records and not incomplete_records
                else "fixture_or_incomplete_record"
            ),
            "producer_record_count": len(records),
            "strict_model_producer_record_count": len(complete_records),
            "incomplete_record_count": len(incomplete_records),
            "incomplete_case_id_samples": _case_id_samples(incomplete_records),
            "source_dataset": sample.get("source_dataset", sample.get("dataset")),
            "source_path_sample": source_path,
            "annotation_type_sample": sample.get("annotation_type"),
            "producer_name": producer_name,
            "producer_backend": producer_backend,
            "model_source": detector.get("model_source"),
            "checkpoint_sample": checkpoint,
            "produces_root_cause": False,
        }
    complete_records = [record for record in records if _is_strict_wm811k_producer_record(record)]
    incomplete_records = [
        record for record in records if not _is_strict_wm811k_producer_record(record)
    ]
    sample = complete_records[0] if complete_records else first
    raw_classifier = sample.get("classifier")
    classifier: Mapping[str, Any] = raw_classifier if isinstance(raw_classifier, Mapping) else {}
    producer_name = sample.get("model_name") or classifier.get("name")
    producer_backend = classifier.get("backend") or classifier.get("source_backend")
    source_table = sample.get("source_table")
    source_row_index = sample.get("source_row_index")
    return {
        "producer_provenance_level": (
            "model_producer_record"
            if records and not incomplete_records
            else "fixture_or_incomplete_record"
        ),
        "producer_record_count": len(records),
        "strict_model_producer_record_count": len(complete_records),
        "incomplete_record_count": len(incomplete_records),
        "incomplete_case_id_samples": _case_id_samples(incomplete_records),
        "source_dataset": sample.get("source_dataset", sample.get("dataset")),
        "source_table_sample": source_table,
        "source_row_index_sample": source_row_index,
        "wafer_id_sample": sample.get("wafer_id"),
        "annotation_type_sample": sample.get("annotation_type"),
        "producer_name": producer_name,
        "producer_backend": producer_backend,
        "model_source": classifier.get("model_source"),
        "model_file": classifier.get("model_file"),
        "produces_root_cause": (
            False
            if records
            and all(_wm811k_producer_boundary_is_explicit(record) for record in records)
            else None
        ),
    }


def _is_strict_mvtec_producer_record(record: Mapping[str, Any]) -> bool:
    raw_detector = record.get("detector")
    detector: Mapping[str, Any] = raw_detector if isinstance(raw_detector, Mapping) else {}
    source_path = record.get("source_path") or record.get("image_path")
    producer_name = record.get("model_name") or detector.get("name")
    producer_backend = detector.get("backend") or detector.get("source_backend")
    checkpoint = detector.get("checkpoint")
    return bool(source_path and producer_name and producer_backend and checkpoint)


def _is_strict_wm811k_producer_record(record: Mapping[str, Any]) -> bool:
    raw_classifier = record.get("classifier")
    classifier: Mapping[str, Any] = (
        raw_classifier if isinstance(raw_classifier, Mapping) else {}
    )
    source_table = record.get("source_table")
    source_row_index = record.get("source_row_index")
    producer_name = record.get("model_name") or classifier.get("name")
    producer_backend = classifier.get("backend") or classifier.get("source_backend")
    model_source = classifier.get("model_source")
    model_file = classifier.get("model_file")
    return bool(
        source_table is not None
        and source_row_index is not None
        and producer_name
        and producer_backend
        and model_source
        and model_file
        and _wm811k_producer_boundary_is_explicit(record)
    )


def _wm811k_producer_boundary_is_explicit(record: Mapping[str, Any]) -> bool:
    raw_classifier = record.get("classifier")
    classifier: Mapping[str, Any] = (
        raw_classifier if isinstance(raw_classifier, Mapping) else {}
    )
    return classifier.get("produces_root_cause") is False


def _case_id_samples(records: Sequence[Mapping[str, Any]], *, limit: int = 5) -> list[str]:
    return [str(record.get("case_id", "unknown")) for record in records[:limit]]


def _strict_findings(
    datasets: Sequence[Mapping[str, Any]],
    validation_passed: bool,
) -> list[str]:
    findings: list[str] = []
    if not validation_passed:
        findings.append("candidate KG validation did not pass")
    for item in datasets:
        label = str(item.get("label", "unknown"))
        if int(item.get("record_count", 0)) < 1:
            findings.append(f"{label} has no producer records")
        if int(item.get("adapter_evidence_count", 0)) < 1:
            findings.append(f"{label} has no generated adapter evidence")
        if int(item.get("overlay_case_count", 0)) < 1:
            findings.append(f"{label} has no overlay reasoning cases")
        if not item.get("overlay_kg_node_paths") or not item.get("overlay_kg_edge_paths"):
            findings.append(f"{label} overlay did not record candidate KG node/edge paths")
        producer = item.get("raw_dataset_or_model_producer")
        if not isinstance(producer, Mapping) or producer.get("produces_root_cause") is not False:
            findings.append(f"{label} producer boundary is missing produces_root_cause=False")
        if not isinstance(producer, Mapping):
            findings.append(f"{label} producer provenance is missing")
        elif producer.get("producer_provenance_level") != "model_producer_record":
            findings.append(
                f"{label} is not a strict model-producer record: "
                f"{producer.get('producer_provenance_level', 'unknown')}"
            )
        elif int(producer.get("incomplete_record_count", 0)) > 0:
            findings.append(f"{label} has incomplete producer metadata on some records")
        if item.get("claim_boundary") != CLAIM_BOUNDARY:
            findings.append(f"{label} claim boundary mismatch")
    return findings


def _equivalent_commands(
    *,
    output_dir: Path,
    mvtec_records_path: Path,
    mvtec_adapter_table_path: Path,
    wm811k_record_paths: Sequence[Path],
    wm811k_adapter_table_paths: Sequence[Path],
    top_k: int,
    top_n: int,
) -> list[str]:
    wm_record_args = [
        part
        for path in wm811k_record_paths
        for part in ("--wm811k-record", str(path))
    ]
    wm_table_args = [
        part
        for path in wm811k_adapter_table_paths
        for part in ("--wm811k-table", str(path))
    ]
    return [
        shlex.join(
            [
                "uv",
                "run",
                "python",
                "scripts/audit_case_explainability.py",
                "--mvtec-records",
                str(mvtec_records_path),
                "--mvtec-table",
                str(mvtec_adapter_table_path),
                *wm_record_args,
                *wm_table_args,
                "--output-dir",
                str(output_dir / "case_rankings"),
                "--top-n",
                str(top_n),
            ]
        ),
        shlex.join(
            [
                "uv",
                "run",
                "python",
                "scripts/build_case_kg.py",
                "--mvtec-records",
                str(mvtec_records_path),
                "--mvtec-table",
                str(mvtec_adapter_table_path),
                *wm_record_args,
                "--output-dir",
                str(output_dir / "candidate_kg"),
                "--top-k",
                str(top_k),
                "--overwrite",
            ]
        ),
    ]


def _summary_markdown(summary: Mapping[str, Any]) -> str:
    lines = [
        "# End-to-End Interpretability Audit",
        "",
        str(summary["claim_boundary"]),
        "",
        f"- Strict audit passed: {summary['strict_audit_passed']}",
        f"- Candidate KG validation passed: {summary['candidate_kg']['validation_passed']}",
        f"- Candidate KG nodes: {summary['candidate_kg']['node_count']}",
        f"- Candidate KG edges: {summary['candidate_kg']['edge_count']}",
        "",
        "## Commands Run",
        "",
    ]
    commands = summary.get("commands_run") or []
    if commands:
        lines.extend(f"- `{command}`" for command in commands)
    else:
        lines.append("- Not supplied by caller")
    lines.extend(["", "## Dataset Provenance", ""])
    for dataset in summary.get("datasets", []):
        if not isinstance(dataset, Mapping):
            continue
        lines.extend(
            [
                f"### {dataset.get('label')} ({dataset.get('dataset')})",
                "",
                f"- Records path: `{dataset.get('records_path')}`",
                f"- Adapter evidence path: `{dataset.get('adapter_evidence_path')}`",
                f"- Overlay reasoning path: `{dataset.get('overlay_reasoning_path')}`",
                f"- Overlay table path: `{dataset.get('overlay_table_path')}`",
                f"- Case ranking: `{dataset.get('case_ranking_paths', {}).get('csv_path', '')}`",
                f"- Claim boundary: {dataset.get('claim_boundary')}",
                "",
            ]
        )
    findings = summary.get("strict_findings") or []
    if findings:
        lines.extend(["## Strict Findings", ""])
        lines.extend(f"- {finding}" for finding in findings)
        lines.append("")
    return "\n".join(lines)


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")


def _ensure_can_write(path: Path, *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"{path} already exists; pass --overwrite to replace it")
