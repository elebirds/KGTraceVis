"""Paper-facing MVTec and WM811K case-study evaluation summaries."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kgtracevis.adapters.batch import load_records
from kgtracevis.producers.common import WM811KPrediction, write_jsonl_records
from kgtracevis.producers.wm811k_records import build_wm811k_records

SUMMARY_FILENAME = "paper_case_study_evaluation_summary.json"
MVTEC_OBJECT_TABLE_FILENAME = "mvtec_object_selection.csv"
WM811K_PATTERN_TABLE_FILENAME = "wm811k_pattern_traceability.csv"
WM811K_STRATIFIED_PATTERN_TABLE_FILENAME = "wm811k_stratified_pattern_traceability.csv"
WM811K_STRATIFIED_BUILD_SUMMARY_FILENAME = "wm811k_stratified_build_summary.json"
NATIVE_LABEL_STRATIFIED_BACKEND = "native-label-stratified"

MVTEC_CLAIM_BOUNDARY = (
    "MVTec rows evaluate visual evidence quality, KG completion, and plausible "
    "source-grounded explanations; they are not verified industrial RCA labels."
)
WM811K_CLAIM_BOUNDARY = (
    "WM811K rows evaluate wafer pattern evidence traceability and source-grounded "
    "candidate paths; they are not verified process RCA labels."
)
WM811K_STRATIFIED_CLAIM_BOUNDARY = (
    "WM811K stratified rows evaluate native-label pattern coverage and "
    "traceability/path coverage; they are not classifier-performance or verified "
    "process RCA results."
)

SUPPORTED_WM811K_PATTERNS = (
    "Center",
    "Donut",
    "Edge-Loc",
    "Edge-Ring",
    "Loc",
    "Random",
    "Scratch",
    "Near-full",
)

MVTEC_OBJECT_COLUMNS = (
    "object",
    "record_count",
    "defect_case_count",
    "good_case_count",
    "defect_anomalous_rate",
    "good_normal_rate",
    "visual_model_score",
    "mean_mask_iou",
    "defect_nonzero_mask_rate",
    "mean_consistency_score",
    "mean_linked_entity_count",
    "kg_completeness_score",
    "explainable_path_rate",
    "unique_top_targets",
    "unique_source_count",
    "selection_score",
    "recommendation",
    "claim_boundary",
)

WM811K_PATTERN_COLUMNS = (
    "pattern",
    "record_count",
    "native_count",
    "predicted_count",
    "exact_correct_count",
    "exact_comparable_count",
    "exact_accuracy",
    "mean_classifier_confidence",
    "mean_consistency_score",
    "mean_linked_entity_count",
    "explainable_path_rate",
    "unique_top_targets",
    "unique_source_count",
    "coverage_status",
    "record_source_scope",
    "accuracy_scope",
    "claim_boundary",
)


@dataclass(frozen=True)
class PaperCaseStudyEvaluationConfig:
    """Inputs for paper-facing MVTec/WM811K case-study summaries."""

    output_dir: Path
    mvtec_records_path: Path
    mvtec_adapter_summary_path: Path
    wm811k_records_path: Path
    wm811k_adapter_summary_path: Path
    mvtec_pipeline_summary_path: Path | None = None
    wm811k_stratified_records_path: Path | None = None
    wm811k_stratified_adapter_summary_path: Path | None = None
    overwrite: bool = False


@dataclass(frozen=True)
class WM811KStratifiedBuildConfig:
    """Configuration for native-label WM811K pattern-stratified record builds."""

    input_path: Path
    output_jsonl: Path
    records_per_pattern: int = 1
    seed: int | None = 0
    overwrite: bool = False
    wafer_map_inline_limit: int = 400


@dataclass(frozen=True)
class WM811KStratifiedBuildOutput:
    """Paths and summary payload for a WM811K stratified record build."""

    output_path: Path
    summary_path: Path
    records: list[dict[str, Any]]
    summary: dict[str, Any]


@dataclass(frozen=True)
class PaperCaseStudyEvaluationOutput:
    """Paths and summary payload produced by the paper case-study workflow."""

    summary_path: Path
    mvtec_object_table_path: Path
    wm811k_pattern_table_path: Path
    wm811k_stratified_pattern_table_path: Path | None
    summary: dict[str, Any]


def build_wm811k_stratified_records(
    config: WM811KStratifiedBuildConfig,
) -> WM811KStratifiedBuildOutput:
    """Build a bounded native-label WM811K sample covering supported patterns.

    This workflow is for paper case-study pattern coverage and traceability. It
    does not run or evaluate a defect-pattern classifier.
    """
    if config.records_per_pattern < 1:
        raise ValueError("records_per_pattern must be >= 1")
    output_path = Path(config.output_jsonl)
    summary_path = output_path.with_name(WM811K_STRATIFIED_BUILD_SUMMARY_FILENAME)
    _ensure_can_write(output_path, overwrite=config.overwrite)
    _ensure_can_write(summary_path, overwrite=config.overwrite)

    raw_records = build_wm811k_records(
        config.input_path,
        _NativeLabelStratifiedWM811KClassifier(),
        output_dir=output_path.with_suffix(""),
        model_backend=NATIVE_LABEL_STRATIFIED_BACKEND,
        checkpoint=None,
        max_per_label=config.records_per_pattern,
        seed=config.seed,
        include_unlabeled=False,
        wafer_map_inline_limit=config.wafer_map_inline_limit,
    )
    records = [
        _native_label_stratified_record(record)
        for record in raw_records
        if _wm811k_native_pattern(record) in SUPPORTED_WM811K_PATTERNS
    ]
    output_path = write_jsonl_records(records, output_path, overwrite=config.overwrite)
    summary = _wm811k_stratified_build_summary(
        config=config,
        output_path=output_path,
        summary_path=summary_path,
        records=records,
    )
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return WM811KStratifiedBuildOutput(
        output_path=output_path,
        summary_path=summary_path,
        records=records,
        summary=summary,
    )


def run_paper_case_study_evaluation(
    config: PaperCaseStudyEvaluationConfig,
) -> PaperCaseStudyEvaluationOutput:
    """Build bounded paper-facing summaries from generated MVTec/WM811K artifacts."""
    output_dir = Path(config.output_dir)
    summary_path = output_dir / SUMMARY_FILENAME
    mvtec_table_path = output_dir / MVTEC_OBJECT_TABLE_FILENAME
    wm811k_table_path = output_dir / WM811K_PATTERN_TABLE_FILENAME
    wm811k_stratified_table_path = (
        output_dir / WM811K_STRATIFIED_PATTERN_TABLE_FILENAME
        if config.wm811k_stratified_records_path is not None
        else None
    )
    for path in (
        summary_path,
        mvtec_table_path,
        wm811k_table_path,
        *([wm811k_stratified_table_path] if wm811k_stratified_table_path is not None else []),
    ):
        _ensure_can_write(path, overwrite=config.overwrite)

    mvtec_records = load_records(config.mvtec_records_path)
    wm811k_records = load_records(config.wm811k_records_path)
    mvtec_summary = _read_json(config.mvtec_adapter_summary_path)
    wm811k_summary = _read_json(config.wm811k_adapter_summary_path)
    mvtec_pipeline_summary = (
        _read_json(config.mvtec_pipeline_summary_path)
        if config.mvtec_pipeline_summary_path is not None
        else {}
    )

    mvtec_rows = summarize_mvtec_object_selection(
        records=mvtec_records,
        adapter_summary=mvtec_summary,
        pipeline_summary=mvtec_pipeline_summary,
    )
    wm811k_rows = summarize_wm811k_traceability(
        records=wm811k_records,
        adapter_summary=wm811k_summary,
    )
    wm811k_stratified_rows: list[dict[str, Any]] = []
    wm811k_stratified_summary: dict[str, Any] = {}
    if config.wm811k_stratified_records_path is not None:
        if config.wm811k_stratified_adapter_summary_path is None:
            raise ValueError(
                "--wm811k-stratified-adapter-summary is required when "
                "--wm811k-stratified-records is provided"
            )
        wm811k_stratified_records = load_records(config.wm811k_stratified_records_path)
        wm811k_stratified_summary = _read_json(config.wm811k_stratified_adapter_summary_path)
        wm811k_stratified_rows = summarize_wm811k_traceability(
            records=wm811k_stratified_records,
            adapter_summary=wm811k_stratified_summary,
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(mvtec_table_path, MVTEC_OBJECT_COLUMNS, mvtec_rows)
    _write_csv(wm811k_table_path, WM811K_PATTERN_COLUMNS, wm811k_rows)
    if wm811k_stratified_table_path is not None:
        _write_csv(
            wm811k_stratified_table_path,
            WM811K_PATTERN_COLUMNS,
            wm811k_stratified_rows,
        )
    summary = _evaluation_summary(
        config=config,
        summary_path=summary_path,
        mvtec_table_path=mvtec_table_path,
        wm811k_table_path=wm811k_table_path,
        wm811k_stratified_table_path=wm811k_stratified_table_path,
        mvtec_rows=mvtec_rows,
        wm811k_rows=wm811k_rows,
        wm811k_stratified_rows=wm811k_stratified_rows,
        mvtec_adapter_summary=mvtec_summary,
        wm811k_adapter_summary=wm811k_summary,
        wm811k_stratified_adapter_summary=wm811k_stratified_summary,
    )
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return PaperCaseStudyEvaluationOutput(
        summary_path=summary_path,
        mvtec_object_table_path=mvtec_table_path,
        wm811k_pattern_table_path=wm811k_table_path,
        wm811k_stratified_pattern_table_path=wm811k_stratified_table_path,
        summary=summary,
    )


def summarize_mvtec_object_selection(
    *,
    records: Sequence[Mapping[str, Any]],
    adapter_summary: Mapping[str, Any],
    pipeline_summary: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return object-level MVTec selection rows for paper case-study scoping."""
    cases_by_id = _cases_by_id(adapter_summary)
    sanity_by_id = _sanity_records_by_id(pipeline_summary or {})
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[_mvtec_object_name(record)].append(record)

    rows: list[dict[str, Any]] = []
    for object_name in sorted(grouped):
        object_records = grouped[object_name]
        row = _mvtec_object_row(
            object_name=object_name,
            records=object_records,
            cases_by_id=cases_by_id,
            sanity_by_id=sanity_by_id,
        )
        rows.append(row)

    if rows:
        selected = max(
            rows,
            key=lambda row: (
                _float_value(row["selection_score"]),
                _int_value(row["defect_case_count"]),
                str(row["object"]),
            ),
        )
        for row in rows:
            row["recommendation"] = (
                "selected_for_paper_visual_evidence_case"
                if row["object"] == selected["object"]
                else "candidate_not_selected"
            )
    return rows


