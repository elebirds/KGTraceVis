"""Build paper-facing manifests from generated experiment artifacts."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kgtracevis.adapters.batch import load_records
from kgtracevis.schema.validators import load_evidence_json

DEFAULT_ADAPTER_SUMMARY_PATHS = (
    Path("runs/v0_experiment_suite/adapter_pipeline_mvtec/adapter_pipeline_summary.json"),
    Path("runs/v0_experiment_suite/adapter_pipeline_wm811k/adapter_pipeline_summary.json"),
)
DEFAULT_NOISE_SUMMARY_PATH = Path("runs/v0_examples/summary.json")
DEFAULT_SUITE_SUMMARY_PATH = Path("runs/v0_experiment_suite/summary.json")
DEFAULT_OUTPUT_DIR = Path("artifacts/paper_tables_v0")

PAPER_MANIFEST_FILENAME = "paper_manifest.csv"
COMMAND_MANIFEST_FILENAME = "command_manifest.csv"
SUMMARY_FILENAME = "paper_tables_summary.json"
DEFAULT_CLAIM_BOUNDARY = (
    "v0 reproducibility output over checked-in examples; MVTec/WM811K paths are "
    "candidate/plausible explanations, not verified process RCA"
)

MANIFEST_COLUMNS = (
    "dataset",
    "noise_type",
    "annotation_type",
    "metric_scope",
    "source_artifact",
    "source_command",
    "record_count",
    "case_count",
    "claim_boundary",
    "artifact_kind",
    "source_stage",
    "adapter_name",
    "metric_names",
)
COMMAND_COLUMNS = (
    "stage",
    "status",
    "source_command",
    "output_paths",
    "source_artifact",
    "metric_scope",
    "claim_boundary",
)

METRIC_FIELDS = (
    "schema_validity_rate",
    "entity_linking_accuracy",
    "top_k_linking_accuracy",
    "inconsistency_precision",
    "inconsistency_recall",
    "correction_accuracy",
    "top_k_correction_accuracy",
    "noise_recovery_rate",
    "top_k_root_cause_accuracy",
    "mrr",
    "path_hit_rate",
)


@dataclass(frozen=True)
class PaperTablesOutput:
    """Paths and row counts produced by the paper table builder."""

    output_dir: Path
    manifest_path: Path
    command_manifest_path: Path
    summary_path: Path
    manifest_rows: list[dict[str, Any]]
    command_rows: list[dict[str, Any]]


def build_paper_tables(
    *,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    adapter_summary_paths: Sequence[str | Path] = DEFAULT_ADAPTER_SUMMARY_PATHS,
    noise_summary_path: str | Path = DEFAULT_NOISE_SUMMARY_PATH,
    suite_summary_path: str | Path = DEFAULT_SUITE_SUMMARY_PATH,
    examples_dir: str | Path = "data/examples",
    references_dir: str | Path = "data/references",
    overwrite: bool = False,
) -> PaperTablesOutput:
    """Build grouped paper-facing CSV/JSON manifests from generated artifacts."""
    destination = Path(output_dir)
    manifest_path = destination / PAPER_MANIFEST_FILENAME
    command_manifest_path = destination / COMMAND_MANIFEST_FILENAME
    summary_path = destination / SUMMARY_FILENAME
    for output_path in (manifest_path, command_manifest_path, summary_path):
        _ensure_can_write(output_path, overwrite=overwrite)

    example_index = load_example_index(Path(examples_dir))
    reference_index = load_reference_index(Path(references_dir))
    suite_summary = _read_json_if_exists(Path(suite_summary_path))
    command_index = _command_index(suite_summary)

    manifest_rows: list[dict[str, Any]] = []
    for adapter_summary_path in adapter_summary_paths:
        artifact_path = Path(adapter_summary_path)
        if not artifact_path.exists():
            continue
        summary = _read_json(artifact_path)
        manifest_rows.extend(
            _adapter_manifest_rows(
                summary,
                source_artifact=artifact_path,
                source_command=command_index.get(str(artifact_path), ""),
            )
        )

    noise_path = Path(noise_summary_path)
    if noise_path.exists():
        noise_summary = _read_json(noise_path)
        manifest_rows.extend(
            _noise_manifest_rows(
                noise_summary,
                source_artifact=noise_path,
                source_command=command_index.get(str(noise_path), ""),
                example_index=example_index,
                reference_index=reference_index,
            )
        )

    command_rows = _suite_command_rows(
        suite_summary,
        source_artifact=Path(suite_summary_path),
    )
    manifest_rows.extend(_suite_manifest_rows(command_rows))

    destination.mkdir(parents=True, exist_ok=True)
    _write_csv(manifest_path, MANIFEST_COLUMNS, manifest_rows)
    _write_csv(command_manifest_path, COMMAND_COLUMNS, command_rows)
    summary_payload = {
        "artifact_type": "paper_tables_v0",
        "artifact_scope": "paper_facing_manifest_from_generated_outputs",
        "output_dir": str(destination),
        "manifest_path": str(manifest_path),
        "command_manifest_path": str(command_manifest_path),
        "manifest_row_count": len(manifest_rows),
        "command_row_count": len(command_rows),
        "source_artifacts": sorted(
            {
                str(path)
                for path in [
                    *[Path(value) for value in adapter_summary_paths],
                    Path(noise_summary_path),
                    Path(suite_summary_path),
                ]
                if path.exists()
            }
        ),
        "claim_boundary": DEFAULT_CLAIM_BOUNDARY,
    }
    summary_path.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")
    return PaperTablesOutput(
        output_dir=destination,
        manifest_path=manifest_path,
        command_manifest_path=command_manifest_path,
        summary_path=summary_path,
        manifest_rows=manifest_rows,
        command_rows=command_rows,
    )


def load_example_index(examples_dir: Path) -> dict[str, dict[str, str]]:
    """Return case-level dataset and adapter metadata from checked-in examples."""
    index: dict[str, dict[str, str]] = {}
    if not examples_dir.exists():
        return index
    for path in sorted(examples_dir.glob("*.json")):
        try:
            evidence = load_evidence_json(path)
        except Exception:
            continue
        index[evidence.case_id] = {
            "dataset": evidence.dataset,
            "adapter_name": evidence.adapter.name if evidence.adapter else "",
        }
    return index


def load_reference_index(references_dir: Path) -> dict[str, dict[str, str]]:
    """Return case-level annotation/reference types from reference CSV files."""
    index: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: {"annotation_type": set(), "label_scope": set()}
    )
    if not references_dir.exists():
        return {}
    for path in sorted(references_dir.glob("*.csv")):
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                case_id = row.get("case_id", "")
                if not case_id:
                    continue
                for key in ("annotation_type", "label_scope"):
                    value = row.get(key, "")
                    if value:
                        index[case_id][key].add(value)
    return {
        case_id: {
            key: "+".join(sorted(values)) if values else ""
            for key, values in fields.items()
        }
        for case_id, fields in index.items()
    }


def _adapter_manifest_rows(
    summary: Mapping[str, Any],
    *,
    source_artifact: Path,
    source_command: str,
) -> list[dict[str, Any]]:
    cases = [case for case in _list_value(summary.get("cases")) if isinstance(case, Mapping)]
    record_annotations = _adapter_record_annotations(summary)
    groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    for case in cases:
        evidence = case.get("generated_evidence")
        evidence_summary = evidence if isinstance(evidence, Mapping) else {}
        dataset = str(case.get("dataset") or evidence_summary.get("dataset") or "unknown")
        adapter_name = str(case.get("adapter_name") or "")
        annotation_type = _adapter_annotation_type(case, record_annotations=record_annotations)
        key = (dataset, adapter_name, annotation_type)
        row = groups.setdefault(
            key,
            _manifest_seed(
                dataset=dataset,
                noise_type="none",
                annotation_type=annotation_type,
                metric_scope="adapter_pipeline_case_summary",
                source_artifact=source_artifact,
                source_command=source_command,
                claim_boundary=str(
                    case.get(
                        "claim_boundary",
                        "candidate/plausible explanation only; not a verified RCA label",
                    )
                ),
                artifact_kind="adapter_pipeline_summary",
                source_stage=_stage_from_artifact(source_artifact),
                adapter_name=adapter_name,
                metric_names=(
                    "case_count,linked_entity_count,consistency_score,"
                    "correction_candidate_count,path_count"
                ),
            ),
        )
        row["case_count"] += 1
        row["record_count"] += 1
    return list(groups.values())


def _noise_manifest_rows(
    summary: Mapping[str, Any],
    *,
    source_artifact: Path,
    source_command: str,
    example_index: Mapping[str, Mapping[str, str]],
    reference_index: Mapping[str, Mapping[str, str]],
) -> list[dict[str, Any]]:
    records = [
        record for record in _list_value(summary.get("records")) if isinstance(record, Mapping)
    ]
    metric_scope = str(summary.get("metric_scope") or "v0_reproducibility_check")
    groups: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    case_sets: dict[tuple[str, str, str, str], set[str]] = defaultdict(set)
    for record in records:
        case_id = str(record.get("case_id", ""))
        dataset = _dataset_for_case(case_id, example_index)
        annotation_type = _annotation_type_for_case(case_id, reference_index)
        noise_type = str(record.get("noise_type") or "unknown")
        key = (dataset, noise_type, annotation_type, metric_scope)
        row = groups.setdefault(
            key,
            _manifest_seed(
                dataset=dataset,
                noise_type=noise_type,
                annotation_type=annotation_type,
                metric_scope=metric_scope,
                source_artifact=source_artifact,
                source_command=source_command,
                claim_boundary=str(summary.get("metric_note") or DEFAULT_CLAIM_BOUNDARY),
                artifact_kind="noise_experiment_summary",
                source_stage="noise_experiment",
                adapter_name="",
                metric_names=",".join(_available_metrics(record)),
            ),
        )
        row["record_count"] += 1
        if case_id:
            case_sets[key].add(case_id)

    for key, case_ids in case_sets.items():
        groups[key]["case_count"] = len(case_ids)
    return list(groups.values())


def _suite_command_rows(
    suite_summary: Mapping[str, Any],
    *,
    source_artifact: Path,
) -> list[dict[str, Any]]:
    commands = [
        command
        for command in _list_value(suite_summary.get("commands"))
        if isinstance(command, Mapping)
    ]
    rows: list[dict[str, Any]] = []
    for command in commands:
        output_paths = [str(path) for path in _list_value(command.get("output_paths"))]
        rows.append(
            {
                "stage": command.get("name", ""),
                "status": "passed" if command.get("passed") else "failed",
                "source_command": _command_string(command.get("command")),
                "output_paths": ";".join(output_paths),
                "source_artifact": str(source_artifact),
                "metric_scope": "command_provenance",
                "claim_boundary": DEFAULT_CLAIM_BOUNDARY,
            }
        )
    return rows


def _suite_manifest_rows(command_rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for command in command_rows:
        rows.append(
            _manifest_seed(
                dataset=_dataset_from_stage(str(command.get("stage", ""))),
                noise_type=_noise_type_from_stage(str(command.get("stage", ""))),
                annotation_type="command_provenance",
                metric_scope="command_provenance",
                source_artifact=Path(str(command.get("source_artifact", ""))),
                source_command=str(command.get("source_command", "")),
                claim_boundary=str(command.get("claim_boundary", DEFAULT_CLAIM_BOUNDARY)),
                artifact_kind="suite_command",
                source_stage=str(command.get("stage", "")),
                adapter_name="",
                metric_names="return_code,duration_seconds,output_paths",
                record_count=0,
                case_count=0,
            )
        )
    return rows


def _manifest_seed(
    *,
    dataset: str,
    noise_type: str,
    annotation_type: str,
    metric_scope: str,
    source_artifact: Path,
    source_command: str,
    claim_boundary: str,
    artifact_kind: str,
    source_stage: str,
    adapter_name: str,
    metric_names: str,
    record_count: int = 0,
    case_count: int = 0,
) -> dict[str, Any]:
    return {
        "dataset": dataset,
        "noise_type": noise_type,
        "annotation_type": annotation_type,
        "metric_scope": metric_scope,
        "source_artifact": str(source_artifact),
        "source_command": source_command,
        "record_count": record_count,
        "case_count": case_count,
        "claim_boundary": claim_boundary,
        "artifact_kind": artifact_kind,
        "source_stage": source_stage,
        "adapter_name": adapter_name,
        "metric_names": metric_names,
    }


def _adapter_record_annotations(summary: Mapping[str, Any]) -> dict[str, str]:
    input_metadata = summary.get("input")
    if not isinstance(input_metadata, Mapping):
        return {}
    record_path = input_metadata.get("record_path")
    if not record_path:
        return {}
    try:
        records = load_records(Path(str(record_path)))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    annotations: dict[str, str] = {}
    for record in records:
        case_id = record.get("case_id")
        annotation_type = record.get("annotation_type")
        if case_id and annotation_type:
            annotations[str(case_id)] = str(annotation_type)
    return annotations


def _adapter_annotation_type(
    case: Mapping[str, Any],
    *,
    record_annotations: Mapping[str, str],
) -> str:
    case_id = str(case.get("case_id") or "")
    if case_id in record_annotations:
        return record_annotations[case_id]
    evidence = case.get("generated_evidence")
    if isinstance(evidence, Mapping):
        value = evidence.get("annotation_type")
        if value:
            return str(value)
    return "demo_synthetic"


def _dataset_for_case(
    case_id: str,
    example_index: Mapping[str, Mapping[str, str]],
) -> str:
    if case_id in example_index:
        return str(example_index[case_id].get("dataset") or "unknown")
    lowered = case_id.lower()
    for prefix, dataset in (("mvtec", "mvtec"), ("tep", "tep"), ("wafer", "wafer")):
        if lowered.startswith(prefix):
            return dataset
    return "unknown"


def _annotation_type_for_case(
    case_id: str,
    reference_index: Mapping[str, Mapping[str, str]],
) -> str:
    metadata = reference_index.get(case_id, {})
    return str(metadata.get("annotation_type") or "checked_in_example")


def _command_index(suite_summary: Mapping[str, Any]) -> dict[str, str]:
    index: dict[str, str] = {}
    commands = [
        command
        for command in _list_value(suite_summary.get("commands"))
        if isinstance(command, Mapping)
    ]
    for command in commands:
        command_text = _command_string(command.get("command"))
        for output_path in _list_value(command.get("output_paths")):
            index[str(output_path)] = command_text
    return index


def _command_string(command: Any) -> str:
    if isinstance(command, list):
        return " ".join(str(part) for part in command)
    return str(command or "")


def _stage_from_artifact(path: Path) -> str:
    parts = set(path.parts)
    if "adapter_pipeline_mvtec" in parts:
        return "adapter_pipeline_mvtec"
    if "adapter_pipeline_wm811k" in parts:
        return "adapter_pipeline_wm811k"
    return path.parent.name or path.stem


def _dataset_from_stage(stage: str) -> str:
    if "mvtec" in stage:
        return "mvtec"
    if "wm811k" in stage or "wafer" in stage:
        return "wafer"
    if "tep" in stage:
        return "tep"
    return "all"


def _noise_type_from_stage(stage: str) -> str:
    return "all" if "noise" in stage else "none"


def _available_metrics(record: Mapping[str, Any]) -> list[str]:
    return [name for name in METRIC_FIELDS if name in record]


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _read_json(path: Path) -> dict[str, Any]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return loaded


def _read_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return _read_json(path)


def _write_csv(
    path: Path,
    fieldnames: Sequence[str],
    rows: Sequence[Mapping[str, Any]],
) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _ensure_can_write(path: Path, *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"{path} already exists; pass --overwrite to replace it")
