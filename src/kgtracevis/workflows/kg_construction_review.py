"""Reusable workflow for reviewing KG construction artifacts."""

from __future__ import annotations

import csv
import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from kgtracevis.kg.graph import REQUIRED_EDGE_COLUMNS, KnowledgeGraph
from kgtracevis.kg_construction.artifact_diff import (
    build_kg_construction_artifact_snapshot,
    build_kg_construction_diff,
    write_kg_construction_diff,
)
from kgtracevis.kg_construction.document_extraction import ALLOWED_DOCUMENT_IE_RELATIONS
from kgtracevis.kg_construction.export_kg_csv import EDGE_COLUMNS
from kgtracevis.kg_construction.models import (
    KGConstructionReviewDecision,
    kg_construction_artifact_paths,
    review_decision_for_edge,
    review_decision_for_item,
)
from kgtracevis.kg_construction.publish import (
    append_review_decision,
    build_publish_snapshot,
    load_review_decisions,
    write_publish_snapshot,
)

ReviewAction = Literal["accept", "reject"]

REVIEWED_CROSS_CHUNK_RCA_RELATION_WHITELIST = frozenset(
    {
        "AFFECTS",
        "CAUSES",
        "HAS_PLAUSIBLE_CAUSE",
        "INDICATES",
        "SUGGESTS_ROOT_CAUSE",
    }
)
REVIEWED_CROSS_CHUNK_RCA_FAMILY_WHITELIST = frozenset(
    {
        "AFFECTS",
        "CAUSES",
        "FAULT_SOURCE",
        "OBSERVATION",
    }
)
REVIEWED_CROSS_CHUNK_RCA_SCORE_CAP = 0.7
REVIEWED_CROSS_CHUNK_PROPAGATION_PRIORITY_CAP = 0.75
REVIEWED_CROSS_CHUNK_SOURCE_TRUST_CAP = 0.8


@dataclass(frozen=True)
class ReviewKGConstructionItemConfig:
    """Configuration for one construction review queue item decision."""

    output_dir: Path
    action: ReviewAction
    target_key: str
    item_type: str = "edge"
    reviewer: str | None = None
    note: str | None = None
    proposed_payload: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class ReviewKGConstructionItemResult:
    """Result of applying one construction review queue item decision."""

    run_id: str
    output_dir: Path
    decision: KGConstructionReviewDecision
    item: dict[str, Any]
    summary: dict[str, Any]
    manifest: dict[str, Any]
    review_decisions_path: Path
    publish_report_path: Path
    published_nodes_path: Path
    published_edges_path: Path
    diff_path: Path


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
    diff_path: Path


def review_kg_construction_edge_artifact(
    config: ReviewKGConstructionEdgeConfig,
) -> ReviewKGConstructionEdgeResult:
    """Apply an edge review decision to a construction build directory."""
    artifact_paths = kg_construction_artifact_paths(config.output_dir)
    before_snapshot = build_kg_construction_artifact_snapshot(config.output_dir)
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
    _refresh_decision_counts(summary, artifact_paths["review_decisions"])
    _refresh_manifest_decision_counts(manifest, summary)
    _write_json_object(artifact_paths["summary"], summary)
    _write_json_object(artifact_paths["manifest"], manifest)
    _refresh_publish_snapshot_artifacts(
        output_dir=config.output_dir,
        run_id=run_id,
    )
    diff_path = _refresh_review_diff_artifact(
        output_dir=config.output_dir,
        run_id=run_id,
        before_snapshot=before_snapshot,
        decision=decision,
        scope="review_edge_action",
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
        diff_path=diff_path,
    )


