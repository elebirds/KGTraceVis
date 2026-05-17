"""Payload conversion helpers for Postgres-backed run storage."""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from kgtracevis.core.result import ranked_root_causes_from_paths
from kgtracevis.service.run_enrichment import (
    path_graph_from_paths,
    review_targets,
    unique_source_edges,
)

VALID_DATASETS = {"mvtec", "tep", "wafer"}
DEFAULT_CLAIM_BOUNDARY = (
    "candidate/plausible explanation only; not a verified root-cause label"
)


def detail_payload(
    *,
    run_row: Mapping[str, Any],
    case_rows: Sequence[Mapping[str, Any]],
    linked_rows: Sequence[Mapping[str, Any]],
    consistency_rows: Sequence[Mapping[str, Any]],
    correction_rows: Sequence[Mapping[str, Any]],
    path_rows: Sequence[Mapping[str, Any]],
    artifact_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Reconstruct a RunDetail-compatible payload from normalized runtime rows."""
    links_by_case = _rows_by_case(linked_rows, _link_payload)
    consistency_by_case = _consistency_by_case(consistency_rows)
    corrections_by_case = _rows_by_case(correction_rows, _correction_payload)
    paths_by_case = _rows_by_case(path_rows, _path_payload)

    cases: list[dict[str, Any]] = []
    aggregate_links: list[dict[str, Any]] = []
    aggregate_corrections: list[dict[str, Any]] = []
    aggregate_paths: list[dict[str, Any]] = []
    first_evidence: dict[str, Any] | None = None
    first_analysis: dict[str, Any] | None = None
    first_summary: dict[str, Any] | None = None
    summary_payload = dict_value(run_row.get("summary"))
    parameters = dict_value(run_row.get("parameters"))
    root_causes_by_case = dict_value(parameters.get("ranked_root_causes_by_case"))
    reasoning_metadata_by_case = dict_value(parameters.get("reasoning_metadata_by_case"))
    run_reasoning_metadata = _reasoning_metadata_value(
        parameters.get("run_reasoning_metadata")
    )
    analysis_reasoning_metadata = _reasoning_metadata_value(
        parameters.get("analysis_reasoning_metadata")
    )
    summary_pipeline = _reasoning_metadata_value(summary_payload.get("pipeline"))

    for row in case_rows:
        case_pk = str(row["case_pk"])
        evidence = dict_value(row.get("evidence_payload"))
        if not evidence:
            evidence = _evidence_from_case_row(row)
        case_id = str(evidence.get("case_id") or row.get("case_id"))
        links = links_by_case.get(case_pk, [])
        corrections = corrections_by_case.get(case_pk, [])
        paths = paths_by_case.get(case_pk, [])
        ranked_root_causes = list_of_dicts(root_causes_by_case.get(case_id))
        if not ranked_root_causes:
            ranked_root_causes = _ranked_root_causes_from_paths(case_id, paths)
        consistency = consistency_by_case.get(case_pk, {})
        source_edges = unique_source_edges(paths)
        case_reasoning_metadata = _reasoning_metadata_value(
            reasoning_metadata_by_case.get(case_id)
        ) or dict(summary_pipeline) or dict(analysis_reasoning_metadata)
        analysis = {
            "case_id": case_id,
            "linked_entities": links,
            "consistency_score": consistency.get("consistency_score"),
            "inconsistent_fields": consistency.get("inconsistent_fields", []),
            "correction_candidates": corrections,
            "top_k_paths": paths,
            "ranked_root_causes": ranked_root_causes,
            "reasoning_metadata": case_reasoning_metadata,
            "human_feedback": evidence.get("human_feedback"),
        }
        cases.append(
            {
                "case_id": case_id,
                "dataset": evidence.get("dataset") or row.get("dataset"),
                "generated_evidence": evidence,
                "generated_evidence_path": row.get("generated_evidence_path"),
                "linked_entities": links,
                "consistency_score": analysis["consistency_score"],
                "inconsistent_fields": analysis["inconsistent_fields"],
                "correction_candidates": corrections,
                "top_k_paths": paths,
                "ranked_root_causes": ranked_root_causes,
                "reasoning_metadata": case_reasoning_metadata,
                "source_edge_provenance": source_edges,
                "path_graph": path_graph_from_paths(paths),
                "review_targets": review_targets(
                    linked_entities=links,
                    correction_candidates=corrections,
                    top_k_paths=paths,
                    ranked_root_causes=ranked_root_causes,
                    source_edges=source_edges,
                ),
            }
        )
        aggregate_links.extend(links)
        aggregate_corrections.extend(corrections)
        aggregate_paths.extend(paths)
        if first_evidence is None:
            first_evidence = evidence
            first_analysis = analysis
            first_summary = _compact_evidence_summary(evidence)

    source_edges = unique_source_edges(aggregate_paths)
    artifacts, visual_evidence = _artifacts_payload(artifact_rows)
    evidence_with_analysis = None
    if first_evidence is not None and first_analysis is not None:
        evidence_with_analysis = dict(first_evidence)
        evidence_with_analysis["kg_analysis"] = {
            "linked_entities": first_analysis["linked_entities"],
            "consistency_score": first_analysis["consistency_score"],
            "inconsistent_fields": first_analysis["inconsistent_fields"],
            "correction_candidates": first_analysis["correction_candidates"],
            "top_k_paths": first_analysis["top_k_paths"],
            "ranked_root_causes": first_analysis["ranked_root_causes"],
            "reasoning_metadata": first_analysis.get("reasoning_metadata") or {},
        }

    aggregate_root_causes = [
        root_cause
        for case in cases
        for root_cause in list_of_dicts(case.get("ranked_root_causes"))
    ]
    if not aggregate_root_causes:
        aggregate_root_causes = _ranked_root_causes_from_paths(
            str(first_evidence.get("case_id") if first_evidence else "aggregate"),
            aggregate_paths,
        )

    summary = dict(summary_payload) if summary_payload else None
    if summary is None and run_reasoning_metadata:
        summary = {"pipeline": dict(run_reasoning_metadata)}
    elif summary is not None and "pipeline" not in summary and run_reasoning_metadata:
        summary["pipeline"] = dict(run_reasoning_metadata)

    analysis_payload = dict(first_analysis) if first_analysis is not None else None
    if analysis_payload is not None and not analysis_payload.get("reasoning_metadata"):
        analysis_payload["reasoning_metadata"] = (
            dict(run_reasoning_metadata)
            or dict(summary_pipeline)
            or dict(analysis_reasoning_metadata)
        )

    return {
        "run": run_summary_payload(run_row),
        "workflow_steps": list_value(parameters.get("workflow_steps")),
        "claim_boundary": run_row.get("claim_boundary") or DEFAULT_CLAIM_BOUNDARY,
        "evidence": first_evidence,
        "evidence_summary": first_summary,
        "evidence_with_analysis": evidence_with_analysis,
        "analysis": analysis_payload,
        "summary": summary,
        "cases": cases,
        "linked_entities": aggregate_links,
        "correction_candidates": aggregate_corrections,
        "top_k_paths": aggregate_paths,
        "ranked_root_causes": aggregate_root_causes,
        "reasoning_metadata": dict(run_reasoning_metadata)
        or dict(summary_pipeline)
        or dict(analysis_reasoning_metadata),
        "path_graph": path_graph_from_paths(aggregate_paths),
        "source_edge_provenance": source_edges,
        "review_targets": review_targets(
            linked_entities=aggregate_links,
            correction_candidates=aggregate_corrections,
            top_k_paths=aggregate_paths,
            ranked_root_causes=aggregate_root_causes,
            source_edges=source_edges,
        ),
        "artifacts": artifacts,
        "visual_evidence": visual_evidence,
    }


def run_summary_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    """Convert one analysis_runs row to a RunSummary-compatible payload."""
    created_at = row["started_at"]
    created_at_text = (
        created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at)
    )
    return {
        "run_id": str(row["run_id"]),
        "created_at": created_at_text,
        "mode": row["mode"],
        "source_filename": row["source_filename"],
        "top_k": row["top_k"],
        "run_dir": row.get("run_dir") or "",
        "status": row.get("status") or "completed",
        "dataset": row.get("dataset"),
        "case_count": int(row.get("case_count") or 0),
        "evidence_count": int(row.get("evidence_count") or 0),
        "label": row.get("label") or "Analysis run",
        "model_preset": row.get("model_preset"),
        "model_backend": row.get("model_backend"),
    }


def _ranked_root_causes_from_paths(
    case_id: str,
    paths: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        item.model_dump(mode="json")
        for item in ranked_root_causes_from_paths(case_id, paths)
    ]


def case_entries(detail: Any) -> list[dict[str, Any]]:
    """Return normalized case entries extracted from a RunDetail."""
    entries: list[dict[str, Any]] = []
    if detail.cases:
        for case in detail.cases:
            evidence = _case_evidence_payload(case)
            if evidence is None:
                continue
            entries.append(
                {
                    "case_id": str(evidence.get("case_id") or case.get("case_id") or "unknown"),
                    "dataset": valid_dataset(evidence.get("dataset") or case.get("dataset")),
                    "evidence": evidence,
                    "evidence_path": case.get("generated_evidence_path")
                    or case.get("evidence_path"),
                    "adapter_name": case.get("adapter") or case.get("adapter_name"),
                    "linked_entities": list_of_dicts(case.get("linked_entities")),
                    "consistency_score": case.get("consistency_score"),
                    "inconsistent_fields": list_value(case.get("inconsistent_fields")),
                    "checks": list_value(case.get("checks")),
                    "correction_candidates": list_of_dicts(case.get("correction_candidates")),
                    "top_k_paths": list_of_dicts(case.get("top_k_paths")),
                    "ranked_root_causes": list_of_dicts(case.get("ranked_root_causes")),
                    "reasoning_metadata": _reasoning_metadata_value(
                        case.get("reasoning_metadata")
                    ),
                }
            )
    if not entries and detail.evidence:
        evidence = dict(detail.evidence)
        analysis = dict_value(detail.analysis)
        entries.append(
            {
                "case_id": str(evidence.get("case_id") or "unknown"),
                "dataset": valid_dataset(evidence.get("dataset")),
                "evidence": evidence,
                "evidence_path": detail.artifacts.get("input_path"),
                "adapter_name": evidence.get("source"),
                "linked_entities": list_of_dicts(analysis.get("linked_entities")),
                "consistency_score": analysis.get("consistency_score"),
                "inconsistent_fields": list_value(analysis.get("inconsistent_fields")),
                "checks": list_value(analysis.get("checks")),
                "correction_candidates": list_of_dicts(analysis.get("correction_candidates")),
                "top_k_paths": list_of_dicts(analysis.get("top_k_paths")),
                "ranked_root_causes": list_of_dicts(analysis.get("ranked_root_causes")),
                "reasoning_metadata": _reasoning_metadata_value(
                    analysis.get("reasoning_metadata")
                ),
            }
        )
    return entries


def run_dataset(detail: Any, entries: Sequence[Mapping[str, Any]]) -> str:
    """Resolve the dataset to store for an analysis run."""
    if detail.run.dataset in VALID_DATASETS:
        return str(detail.run.dataset)
    for entry in entries:
        dataset = entry.get("dataset")
        if dataset in VALID_DATASETS:
            return str(dataset)
    return "mvtec"


def parse_run_uuid(run_id: str) -> uuid.UUID:
    """Parse a public run ID as a UUID."""
    try:
        return uuid.UUID(str(run_id))
    except ValueError as exc:
        raise ValueError(f"run_id must be a UUID: {run_id}") from exc


def valid_dataset(value: object) -> str:
    """Return a supported dataset name, defaulting to mvtec for legacy rows."""
    dataset = str(value or "").lower()
    if dataset in VALID_DATASETS:
        return dataset
    return "mvtec"


def feedback_context(
    connection: Any,
    run_uuid: uuid.UUID | None,
    case_id: str | None,
) -> dict[str, Any]:
    """Resolve dataset/case context for a feedback record."""
    if run_uuid is not None:
        if case_id:
            row = connection.execute(
                """
                SELECT c.dataset, c.id AS case_pk
                FROM run_evidence_cases rc
                JOIN evidence_cases c ON c.id = rc.case_pk
                WHERE rc.run_id = %s
                  AND c.case_id = %s
                LIMIT 1
                """,
                (run_uuid, case_id),
            ).fetchone()
            if row is not None:
                return {"dataset": row["dataset"], "case_pk": row["case_pk"]}
        row = connection.execute(
            "SELECT dataset, case_pk FROM analysis_runs WHERE run_id = %s",
            (run_uuid,),
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown run session: {run_uuid}")
        return {"dataset": row["dataset"], "case_pk": row.get("case_pk")}
    if case_id:
        row = connection.execute(
            """
            SELECT id AS case_pk, dataset
            FROM evidence_cases
            WHERE case_id = %s
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (case_id,),
        ).fetchone()
        if row is not None:
            return {"dataset": row["dataset"], "case_pk": row["case_pk"]}
    return {"dataset": "mvtec", "case_pk": None}


