"""Reusable workflow for reviewing KG construction artifacts."""

from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from kgtracevis.kg.graph import REQUIRED_EDGE_COLUMNS, KnowledgeGraph
from kgtracevis.kg_construction.export_kg_csv import EDGE_COLUMNS
from kgtracevis.kg_construction.models import (
    KGConstructionReviewDecision,
    kg_construction_artifact_paths,
    review_decision_for_edge,
)
from kgtracevis.kg_construction.publish import (
    append_review_decision,
    build_publish_snapshot,
    load_review_decisions,
    write_publish_snapshot,
)

ReviewAction = Literal["accept", "reject"]


@dataclass(frozen=True)
class ReviewKGConstructionEdgeConfig:
    """Configuration for one construction artifact edge review."""

    output_dir: Path
    action: ReviewAction
    target_key: str | None = None
    head: str | None = None
    relation: str | None = None
    tail: str | None = None
    scenario: str | None = None
    reviewer: str | None = None
    note: str | None = None
    proposed_payload: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class ReviewKGConstructionEdgeResult:
    """Result of applying one construction edge review decision."""

    run_id: str
    output_dir: Path
    decision: KGConstructionReviewDecision
    edge: dict[str, Any]
    summary: dict[str, Any]
    manifest: dict[str, Any]
    review_decisions_path: Path
    publish_report_path: Path
    published_nodes_path: Path
    published_edges_path: Path


def review_kg_construction_edge_artifact(
    config: ReviewKGConstructionEdgeConfig,
) -> ReviewKGConstructionEdgeResult:
    """Apply an edge review decision to a construction build directory."""
    artifact_paths = kg_construction_artifact_paths(config.output_dir)
    target_key = _edge_key_from_config(config)
    edge_rows = _read_edge_rows(artifact_paths["edges"])
    updated_edge = _review_edge_row(edge_rows, target_key=target_key, action=config.action)
    _write_edge_rows(artifact_paths["edges"], edge_rows)

    manifest = _load_json_object(artifact_paths["manifest"], object_name="construction manifest")
    summary = _load_json_object(artifact_paths["summary"], object_name="construction summary")
    run_id = _run_id_from_manifest(manifest)
    _refresh_review_summary(summary, edge_rows)
    _refresh_manifest_review_summary(manifest, summary)
    _refresh_review_queue_artifact(artifact_paths["review_queue"], updated_edge)
    decision = review_decision_for_edge(
        target_id=target_key,
        target_key=target_key,
        action=config.action,
        reviewer=config.reviewer,
        note=config.note,
        proposed_payload=config.proposed_payload or updated_edge,
        metadata={
            "run_id": run_id,
            "edge": updated_edge,
            **dict(config.metadata or {}),
        },
    )
    append_review_decision(artifact_paths["review_decisions"], decision)
    manifest.setdefault("review_decisions", []).append(decision.model_dump(mode="json"))
    _write_json_object(artifact_paths["summary"], summary)
    _write_json_object(artifact_paths["manifest"], manifest)
    _refresh_publish_snapshot_artifacts(
        output_dir=config.output_dir,
        run_id=run_id,
    )
    return ReviewKGConstructionEdgeResult(
        run_id=run_id,
        output_dir=config.output_dir,
        decision=decision,
        edge=updated_edge,
        summary=summary,
        manifest=manifest,
        review_decisions_path=artifact_paths["review_decisions"],
        publish_report_path=artifact_paths["publish_report"],
        published_nodes_path=artifact_paths["published_nodes"],
        published_edges_path=artifact_paths["published_edges"],
    )


def _edge_key_from_config(config: ReviewKGConstructionEdgeConfig) -> str:
    if config.target_key is not None:
        return _safe_edge_key(config.target_key)
    if not all((config.head, config.relation, config.tail, config.scenario)):
        raise ValueError("pass either target_key or head/relation/tail/scenario")
    return _safe_edge_key(
        f"{config.head}|{config.relation}|{config.tail}|{config.scenario}"
    )


