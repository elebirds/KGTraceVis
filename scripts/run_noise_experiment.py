"""Run deterministic v0 noise reproducibility checks over checked-in examples."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from kgtracevis.core import KGTracePipeline
from kgtracevis.core.result import AnalysisResult
from kgtracevis.metrics import (
    correction_accuracy,
    entity_linking_accuracy,
    inconsistency_detection_precision_recall,
    mean_reciprocal_rank,
    noise_recovery_rate,
    path_hit_rate,
    schema_validity_rate,
    top_k_correction_accuracy,
    top_k_linking_accuracy,
    top_k_root_cause_accuracy,
)
from kgtracevis.noise.noise_injector import inject_noise
from kgtracevis.schema.evidence_schema import Evidence
from kgtracevis.schema.validators import load_evidence_json


def main() -> None:
    """Run the configured noise experiment and write a compact JSON summary."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--noise-config", default="configs/noise_config.yaml")
    parser.add_argument("--experiment-config", default="configs/experiment_config.yaml")
    args = parser.parse_args()

    noise_config = _read_yaml(Path(args.noise_config))
    experiment_config = _read_yaml(Path(args.experiment_config))

    seed = int(noise_config.get("seed", experiment_config.get("seed", 42)))
    noise_levels = [float(value) for value in noise_config.get("noise_levels", [])]
    noise_types = [str(value) for value in noise_config.get("supported_noise_types", [])]
    input_dir = Path(str(experiment_config.get("input_dir", "data/examples")))
    output_root = Path(str(experiment_config.get("output_dir", "runs")))
    experiment_name = str(experiment_config.get("experiment_name", "noise_v0"))
    top_k = int(experiment_config.get("top_k", 5))

    evidence_items = _load_examples(input_dir)
    pipeline = KGTracePipeline()
    clean_results = {item.case_id: pipeline.analyze(item) for item in evidence_items}

    records: list[dict[str, Any]] = []
    grouped: dict[tuple[float, str], list[dict[str, Any]]] = defaultdict(list)
    for noise_level in noise_levels:
        for noise_type in noise_types:
            for evidence in evidence_items:
                noisy = inject_noise(evidence, noise_type, noise_level, seed=seed)
                noisy_result = pipeline.analyze(noisy)
                record = _record_metrics(
                    clean_results[evidence.case_id],
                    noisy,
                    noisy_result,
                    top_k=top_k,
                )
                records.append(record)
                grouped[(noise_level, noise_type)].append(record)

    summary = {
        "experiment_name": experiment_name,
        "metric_scope": "v0_reproducibility_check",
        "metric_note": (
            "Metrics compare noisy pipeline outputs with clean-run references "
            "for reproducibility checks; they are not paper-grade ground-truth claims."
        ),
        "seed": seed,
        "input_dir": str(input_dir),
        "case_count": len(evidence_items),
        "noise_levels": noise_levels,
        "noise_types": noise_types,
        "overall": _aggregate(records),
        "by_noise": [
            {
                "noise_level": noise_level,
                "noise_type": noise_type,
                **_aggregate(items),
            }
            for (noise_level, noise_type), items in sorted(grouped.items())
        ],
        "records": records,
    }

    output_dir = output_root / experiment_name
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "summary.json"
    output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(
        "noise experiment "
        f"name={experiment_name}, cases={len(evidence_items)}, "
        f"records={len(records)}, output={output_path}"
    )
    print(json.dumps(summary["overall"], indent=2))


def _read_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return data


def _load_examples(input_dir: Path) -> list[Evidence]:
    paths = sorted(input_dir.glob("*.json"))
    if not paths:
        raise ValueError(f"no example JSON files found in {input_dir}")
    return [load_evidence_json(path) for path in paths]