class FeedbackRecordAdapter:
    """Adapter for JSON-compatible feedback payloads used in unit tests."""

    def __init__(self, record: Mapping[str, Any]) -> None:
        self._record = dict(record)
        self.run_id = self._record.get("run_id")
        self.case_id = self._record.get("case_id")
        self.target_type = str(self._record.get("target_type") or "case")
        self.target_id = self._record.get("target_id")
        self.reviewer = self._record.get("reviewer")
        self.metadata = dict_value(self._record.get("metadata"))

    def review_action(self) -> str:
        """Return the normalized feedback action."""
        return str(
            self._record.get("action")
            or self._record.get("decision")
            or self._record.get("feedback")
            or "uncertain"
        )

    def review_note(self) -> str | None:
        """Return the submitted feedback note/comment."""
        note = self._record.get("note")
        if note is not None:
            return str(note)
        comment = self._record.get("comment")
        return str(comment) if comment is not None else None

    def model_dump(self, *, mode: str = "json") -> dict[str, Any]:
        """Return the original JSON-compatible record."""
        return dict(self._record)


def _reasoning_metadata_value(value: Any) -> dict[str, Any]:
    """Return a JSON-friendly reasoning metadata payload."""
    return dict_value(value)


def feedback_target_type(value: str) -> str:
    """Map API feedback target names to Postgres enum names."""
    return {
        "path": "ranked_path",
        "edge": "kg_edge",
        "correction": "correction_candidate",
        "link": "entity_link",
        "entity_link": "entity_link",
        "root_cause_candidate": "root_cause_candidate",
        "case": "case",
    }.get(value, value)