def review_kg_construction_item_artifact(
    config: ReviewKGConstructionItemConfig,
) -> ReviewKGConstructionItemResult:
    """Apply an accept/reject decision to any construction review queue item."""
    if config.item_type == "edge":
        edge_result = review_kg_construction_edge_artifact(
            ReviewKGConstructionEdgeConfig(
                output_dir=config.output_dir,
                action=config.action,
                target_key=config.target_key,
                reviewer=config.reviewer,
                note=config.note,
                proposed_payload=config.proposed_payload,
                metadata=config.metadata,
            )
        )
        return ReviewKGConstructionItemResult(
            run_id=edge_result.run_id,
            output_dir=edge_result.output_dir,
            decision=edge_result.decision,
            item={
                "target_key": edge_result.decision.target_key,
                "item_type": "edge",
                "review_status": edge_result.edge.get("review_status", ""),
                "candidate_payload": edge_result.edge,
            },
            summary=edge_result.summary,
            manifest=edge_result.manifest,
            review_decisions_path=edge_result.review_decisions_path,
            publish_report_path=edge_result.publish_report_path,
            published_nodes_path=edge_result.published_nodes_path,
            published_edges_path=edge_result.published_edges_path,
            diff_path=edge_result.diff_path,
        )

    artifact_paths = kg_construction_artifact_paths(config.output_dir)
    before_snapshot = build_kg_construction_artifact_snapshot(config.output_dir)
    if not config.target_key.strip():
        raise ValueError("review target_key cannot be empty")
    if not config.item_type.strip():
        raise ValueError("review item_type cannot be empty")

    queue_items = _load_json_list(
        artifact_paths["review_queue"],
        object_name="construction review queue",
    )
    is_cross_chunk_accept = (
        config.item_type.strip() == "cross_chunk_relation_candidate"
        and config.action == "accept"
    )
    updated_item = _review_queue_item(
        queue_items,
        target_key=config.target_key.strip(),
        item_type=config.item_type.strip(),
        action=config.action,
        proposed_payload={} if is_cross_chunk_accept else config.proposed_payload or {},
    )
    manifest = _load_json_object(artifact_paths["manifest"], object_name="construction manifest")
    summary = _load_json_object(artifact_paths["summary"], object_name="construction summary")
    run_id = _run_id_from_manifest(manifest)
    if is_cross_chunk_accept:
        edge_rows = _read_edge_rows(artifact_paths["edges"])
        staged_edge = _stage_cross_chunk_relation_candidate_edge(
            artifact_paths=artifact_paths,
            edge_rows=edge_rows,
            reviewed_item=updated_item,
            run_id=run_id,
        )
        _write_edge_rows(artifact_paths["edges"], edge_rows)
        updated_item.setdefault("candidate_payload", {})["staged_edge"] = staged_edge
        _refresh_review_summary(summary, edge_rows)
        _refresh_manifest_review_summary(manifest, summary)
    decision = review_decision_for_item(
        target_type=config.item_type.strip(),
        target_id=config.target_key.strip(),
        target_key=config.target_key.strip(),
        action=config.action,
        reviewer=config.reviewer,
        note=config.note,
        proposed_payload=config.proposed_payload or updated_item,
        metadata={
            "run_id": run_id,
            "item_type": config.item_type.strip(),
            "item": updated_item,
            **dict(config.metadata or {}),
        },
    )
    append_review_decision(artifact_paths["review_decisions"], decision)
    manifest.setdefault("review_decisions", []).append(decision.model_dump(mode="json"))
    _refresh_decision_counts(summary, artifact_paths["review_decisions"])
    _refresh_manifest_decision_counts(manifest, summary)
    _write_json_list(artifact_paths["review_queue"], queue_items)
    _write_json_object(artifact_paths["summary"], summary)
    _write_json_object(artifact_paths["manifest"], manifest)
    if is_cross_chunk_accept:
        _refresh_publish_snapshot_artifacts(
            output_dir=config.output_dir,
            run_id=run_id,
        )
    diff_path = _refresh_review_diff_artifact(
        output_dir=config.output_dir,
        run_id=run_id,
        before_snapshot=before_snapshot,
        decision=decision,
        scope="review_item_action",
    )
    return ReviewKGConstructionItemResult(
        run_id=run_id,
        output_dir=config.output_dir,
        decision=decision,
        item=updated_item,
        summary=summary,
        manifest=manifest,
        review_decisions_path=artifact_paths["review_decisions"],
        publish_report_path=artifact_paths["publish_report"],
        published_nodes_path=artifact_paths["published_nodes"],
        published_edges_path=artifact_paths["published_edges"],
        diff_path=diff_path,
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


def _stage_cross_chunk_relation_candidate_edge(
    *,
    artifact_paths: Mapping[str, Path],
    edge_rows: list[dict[str, str]],
    reviewed_item: dict[str, Any],
    run_id: str,
) -> dict[str, str]:
    candidate = reviewed_item.get("candidate_payload")
    if not isinstance(candidate, dict):
        raise ValueError("cross-chunk review item is missing candidate_payload")
    if str(candidate.get("validation_status") or "") != "review_required":
        raise ValueError("only review-required cross-chunk proposals can be accepted")
    head = str(candidate.get("head") or "").strip()
    relation = str(candidate.get("relation") or "").strip().upper()
    tail = str(candidate.get("tail") or "").strip()
    scenario = str(reviewed_item.get("scenario") or candidate.get("scenario") or "shared").strip()
    if relation not in ALLOWED_DOCUMENT_IE_RELATIONS:
        raise ValueError(
            f"cross-chunk accepted edge relation is not allowed for document IE: {relation}"
        )
    spans = candidate.get("supporting_spans")
    if not isinstance(spans, list) or len(spans) < 2:
        raise ValueError(
            "cross-chunk accepted edge requires at least two supporting spans"
        )
    target_key = _safe_edge_key(f"{head}|{relation}|{tail}|{scenario}")
    if any(_edge_key_from_row(row) == target_key for row in edge_rows):
        raise ValueError(f"cross-chunk accepted edge already exists: {target_key}")
    node_ids = _read_node_ids(artifact_paths["nodes"])
    missing = sorted({head, tail}.difference(node_ids))
    if missing:
        raise ValueError(
            "cross-chunk accepted edge endpoints must already exist in nodes.csv: "
            + ", ".join(missing)
        )
    confidence = max(0.0, min(_float_value(candidate.get("confidence")), 1.0))
    evidence = _cross_chunk_evidence(candidate, reviewed_item)
    if not evidence:
        raise ValueError("cross-chunk accepted edge requires supporting evidence")
    weight = 1.0 - confidence
    row = {key: "" for key in EDGE_COLUMNS}
    row.update(
        {
            "head": head,
            "relation": relation,
            "tail": tail,
            "scenario": scenario,
            "source": f"cross_chunk_proposal:{candidate.get('source_id') or 'document'}",
            "evidence": evidence,
            "confidence": f"{confidence:.6g}",
            "weight": f"{weight:.6g}",
            "review_status": "reviewed",
            "feedback_count": "1",
            "accepted_count": "1",
            "rejected_count": "0",
            "relation_family": str(candidate.get("relation_family") or relation),
            "propagation_enabled": "false",
            "propagation_direction": "forward",
            "propagation_priority": "0",
            "attenuation": "1",
            "edge_weight": f"{weight:.6g}",
            "root_candidate": "false",
            "observable": "false",
            "confidence_policy": "human_reviewed_cross_chunk_proposal",
            "source_trust": "0",
            "rca_score": "0",
            "rca_score_confidence": "0",
            "rca_score_priority": "0",
            "rca_score_attenuation": "0",
            "rca_score_source_trust": "0",
            "external_edge_id": str(candidate.get("proposal_id") or target_key),
            "kg_build_id": run_id,
        }
    )
    policy_updates, policy_audit = _reviewed_cross_chunk_rca_policy(
        candidate,
        relation=relation,
        relation_family=row["relation_family"],
        confidence=confidence,
    )
    row.update(policy_updates)
    candidate["review_acceptance_policy_result"] = policy_audit
    edge_rows.append(row)
    return dict(row)


def _reviewed_cross_chunk_rca_policy(
    candidate: Mapping[str, Any],
    *,
    relation: str,
    relation_family: str,
    confidence: float,
) -> tuple[dict[str, str], dict[str, Any]]:
    policy = candidate.get("review_acceptance_policy")
    policy_name = "review_acceptance_policy"
    if not isinstance(policy, Mapping):
        policy = candidate.get("rca_policy")
        policy_name = "rca_policy"
    if not isinstance(policy, Mapping):
        return {}, {"status": "default", "reason": "no explicit RCA staging policy"}

    normalized_relation = relation.strip().upper()
    normalized_family = relation_family.strip().upper()
    allowed = (
        normalized_relation in REVIEWED_CROSS_CHUNK_RCA_RELATION_WHITELIST
        and normalized_family in REVIEWED_CROSS_CHUNK_RCA_FAMILY_WHITELIST
    )
    if not allowed:
        return (
            {},
            {
                "status": "ignored",
                "policy_field": policy_name,
                "reason": "relation or relation family is not eligible for RCA staging",
                "relation": normalized_relation,
                "relation_family": normalized_family,
            },
        )

    updates: dict[str, str] = {}
    applied_fields: list[str] = []
    propagation_requested = _optional_bool(policy.get("propagation_enabled"))
    if propagation_requested is True:
        updates["propagation_enabled"] = "true"
        applied_fields.append("propagation_enabled")
        direction = str(policy.get("propagation_direction") or "").strip().lower()
        if direction in {"forward", "reverse", "bidirectional"}:
            updates["propagation_direction"] = direction
            applied_fields.append("propagation_direction")
        priority = _bounded_policy_float(
            policy.get("propagation_priority"),
            default=REVIEWED_CROSS_CHUNK_PROPAGATION_PRIORITY_CAP,
            upper=REVIEWED_CROSS_CHUNK_PROPAGATION_PRIORITY_CAP,
        )
        updates["propagation_priority"] = f"{priority:.6g}"
        applied_fields.append("propagation_priority")

    if "attenuation" in policy:
        attenuation = _bounded_policy_float(policy.get("attenuation"), default=1.0, upper=1.0)
        updates["attenuation"] = f"{attenuation:.6g}"
        applied_fields.append("attenuation")
    if "source_trust" in policy:
        source_trust = _bounded_policy_float(
            policy.get("source_trust"),
            default=0.0,
            upper=REVIEWED_CROSS_CHUNK_SOURCE_TRUST_CAP,
        )
        updates["source_trust"] = f"{source_trust:.6g}"
        updates["rca_score_source_trust"] = f"{source_trust:.6g}"
        applied_fields.extend(["source_trust", "rca_score_source_trust"])
    if "rca_score" in policy:
        score = _bounded_policy_float(
            policy.get("rca_score"),
            default=0.0,
            upper=REVIEWED_CROSS_CHUNK_RCA_SCORE_CAP,
        )
        score_confidence = _bounded_policy_float(
            policy.get("rca_score_confidence"),
            default=min(confidence, score),
            upper=REVIEWED_CROSS_CHUNK_RCA_SCORE_CAP,
        )
        updates["rca_score"] = f"{score:.6g}"
        updates["rca_score_confidence"] = f"{score_confidence:.6g}"
        applied_fields.extend(["rca_score", "rca_score_confidence"])

    if not applied_fields:
        return (
            {},
            {
                "status": "ignored",
                "policy_field": policy_name,
                "reason": "policy did not request supported RCA staging fields",
            },
        )
    updates["confidence_policy"] = "human_reviewed_cross_chunk_proposal_with_rca_policy"
    return (
        updates,
        {
            "status": "applied",
            "policy_field": policy_name,
            "applied_fields": applied_fields,
            "caps": {
                "rca_score": REVIEWED_CROSS_CHUNK_RCA_SCORE_CAP,
                "propagation_priority": REVIEWED_CROSS_CHUNK_PROPAGATION_PRIORITY_CAP,
                "source_trust": REVIEWED_CROSS_CHUNK_SOURCE_TRUST_CAP,
            },
        },
    )


def _read_node_ids(path: Path) -> set[str]:
    if not path.is_file():
        raise ValueError(f"construction build nodes not found: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if "id" not in (reader.fieldnames or []):
            raise ValueError(f"node CSV missing id column: {path}")
        return {str(row.get("id") or "").strip() for row in reader if row.get("id")}


def _cross_chunk_evidence(
    candidate: Mapping[str, Any],
    reviewed_item: Mapping[str, Any],
) -> str:
    spans = candidate.get("supporting_spans")
    parts: list[str] = []
    if isinstance(spans, list):
        for span in spans:
            if not isinstance(span, Mapping):
                continue
            text = str(span.get("text") or span.get("evidence") or "").strip()
            if text:
                parts.append(text)
    if not parts:
        item_evidence = str(reviewed_item.get("evidence") or "").strip()
        if item_evidence:
            parts.append(item_evidence)
    if not parts:
        why = str(candidate.get("why_hint_only") or "").strip()
        if why:
            parts.append(why)
    return "; ".join(dict.fromkeys(parts))


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


def _review_queue_item(
    items: list[Any],
    *,
    target_key: str,
    item_type: str,
    action: ReviewAction,
    proposed_payload: dict[str, Any],
) -> dict[str, Any]:
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("target_key") or "") != target_key:
            continue
        if str(item.get("item_type") or "") != item_type:
            continue
        status = "reviewed" if action == "accept" else "rejected"
        candidate = item.get("candidate_payload")
        if not isinstance(candidate, dict):
            candidate = {}
        candidate.update(proposed_payload)
        candidate["review_status"] = status
        candidate["review_action"] = action
        candidate["target_key"] = target_key
        candidate["item_type"] = item_type
        item["candidate_payload"] = candidate
        item["review_status"] = status
        item["feedback_count"] = _int_value(item.get("feedback_count")) + 1
        if action == "accept":
            item["accepted_count"] = _int_value(item.get("accepted_count")) + 1
        else:
            item["rejected_count"] = _int_value(item.get("rejected_count")) + 1
        return dict(item)
    raise ValueError(
        f"unknown construction review target_key for item_type={item_type}: {target_key}"
    )


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


def _refresh_decision_counts(summary: dict[str, Any], decisions_path: Path) -> None:
    decisions = load_review_decisions(decisions_path)
    summary["review_decision_counts"] = dict(
        sorted(Counter(decision.action for decision in decisions).items())
    )
    summary["review_decision_target_type_counts"] = dict(
        sorted(Counter(decision.target_type for decision in decisions).items())
    )


def _refresh_manifest_decision_counts(
    manifest: dict[str, Any],
    summary: dict[str, Any],
) -> None:
    manifest_summary = manifest.get("summary")
    if isinstance(manifest_summary, dict):
        manifest_summary["review_decision_counts"] = summary.get(
            "review_decision_counts",
            {},
        )
        manifest_summary["review_decision_target_type_counts"] = summary.get(
            "review_decision_target_type_counts",
            {},
        )


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


def _refresh_review_diff_artifact(
    *,
    output_dir: Path,
    run_id: str,
    before_snapshot: dict[str, Any],
    decision: KGConstructionReviewDecision,
    scope: str,
) -> Path:
    artifact_paths = kg_construction_artifact_paths(output_dir)
    after_snapshot = build_kg_construction_artifact_snapshot(output_dir)
    return write_kg_construction_diff(
        artifact_paths["kg_construction_diff"],
        build_kg_construction_diff(
            run_id=run_id,
            before=before_snapshot,
            after=after_snapshot,
            decision_provenance=(decision,),
            scope=scope,
        ),
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


def _optional_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes"}:
            return True
        if normalized in {"0", "false", "no"}:
            return False
    return None


def _bounded_policy_float(value: object, *, default: float, upper: float) -> float:
    if value is None:
        return default
    parsed = _float_value(value)
    return max(0.0, min(parsed, upper))