def summarize_wm811k_traceability(
    *,
    records: Sequence[Mapping[str, Any]],
    adapter_summary: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Return WM811K pattern coverage and traceability rows."""
    cases_by_id = _cases_by_id(adapter_summary)
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    native_counts: Counter[str] = Counter()
    predicted_counts: Counter[str] = Counter()
    for record in records:
        native = _wm811k_native_pattern(record)
        predicted = _wm811k_predicted_pattern(record)
        if native:
            native_counts[native] += 1
        if predicted:
            predicted_counts[predicted] += 1
        grouped[native or predicted or _wm811k_observed_pattern(record) or "unknown"].append(record)

    rows: list[dict[str, Any]] = []
    observed_patterns = [
        *SUPPORTED_WM811K_PATTERNS,
        *sorted(pattern for pattern in grouped if pattern not in SUPPORTED_WM811K_PATTERNS),
    ]
    for pattern in observed_patterns:
        pattern_records = grouped.get(pattern, [])
        rows.append(
            _wm811k_pattern_row(
                pattern=pattern,
                records=pattern_records,
                native_count=native_counts.get(pattern, 0),
                predicted_count=predicted_counts.get(pattern, 0),
                cases_by_id=cases_by_id,
            )
        )
    return rows


def _evaluation_summary(
    *,
    config: PaperCaseStudyEvaluationConfig,
    summary_path: Path,
    mvtec_table_path: Path,
    wm811k_table_path: Path,
    wm811k_stratified_table_path: Path | None,
    mvtec_rows: list[dict[str, Any]],
    wm811k_rows: list[dict[str, Any]],
    wm811k_stratified_rows: list[dict[str, Any]],
    mvtec_adapter_summary: Mapping[str, Any],
    wm811k_adapter_summary: Mapping[str, Any],
    wm811k_stratified_adapter_summary: Mapping[str, Any],
) -> dict[str, Any]:
    selected_mvtec = next(
        (
            row
            for row in mvtec_rows
            if row.get("recommendation") == "selected_for_paper_visual_evidence_case"
        ),
        None,
    )
    wm811k_summary = _wm811k_layer_summary(
        rows=wm811k_rows,
        adapter_summary=wm811k_adapter_summary,
        claim_boundary=WM811K_CLAIM_BOUNDARY,
    )
    wm811k_stratified_summary = _wm811k_layer_summary(
        rows=wm811k_stratified_rows,
        adapter_summary=wm811k_stratified_adapter_summary,
        claim_boundary=WM811K_STRATIFIED_CLAIM_BOUNDARY,
    )
    return {
        "artifact_type": "paper_case_study_evaluation_hardening_v0",
        "artifact_scope": "paper_facing_summary_from_generated_outputs",
        "output": {
            "summary_path": str(summary_path),
            "mvtec_object_table": str(mvtec_table_path),
            "wm811k_pattern_table": str(wm811k_table_path),
            "wm811k_stratified_pattern_table": (
                str(wm811k_stratified_table_path)
                if wm811k_stratified_table_path is not None
                else None
            ),
        },
        "inputs": {
            "mvtec_records": str(config.mvtec_records_path),
            "mvtec_adapter_summary": str(config.mvtec_adapter_summary_path),
            "mvtec_pipeline_summary": (
                str(config.mvtec_pipeline_summary_path)
                if config.mvtec_pipeline_summary_path is not None
                else None
            ),
            "wm811k_records": str(config.wm811k_records_path),
            "wm811k_adapter_summary": str(config.wm811k_adapter_summary_path),
            "wm811k_stratified_records": (
                str(config.wm811k_stratified_records_path)
                if config.wm811k_stratified_records_path is not None
                else None
            ),
            "wm811k_stratified_adapter_summary": (
                str(config.wm811k_stratified_adapter_summary_path)
                if config.wm811k_stratified_adapter_summary_path is not None
                else None
            ),
        },
        "mvtec": {
            "claim_boundary": MVTEC_CLAIM_BOUNDARY,
            "adapter_case_count": mvtec_adapter_summary.get("case_count", 0),
            "object_count": len(mvtec_rows),
            "selected_object": selected_mvtec["object"] if selected_mvtec else None,
            "selected_object_summary": selected_mvtec,
            "selection_rule": (
                "Maximize transparent score over visual model separation, localization "
                "signal, KG entity coverage, and explainable path coverage."
            ),
        },
        "wm811k": wm811k_summary,
        "wm811k_stratified": wm811k_stratified_summary if wm811k_stratified_rows else None,
    }


def _mvtec_object_row(
    *,
    object_name: str,
    records: Sequence[Mapping[str, Any]],
    cases_by_id: Mapping[str, Mapping[str, Any]],
    sanity_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    defect_records = [record for record in records if _mvtec_label(record) != "good"]
    good_records = [record for record in records if _mvtec_label(record) == "good"]
    defect_anomalous_rate = _safe_div(
        sum(_mvtec_is_anomalous(record) is True for record in defect_records),
        len(defect_records),
    )
    good_normal_rate = _safe_div(
        sum(_mvtec_is_anomalous(record) is False for record in good_records),
        len(good_records),
    )
    visual_model_score = _mean_defined([defect_anomalous_rate, good_normal_rate])
    mask_ious = [
        value
        for record in defect_records
        if (value := _mvtec_mask_iou(record, sanity_by_id=sanity_by_id)) is not None
    ]
    defect_mask_areas = [
        value
        for record in defect_records
        if (value := _mvtec_mask_area(record, sanity_by_id=sanity_by_id)) is not None
    ]
    object_cases = [
        cases_by_id[str(record.get("case_id"))]
        for record in records
        if str(record.get("case_id")) in cases_by_id
    ]
    mean_linked = _mean([_number(case.get("linked_entity_count")) for case in object_cases])
    explainable_path_rate = _safe_div(
        sum(len(_list_value(case.get("top_k_paths"))) > 0 for case in object_cases),
        len(object_cases),
    )
    kg_score = _safe_div(min(mean_linked or 0.0, 4.0), 4.0)
    localization_score = _mean(mask_ious)
    if localization_score is None:
        localization_score = _safe_div(
            sum(area > 0 for area in defect_mask_areas),
            len(defect_mask_areas),
        )
    selection_score = (
        0.35 * (visual_model_score or 0.0)
        + 0.20 * (localization_score or 0.0)
        + 0.20 * (kg_score or 0.0)
        + 0.25 * (explainable_path_rate or 0.0)
    )
    return {
        "object": object_name,
        "record_count": len(records),
        "defect_case_count": len(defect_records),
        "good_case_count": len(good_records),
        "defect_anomalous_rate": _round(defect_anomalous_rate),
        "good_normal_rate": _round(good_normal_rate),
        "visual_model_score": _round(visual_model_score),
        "mean_mask_iou": _round(_mean(mask_ious)),
        "defect_nonzero_mask_rate": _round(
            _safe_div(sum(area > 0 for area in defect_mask_areas), len(defect_mask_areas))
        ),
        "mean_consistency_score": _round(
            _mean([_number(case.get("consistency_score")) for case in object_cases])
        ),
        "mean_linked_entity_count": _round(mean_linked),
        "kg_completeness_score": _round(kg_score),
        "explainable_path_rate": _round(explainable_path_rate),
        "unique_top_targets": ";".join(_unique_top_targets(object_cases)),
        "unique_source_count": len(_unique_sources(object_cases)),
        "selection_score": _round(selection_score),
        "recommendation": "",
        "claim_boundary": MVTEC_CLAIM_BOUNDARY,
    }


def _wm811k_pattern_row(
    *,
    pattern: str,
    records: Sequence[Mapping[str, Any]],
    native_count: int,
    predicted_count: int,
    cases_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    exact_correct = 0
    comparable = 0
    accuracy_scope = "not_available"
    for record in records:
        native = _wm811k_native_pattern(record)
        predicted = _wm811k_predicted_pattern(record)
        if native and predicted:
            comparable += 1
            exact_correct += int(native == predicted)
            accuracy_scope = "native_vs_predicted_wm811k_pattern"
    source_scope = _wm811k_record_source_scope(records)
    if source_scope == "native_label_stratified_sampling_not_classifier_performance":
        comparable = 0
        exact_correct = 0
        accuracy_scope = "not_applicable_native_label_stratified_sampling"
    pattern_cases = [
        cases_by_id[str(record.get("case_id"))]
        for record in records
        if str(record.get("case_id")) in cases_by_id
    ]
    return {
        "pattern": pattern,
        "record_count": len(records),
        "native_count": native_count,
        "predicted_count": predicted_count,
        "exact_correct_count": exact_correct,
        "exact_comparable_count": comparable,
        "exact_accuracy": _round(_safe_div(exact_correct, comparable)),
        "mean_classifier_confidence": _round(
            _mean([_wm811k_confidence(record) for record in records])
        ),
        "mean_consistency_score": _round(
            _mean([_number(case.get("consistency_score")) for case in pattern_cases])
        ),
        "mean_linked_entity_count": _round(
            _mean([_number(case.get("linked_entity_count")) for case in pattern_cases])
        ),
        "explainable_path_rate": _round(
            _safe_div(
                sum(len(_list_value(case.get("top_k_paths"))) > 0 for case in pattern_cases),
                len(pattern_cases),
            )
        ),
        "unique_top_targets": ";".join(_unique_top_targets(pattern_cases)),
        "unique_source_count": len(_unique_sources(pattern_cases)),
        "coverage_status": "observed" if records else "not_observed_in_input",
        "record_source_scope": source_scope,
        "accuracy_scope": accuracy_scope,
        "claim_boundary": (
            WM811K_STRATIFIED_CLAIM_BOUNDARY
            if source_scope == "native_label_stratified_sampling_not_classifier_performance"
            else WM811K_CLAIM_BOUNDARY
        ),
    }


def _wm811k_layer_summary(
    *,
    rows: Sequence[Mapping[str, Any]],
    adapter_summary: Mapping[str, Any],
    claim_boundary: str,
) -> dict[str, Any]:
    observed_patterns = [str(row["pattern"]) for row in rows if _int_value(row["record_count"]) > 0]
    comparable = sum(_int_value(row["exact_comparable_count"]) for row in rows)
    correct = sum(_int_value(row["exact_correct_count"]) for row in rows)
    record_count = sum(_int_value(row["record_count"]) for row in rows)
    accuracy_scopes = sorted(
        {
            str(row.get("accuracy_scope"))
            for row in rows
            if _int_value(row.get("record_count")) > 0 and row.get("accuracy_scope")
        }
    )
    return {
        "claim_boundary": claim_boundary,
        "adapter_case_count": adapter_summary.get("case_count", 0),
        "record_count": record_count,
        "observed_pattern_count": len(observed_patterns),
        "observed_patterns": observed_patterns,
        "supported_patterns": list(SUPPORTED_WM811K_PATTERNS),
        "supported_pattern_coverage_rate": _round(
            _safe_div(len(set(observed_patterns)), len(SUPPORTED_WM811K_PATTERNS))
        ),
        "exact_pattern_accuracy": _round(_safe_div(correct, comparable)),
        "exact_pattern_accuracy_scope": (
            "native_vs_predicted_wm811k_pattern" if comparable else "not_available"
        ),
        "accuracy_scopes": accuracy_scopes,
        "traceability_path_coverage_rate": _round(
            _safe_div(
                sum(
                    _int_value(row["record_count"]) * _float_value(row["explainable_path_rate"])
                    for row in rows
                ),
                record_count,
            )
        ),
    }


def _wm811k_stratified_build_summary(
    *,
    config: WM811KStratifiedBuildConfig,
    output_path: Path,
    summary_path: Path,
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    counts = Counter(_wm811k_native_pattern(record) or "unknown" for record in records)
    observed = [pattern for pattern in SUPPORTED_WM811K_PATTERNS if counts.get(pattern, 0) > 0]
    missing = [pattern for pattern in SUPPORTED_WM811K_PATTERNS if counts.get(pattern, 0) == 0]
    return {
        "artifact_type": "wm811k_native_label_stratified_records_v0",
        "artifact_scope": "pattern_stratified_case_study_input",
        "input": {"table": str(config.input_path)},
        "output": {
            "records": str(output_path),
            "summary": str(summary_path),
        },
        "record_count": len(records),
        "records_per_pattern": config.records_per_pattern,
        "seed": config.seed,
        "supported_patterns": list(SUPPORTED_WM811K_PATTERNS),
        "observed_patterns": observed,
        "missing_patterns": missing,
        "pattern_counts": dict(sorted(counts.items())),
        "coverage_rate": _round(_safe_div(len(observed), len(SUPPORTED_WM811K_PATTERNS))),
        "claim_boundary": (
            "Records are selected from native WM811K pattern labels to cover public "
            "pattern strata. They are valid for pattern coverage and KG traceability "
            "checks, not classifier-performance or verified process RCA claims."
        ),
    }


class _NativeLabelStratifiedWM811KClassifier:
    """Minimal classifier protocol adapter that echoes native labels for sampling."""

    def predict(
        self,
        wafer_map: Sequence[Sequence[Any]],
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> WM811KPrediction:
        del wafer_map
        pattern = (
            _canonical_wm811k_pattern((metadata or {}).get("native_failure_pattern")) or "unknown"
        )
        return {
            "pattern": pattern,
            "metadata": {
                "source_backend": NATIVE_LABEL_STRATIFIED_BACKEND,
                "task": "native_pattern_stratified_sampling",
                "produces_root_cause": False,
                "uses_native_pattern_reference": True,
                "claim_boundary": (
                    "Native label echo used only to build pattern-stratified "
                    "case-study records; not a classifier inference result."
                ),
            },
        }


def _native_label_stratified_record(record: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(record)
    native_pattern = _wm811k_native_pattern(record)
    normalized["failure_pattern"] = native_pattern
    normalized.pop("predicted_pattern", None)
    normalized["classification_confidence"] = None
    normalized["record_source_scope"] = (
        "native_label_stratified_sampling_not_classifier_performance"
    )
    classifier_value = normalized.get("classifier")
    classifier = dict(classifier_value) if isinstance(classifier_value, Mapping) else {}
    classifier.update(
        {
            "backend": NATIVE_LABEL_STRATIFIED_BACKEND,
            "task": "native_pattern_stratified_sampling",
            "produces_root_cause": False,
            "uses_native_pattern_reference": True,
            "claim_boundary": (
                "Native WM811K label used to build a pattern-stratified "
                "traceability sample; not classifier performance."
            ),
        }
    )
    normalized["classifier"] = classifier
    return normalized


def _cases_by_id(summary: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(case.get("case_id")): case
        for case in _list_value(summary.get("cases"))
        if isinstance(case, Mapping) and case.get("case_id")
    }


def _sanity_records_by_id(summary: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    sanity = summary.get("sanity")
    if not isinstance(sanity, Mapping):
        return {}
    return {
        str(record.get("case_id")): record
        for record in _list_value(sanity.get("records"))
        if isinstance(record, Mapping) and record.get("case_id")
    }


def _mvtec_object_name(record: Mapping[str, Any]) -> str:
    value = record.get("object")
    if value:
        return str(value)
    case_id = str(record.get("case_id", ""))
    parts = case_id.split("_")
    return parts[1] if len(parts) > 2 and parts[0] == "mvtec" else "unknown"


def _mvtec_label(record: Mapping[str, Any]) -> str:
    return str(record.get("defect_type") or record.get("source_label") or "").lower()


def _mvtec_is_anomalous(record: Mapping[str, Any]) -> bool | None:
    detector = record.get("detector") if isinstance(record.get("detector"), Mapping) else {}
    for value in (
        record.get("pred_label"),
        detector.get("pred_label") if isinstance(detector, Mapping) else None,
        detector.get("raw_pred_label") if isinstance(detector, Mapping) else None,
    ):
        parsed = _parse_anomaly_label(value)
        if parsed is not None:
            return parsed
    return None


def _parse_anomaly_label(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if not text or text == "none":
        return None
    if "abnormal" in text or "anomal" in text or text in {"true", "1", "defect"}:
        return True
    if "normal" in text or text in {"false", "0", "good"}:
        return False
    return None


def _mvtec_mask_iou(
    record: Mapping[str, Any],
    *,
    sanity_by_id: Mapping[str, Mapping[str, Any]],
) -> float | None:
    case_id = str(record.get("case_id"))
    for source in (sanity_by_id.get(case_id, {}), _mask_stats(record)):
        for key in ("mask_iou", "iou_with_gt", "iou"):
            value = _number(source.get(key))
            if value is not None:
                return value
    return None


def _mvtec_mask_area(
    record: Mapping[str, Any],
    *,
    sanity_by_id: Mapping[str, Mapping[str, Any]],
) -> float | None:
    case_id = str(record.get("case_id"))
    for source in (sanity_by_id.get(case_id, {}), _mask_stats(record)):
        value = _number(source.get("mask_area_ratio") or source.get("area_ratio"))
        if value is not None:
            return value
    return None


def _mask_stats(record: Mapping[str, Any]) -> Mapping[str, Any]:
    value = record.get("mask_stats")
    return value if isinstance(value, Mapping) else {}


def _canonical_wm811k_pattern(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    normalized = text.lower().replace("_", "").replace("-", "").replace(" ", "")
    aliases = {
        "center": "Center",
        "donut": "Donut",
        "edgeloc": "Edge-Loc",
        "edgering": "Edge-Ring",
        "loc": "Loc",
        "local": "Loc",
        "random": "Random",
        "scratch": "Scratch",
        "nearfull": "Near-full",
        "nearfulldense": "Near-full",
    }
    return aliases.get(normalized, text)


def _wm811k_native_pattern(record: Mapping[str, Any]) -> str:
    native = _canonical_wm811k_pattern(record.get("native_failure_pattern"))
    if native:
        return native
    if str(record.get("annotation_type") or "").strip().lower() == "native_ground_truth":
        return _canonical_wm811k_pattern(record.get("failure_pattern"))
    return ""


def _wm811k_predicted_pattern(record: Mapping[str, Any]) -> str:
    return _canonical_wm811k_pattern(record.get("predicted_pattern"))


def _wm811k_observed_pattern(record: Mapping[str, Any]) -> str:
    return (
        _wm811k_native_pattern(record)
        or _wm811k_predicted_pattern(record)
        or _canonical_wm811k_pattern(record.get("failure_pattern"))
    )


def _wm811k_confidence(record: Mapping[str, Any]) -> float | None:
    classifier = record.get("classifier")
    classifier_mapping = classifier if isinstance(classifier, Mapping) else {}
    confidence = _number(record.get("classification_confidence"))
    if confidence is not None:
        return confidence
    return _number(classifier_mapping.get("confidence"))


def _wm811k_record_source_scope(records: Sequence[Mapping[str, Any]]) -> str:
    if not records:
        return ""
    scopes = {str(record.get("record_source_scope") or "") for record in records}
    if scopes == {"native_label_stratified_sampling_not_classifier_performance"}:
        return "native_label_stratified_sampling_not_classifier_performance"
    classifiers: list[Mapping[str, Any]] = []
    for record in records:
        classifier = record.get("classifier")
        if isinstance(classifier, Mapping):
            classifiers.append(classifier)
    if classifiers and all(
        classifier.get("backend") == NATIVE_LABEL_STRATIFIED_BACKEND for classifier in classifiers
    ):
        return "native_label_stratified_sampling_not_classifier_performance"
    return "producer_classifier_or_mixed"


def _unique_top_targets(cases: Sequence[Mapping[str, Any]]) -> list[str]:
    targets: set[str] = set()
    for case in cases:
        candidate_targets = _list_value(case.get("candidate_plausible_explanation_targets"))
        if candidate_targets:
            first = candidate_targets[0]
            if isinstance(first, Mapping) and first.get("target_entity_id"):
                targets.add(str(first["target_entity_id"]))
    return sorted(targets)


def _unique_sources(cases: Sequence[Mapping[str, Any]]) -> set[str]:
    sources: set[str] = set()
    for case in cases:
        for edge in _list_value(case.get("source_edge_provenance")):
            if isinstance(edge, Mapping) and edge.get("source"):
                sources.add(str(edge["source"]))
    return sources


def _read_json(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_csv(path: Path, fieldnames: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _ensure_can_write(path: Path, *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"{path} already exists; pass --overwrite to replace it")


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _mean(values: Sequence[float | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    return sum(present) / len(present) if present else None


def _mean_defined(values: Sequence[float | None]) -> float | None:
    return _mean(values)


def _safe_div(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def _round(value: float | None) -> float | str:
    return round(value, 4) if value is not None else ""


def _float_value(value: Any) -> float:
    return _number(value) or 0.0


def _int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