def feedback_value(value: str) -> str:
    """Map API feedback actions to Postgres enum values."""
    return {"needs_review": "uncertain"}.get(value, value)


def dict_value(value: Any) -> dict[str, Any]:
    """Return a dict for mapping values and an empty dict otherwise."""
    return dict(value) if isinstance(value, Mapping) else {}


def list_value(value: Any) -> list[Any]:
    """Return a list for non-string sequence values and an empty list otherwise."""
    return list(value) if isinstance(value, Sequence) and not isinstance(value, str) else []


def list_of_dicts(value: Any) -> list[dict[str, Any]]:
    """Return mapping items from a list-like value."""
    return [dict(item) for item in list_value(value) if isinstance(item, Mapping)]


def float_value(value: Any) -> float:
    """Return a non-null float for Postgres numeric fields."""
    return float(value) if value is not None else 0.0


def nullable_float(value: Any) -> float | None:
    """Return a nullable float for optional Postgres numeric fields."""
    return float(value) if value is not None else None


def optional_text(value: Any) -> str | None:
    """Return a string or None for optional text columns."""
    return None if value is None else str(value)


def _rows_by_case(
    rows: Sequence[Mapping[str, Any]],
    transform: Any,
) -> dict[str, list[dict[str, Any]]]:
    by_case: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = str(row.get("case_pk"))
        by_case.setdefault(key, []).append(transform(row))
    return by_case