def _record_metrics(
    clean_result: AnalysisResult,
    noisy: Evidence,
    noisy_result: AnalysisResult,
    *,
    top_k: int,
) -> dict[str, Any]:
    extra = noisy.raw_evidence.extra
    corrupted_fields = [str(field) for field in extra.get("corrupted_fields", [])]
    expected_inconsistent = [_metric_field(field) for field in corrupted_fields]

    gold_link_ids, predicted_link_ids, predicted_link_candidates = _linking_inputs(
        clean_result,
        noisy_result,
    )
    gold_corrections, predicted_corrections, correction_candidates = _correction_inputs(
        clean_result,
        noisy_result,
        expected_inconsistent,
    )
    clean_targets = [path.get("target_entity_id") for path in clean_result.top_k_paths[:top_k]]
    noisy_paths = noisy_result.top_k_paths[:top_k]

    detection = inconsistency_detection_precision_recall(
        [expected_inconsistent],
        [noisy_result.inconsistent_fields],
    )
    return {
        "case_id": noisy.case_id,
        "noise_level": extra.get("noise_level"),
        "noise_type": extra.get("noise_type"),
        "is_noisy": extra.get("is_noisy"),
        "corrupted_fields": corrupted_fields,
        "schema_validity_rate": schema_validity_rate([noisy]),
        "entity_linking_accuracy": entity_linking_accuracy(gold_link_ids, predicted_link_ids),
        "top_k_linking_accuracy": top_k_linking_accuracy(
            gold_link_ids,
            predicted_link_candidates,
            k=top_k,
        ),
        "inconsistency_precision": detection["precision"],
        "inconsistency_recall": detection["recall"],
        "correction_accuracy": correction_accuracy(gold_corrections, predicted_corrections),
        "top_k_correction_accuracy": top_k_correction_accuracy(
            gold_corrections,
            correction_candidates,
            k=top_k,
        ),
        "noise_recovery_rate": noise_recovery_rate(gold_corrections, predicted_corrections),
        "top_k_root_cause_accuracy": top_k_root_cause_accuracy(
            [clean_targets],
            [noisy_paths],
            k=top_k,
        ),
        "mrr": mean_reciprocal_rank([clean_targets], [noisy_paths]),
        "path_hit_rate": path_hit_rate(
            [clean_result.top_k_paths[0] if clean_result.top_k_paths else None],
            [noisy_paths],
            k=top_k,
        ),
        "noisy_consistency_score": noisy_result.consistency_score,
        "noisy_inconsistent_fields": noisy_result.inconsistent_fields,
    }


def _linking_inputs(
    clean_result: AnalysisResult,
    noisy_result: AnalysisResult,
) -> tuple[list[str | None], list[str | None], list[list[dict[str, Any]]]]:
    clean_by_field = _links_by_field(clean_result.linked_entities)
    noisy_by_field = _links_by_field(noisy_result.linked_entities)
    fields = sorted(clean_by_field)
    gold = [_string_or_none(clean_by_field[field].get("selected_entity_id")) for field in fields]
    predicted = [
        _string_or_none(noisy_by_field.get(field, {}).get("selected_entity_id")) for field in fields
    ]
    candidates = [
        list(noisy_by_field.get(field, {}).get("candidates", [])) for field in fields
    ]
    return gold, predicted, candidates


def _correction_inputs(
    clean_result: AnalysisResult,
    noisy_result: AnalysisResult,
    fields: list[str],
) -> tuple[list[str], list[dict[str, Any] | None], list[list[dict[str, Any]]]]:
    clean_by_field = _links_by_field(clean_result.linked_entities)
    corrections_by_field: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in noisy_result.correction_candidates:
        field = _metric_field(str(candidate.get("field", candidate.get("target_field", ""))))
        corrections_by_field[field].append(candidate)

    gold: list[str] = []
    predicted: list[dict[str, Any] | None] = []
    candidates: list[list[dict[str, Any]]] = []
    for field in sorted(set(fields)):
        clean_link = clean_by_field.get(field)
        clean_entity_id = (
            _string_or_none(clean_link.get("selected_entity_id")) if clean_link else None
        )
        if clean_entity_id is None:
            continue
        field_candidates = corrections_by_field.get(field, [])
        gold.append(clean_entity_id)
        predicted.append(field_candidates[0] if field_candidates else None)
        candidates.append(field_candidates)
    return gold, predicted, candidates


def _aggregate(records: list[dict[str, Any]]) -> dict[str, Any]:
    metric_names = [
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
    ]
    summary: dict[str, Any] = {"record_count": len(records)}
    for name in metric_names:
        values = [float(record[name]) for record in records]
        summary[name] = round(sum(values) / len(values), 4) if values else 0.0
    return summary


def _links_by_field(links: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {_metric_field(str(link["field"])): link for link in links}


def _metric_field(field: str) -> str:
    if field.startswith("raw_evidence."):
        field = field.removeprefix("raw_evidence.")
    if field in {"variables", "variable_contributions"}:
        return "variable"
    if field == "log_events":
        return "log_event"
    return field


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


if __name__ == "__main__":
    main()