def _read_edge_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise ValueError(f"construction build edges not found: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED_EDGE_COLUMNS.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"edge CSV missing required columns: {sorted(missing)}")
        return [{key: row.get(key, "") for key in EDGE_COLUMNS} for row in reader]


def _write_edge_rows(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=EDGE_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _review_edge_row(
    rows: list[dict[str, str]],
    *,
    target_key: str,
    action: ReviewAction,
) -> dict[str, Any]:
    for row in rows:
        if _edge_key_from_row(row) != target_key:
            continue
        row["feedback_count"] = str(_int_value(row.get("feedback_count")) + 1)
        if action == "accept":
            row["review_status"] = "reviewed"
            row["accepted_count"] = str(_int_value(row.get("accepted_count")) + 1)
        elif action == "reject":
            row["review_status"] = "rejected"
            row["rejected_count"] = str(_int_value(row.get("rejected_count")) + 1)
        return dict(row)
    raise ValueError(f"unknown construction edge target_key: {target_key}")


def _edge_key_from_row(row: dict[str, str]) -> str:
    return _safe_edge_key(
        "|".join(
            (
                row.get("head", ""),
                row.get("relation", ""),
                row.get("tail", ""),
                row.get("scenario", ""),
            )
        )
    )


def _safe_edge_key(value: str) -> str:
    parts = [part.strip() for part in value.split("|")]
    if len(parts) != 4 or any(not part for part in parts):
        raise ValueError("edge target_key must have form head|relation|tail|scenario")
    return "|".join(parts)


def _load_json_object(path: Path, *, object_name: str) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"{object_name} not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{object_name} must be a JSON object: {path}")
    return payload


def _load_json_list(path: Path, *, object_name: str) -> list[Any]:
    if not path.is_file():
        raise ValueError(f"{object_name} not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"{object_name} must be a JSON array: {path}")
    return payload


def _write_json_object(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _write_json_list(path: Path, payload: list[Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _refresh_review_queue_artifact(
    queue_path: Path,
    updated_edge: dict[str, Any],
) -> None:
    if not queue_path.is_file():
        return
    payload = _load_json_list(queue_path, object_name="construction review queue")
    target_key = _edge_key_from_row(
        {key: str(updated_edge.get(key, "")) for key in EDGE_COLUMNS}
    )
    updated = False
    for item in payload:
        if not isinstance(item, dict):
            continue
        candidate = item.get("candidate_payload")
        if not isinstance(candidate, dict):
            candidate = {}
        item_key = str(item.get("target_key") or candidate.get("edge_id") or "")
        if item_key != target_key:
            continue
        candidate.update(updated_edge)
        candidate["edge_id"] = target_key
        item["candidate_payload"] = candidate
        item["review_status"] = updated_edge.get("review_status", "")
        item["feedback_count"] = _int_value(updated_edge.get("feedback_count"))
        item["accepted_count"] = _int_value(updated_edge.get("accepted_count"))
        item["rejected_count"] = _int_value(updated_edge.get("rejected_count"))
        item["source"] = updated_edge.get("source", item.get("source", ""))
        item["evidence"] = updated_edge.get("evidence", item.get("evidence", ""))
        item["confidence"] = _float_value(updated_edge.get("confidence"))
        item["scenario"] = updated_edge.get("scenario", item.get("scenario", ""))
        item["relation_family"] = updated_edge.get(
            "relation_family",
            item.get("relation_family", ""),
        )
        updated = True
    if updated:
        _write_json_list(queue_path, payload)


def _refresh_review_summary(
    summary: dict[str, Any],
    edge_rows: list[dict[str, str]],
) -> None:
    review_counts = Counter(row.get("review_status", "") for row in edge_rows)
    review_counts.pop("", None)
    summary["review_status_counts"] = dict(sorted(review_counts.items()))


def _refresh_manifest_review_summary(
    manifest: dict[str, Any],
    summary: dict[str, Any],
) -> None:
    manifest_summary = manifest.get("summary")
    if isinstance(manifest_summary, dict):
        manifest_summary["review_status_counts"] = summary.get("review_status_counts", {})
    run = manifest.get("run")
    if isinstance(run, dict) and summary.get("review_status_counts"):
        statuses = set(_int_dict(summary.get("review_status_counts")))
        if statuses and "auto" not in statuses:
            run["status"] = "reviewed"


def _refresh_publish_snapshot_artifacts(
    *,
    output_dir: Path,
    run_id: str,
) -> None:
    artifact_paths = kg_construction_artifact_paths(output_dir)
    graph = KnowledgeGraph.from_csv(artifact_paths["nodes"], artifact_paths["edges"])
    decisions = load_review_decisions(artifact_paths["review_decisions"])
    snapshot = build_publish_snapshot(
        kg_build_id=run_id,
        nodes=tuple(graph.nodes.values()),
        edges=tuple(graph.edges),
        review_decisions=decisions,
    )
    write_publish_snapshot(
        snapshot,
        nodes_path=artifact_paths["published_nodes"],
        edges_path=artifact_paths["published_edges"],
        report_path=artifact_paths["publish_report"],
    )


def _run_id_from_manifest(manifest: dict[str, Any]) -> str:
    run = manifest.get("run")
    if isinstance(run, dict) and str(run.get("run_id") or ""):
        return str(run["run_id"])
    summary = manifest.get("summary")
    if isinstance(summary, dict) and str(summary.get("run_id") or ""):
        return str(summary["run_id"])
    raise ValueError("construction manifest missing run_id")


def _int_dict(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {str(key): _int_value(item) for key, item in value.items()}


def _int_value(value: object) -> int:
    if not isinstance(value, (str, bytes, bytearray, int, float)):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _float_value(value: object) -> float:
    if not isinstance(value, (str, bytes, bytearray, int, float)):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