def _consistency_by_case(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    by_case: dict[str, dict[str, Any]] = {}
    for row in rows:
        by_case[str(row.get("case_pk"))] = {
            "consistency_score": row.get("consistency_score"),
            "inconsistent_fields": list(row.get("inconsistent_fields") or []),
            "checks": list_value(row.get("checks")),
        }
    return by_case


def _link_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "link_id": row.get("link_id"),
        "field": row.get("field"),
        "mention": row.get("mention"),
        "selected_entity_id": row.get("selected_entity_id"),
        "selected_entity_scenario": row.get("selected_entity_scenario"),
        "score": row.get("score"),
        "match_type": row.get("match_type"),
        "ambiguous": row.get("ambiguous"),
        "candidates": list_value(row.get("candidates")),
    }


def _correction_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict_value(row.get("payload"))
    if payload:
        return payload
    return {
        "candidate_id": row.get("candidate_id"),
        "field": row.get("field"),
        "original_value": row.get("original_value"),
        "suggested_value": row.get("suggested_value"),
        "suggested_entity_id": row.get("suggested_entity_id"),
        "score": row.get("score"),
        "reason": row.get("reason"),
        "source_edges": list_value(row.get("source_edges")),
    }


def _path_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict_value(row.get("payload"))
    if payload:
        return payload
    return {
        "path_id": row.get("path_id"),
        "rank": row.get("rank"),
        "source_entity_id": row.get("source_entity_id"),
        "target_entity_id": row.get("target_entity_id"),
        "nodes": list(row.get("node_ids") or []),
        "relations": list(row.get("relation_ids") or []),
        "score": row.get("score"),
        "confidence": row.get("confidence"),
        "evidence_match": row.get("evidence_match"),
        "supporting_evidence": list_value(row.get("supporting_evidence")),
        "source_edges": [],
    }


def _artifacts_payload(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    artifacts: dict[str, str] = {}
    visual_evidence: list[dict[str, Any]] = []
    for row in rows:
        metadata = dict_value(row.get("metadata"))
        key = metadata.get("key")
        if key:
            artifacts[str(key)] = str(row.get("uri"))
        item = metadata.get("visual_evidence")
        if isinstance(item, Mapping):
            visual_evidence.append(dict(item))
    return artifacts, visual_evidence


def _case_evidence_payload(case: Mapping[str, Any]) -> dict[str, Any] | None:
    for key in ("evidence", "generated_evidence"):
        value = case.get(key)
        if isinstance(value, Mapping):
            payload = dict(value)
            payload.setdefault("case_id", case.get("case_id", "unknown"))
            payload.setdefault("dataset", valid_dataset(case.get("dataset")))
            payload.setdefault("raw_evidence", {})
            payload.setdefault("normalized_evidence", {})
            payload.setdefault("human_feedback", {})
            return payload
    if case.get("case_id") and case.get("dataset"):
        return {
            "case_id": case["case_id"],
            "dataset": valid_dataset(case["dataset"]),
            "source": case.get("source", "upload"),
            "object": case.get("object", "unknown"),
            "anomaly_type": case.get("anomaly_type", "unknown"),
            "location": case.get("location"),
            "morphology": case.get("morphology"),
            "severity": case.get("severity"),
            "confidence": case.get("confidence"),
            "timestamp": case.get("timestamp"),
            "raw_evidence": {},
            "normalized_evidence": {},
            "human_feedback": {},
        }
    return None


def _evidence_from_case_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "case_id": row.get("case_id"),
        "dataset": row.get("dataset"),
        "raw_evidence": dict_value(row.get("raw_evidence")),
        "normalized_evidence": dict_value(row.get("normalized_evidence")),
        "human_feedback": dict_value(row.get("human_feedback")),
    }


def _compact_evidence_summary(evidence: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "case_id": evidence.get("case_id"),
        "dataset": evidence.get("dataset"),
        "source": evidence.get("source"),
        "object": evidence.get("object"),
        "anomaly_type": evidence.get("anomaly_type"),
        "location": evidence.get("location"),
        "morphology": evidence.get("morphology"),
        "severity": evidence.get("severity"),
        "confidence": evidence.get("confidence"),
        "observation_count": len(list_value(evidence.get("observations"))),
    }
