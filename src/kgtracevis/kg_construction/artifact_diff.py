"""Artifact-level diffs for source-to-KG construction builds."""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from kgtracevis.kg_construction.models import (
    KGConstructionReviewDecision,
    kg_construction_artifact_paths,
)

KG_CONSTRUCTION_DIFF_ARTIFACT_TYPE = "kg_construction_diff_v1"

COUNT_SUMMARY_KEYS: tuple[str, ...] = (
    "source_count",
    "draft_entity_count",
    "draft_relation_count",
    "node_count",
    "edge_count",
    "node_labels",
    "edge_relations",
    "scenarios",
    "review_status_counts",
    "review_decision_counts",
    "review_decision_target_type_counts",
)


def build_kg_construction_artifact_snapshot(output_dir: str | Path) -> dict[str, Any]:
    """Read diffable construction artifacts from one build directory."""
    artifact_paths = kg_construction_artifact_paths(output_dir)
    return {
        "nodes": _csv_record_snapshot(artifact_paths["nodes"], key_fields=("id",)),
        "edges": _csv_record_snapshot(
            artifact_paths["edges"],
            key_fields=("head", "relation", "tail", "scenario"),
        ),
        "review_queue": _json_list_snapshot(
            artifact_paths["review_queue"],
            key_fields=("item_type", "target_key"),
        ),
        "alignment_manifest": _json_object_snapshot(
            artifact_paths["alignment_manifest"],
        ),
        "profile_manifest": _json_object_snapshot(
            artifact_paths["profile_manifest"],
        ),
        "semantic_layer_manifest": _json_object_snapshot(
            artifact_paths["semantic_layer_manifest"],
        ),
        "rca_view_manifest": _json_object_snapshot(
            artifact_paths["rca_view_manifest"],
        ),
        "publish_report": _json_object_snapshot(
            artifact_paths["publish_report"],
            ignored_keys=("created_at",),
        ),
        "summary_counts": _summary_count_snapshot(
            artifact_paths["summary"],
        ),
    }


def build_kg_construction_diff(
    *,
    run_id: str,
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    decision_provenance: Sequence[KGConstructionReviewDecision] = (),
    scope: str = "review_replay",
) -> dict[str, Any]:
    """Return a structured before/after diff for construction artifacts."""
    artifact_diffs = {
        "nodes": _diff_records(before.get("nodes"), after.get("nodes")),
        "edges": _diff_records(before.get("edges"), after.get("edges")),
        "review_queue": _diff_records(
            before.get("review_queue"),
            after.get("review_queue"),
        ),
        "alignment_manifest": _diff_objects(
            before.get("alignment_manifest"),
            after.get("alignment_manifest"),
        ),
        "profile_manifest": _diff_objects(
            before.get("profile_manifest"),
            after.get("profile_manifest"),
        ),
        "semantic_layer_manifest": _diff_objects(
            before.get("semantic_layer_manifest"),
            after.get("semantic_layer_manifest"),
        ),
        "rca_view_manifest": _diff_objects(
            before.get("rca_view_manifest"),
            after.get("rca_view_manifest"),
        ),
        "publish_report": _diff_objects(
            before.get("publish_report"),
            after.get("publish_report"),
        ),
        "summary_counts": _diff_objects(
            before.get("summary_counts"),
            after.get("summary_counts"),
        ),
    }
    summary = _diff_summary(artifact_diffs)
    return {
        "artifact_type": KG_CONSTRUCTION_DIFF_ARTIFACT_TYPE,
        "run_id": run_id,
        "scope": scope,
        "has_changes": summary["has_changes"],
        "summary": summary,
        "decision_provenance": [
            decision.model_dump(mode="json") for decision in decision_provenance
        ],
        "artifacts": artifact_diffs,
    }


def build_noop_kg_construction_diff(
    *,
    run_id: str,
    snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a no-op construction diff for a fresh build."""
    return build_kg_construction_diff(
        run_id=run_id,
        before=snapshot,
        after=snapshot,
        decision_provenance=(),
        scope="fresh_build",
    )


def write_kg_construction_diff(path: str | Path, diff: Mapping[str, Any]) -> Path:
    """Write a construction diff JSON artifact and return its path."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(diff, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return output_path


def _csv_record_snapshot(path: Path, *, key_fields: tuple[str, ...]) -> dict[str, Any]:
    if not path.is_file():
        return _missing_record_snapshot(path)
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = [
            {str(key): str(value) for key, value in row.items()}
            for row in reader
        ]
    records = {_record_key(row, key_fields): row for row in rows}
    return {
        "kind": "records",
        "path": str(path),
        "exists": True,
        "key_fields": list(key_fields),
        "count": len(records),
        "records": dict(sorted(records.items())),
    }


def _json_list_snapshot(path: Path, *, key_fields: tuple[str, ...]) -> dict[str, Any]:
    if not path.is_file():
        return _missing_record_snapshot(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"diff artifact must be a JSON array: {path}")
    rows = [row for row in payload if isinstance(row, dict)]
    records = {_record_key(row, key_fields): _jsonable(row) for row in rows}
    return {
        "kind": "records",
        "path": str(path),
        "exists": True,
        "key_fields": list(key_fields),
        "count": len(records),
        "records": dict(sorted(records.items())),
    }


def _json_object_snapshot(
    path: Path,
    *,
    ignored_keys: tuple[str, ...] = (),
) -> dict[str, Any]:
    if not path.is_file():
        return _missing_object_snapshot(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"diff artifact must be a JSON object: {path}")
    normalized = _strip_ignored_keys(_jsonable(payload), set(ignored_keys))
    return {
        "kind": "object",
        "path": str(path),
        "exists": True,
        "payload": normalized,
    }


def _summary_count_snapshot(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return _missing_object_snapshot(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"diff summary artifact must be a JSON object: {path}")
    counts = {
        key: _jsonable(payload[key])
        for key in COUNT_SUMMARY_KEYS
        if key in payload
    }
    return {
        "kind": "object",
        "path": str(path),
        "exists": True,
        "payload": counts,
    }


def _missing_record_snapshot(path: Path) -> dict[str, Any]:
    return {
        "kind": "records",
        "path": str(path),
        "exists": False,
        "key_fields": [],
        "count": 0,
        "records": {},
    }


def _missing_object_snapshot(path: Path) -> dict[str, Any]:
    return {
        "kind": "object",
        "path": str(path),
        "exists": False,
        "payload": {},
    }


def _diff_records(before: Any, after: Any) -> dict[str, Any]:
    before_snapshot = before if isinstance(before, dict) else _missing_record_snapshot(Path(""))
    after_snapshot = after if isinstance(after, dict) else _missing_record_snapshot(Path(""))
    before_records = _dict_value(before_snapshot.get("records"))
    after_records = _dict_value(after_snapshot.get("records"))
    before_keys = set(before_records)
    after_keys = set(after_records)
    added_keys = sorted(after_keys - before_keys)
    removed_keys = sorted(before_keys - after_keys)
    common_keys = sorted(before_keys & after_keys)
    changed = [
        {
            "key": key,
            "before": before_records[key],
            "after": after_records[key],
        }
        for key in common_keys
        if before_records[key] != after_records[key]
    ]
    return {
        "kind": "records",
        "before_count": int(before_snapshot.get("count") or 0),
        "after_count": int(after_snapshot.get("count") or 0),
        "added_count": len(added_keys),
        "removed_count": len(removed_keys),
        "changed_count": len(changed),
        "added": [{"key": key, "after": after_records[key]} for key in added_keys],
        "removed": [
            {"key": key, "before": before_records[key]} for key in removed_keys
        ],
        "changed": changed,
    }


def _diff_objects(before: Any, after: Any) -> dict[str, Any]:
    before_snapshot = before if isinstance(before, dict) else _missing_object_snapshot(Path(""))
    after_snapshot = after if isinstance(after, dict) else _missing_object_snapshot(Path(""))
    before_payload = _dict_value(before_snapshot.get("payload"))
    after_payload = _dict_value(after_snapshot.get("payload"))
    changed = before_payload != after_payload
    before_exists = bool(before_snapshot.get("exists"))
    after_exists = bool(after_snapshot.get("exists"))
    return {
        "kind": "object",
        "before_count": int(before_exists),
        "after_count": int(after_exists),
        "added_count": int(not before_exists and after_exists),
        "removed_count": int(before_exists and not after_exists),
        "changed_count": int(changed),
        "changed": changed,
        "before": before_payload if changed else {},
        "after": after_payload if changed else {},
    }


def _diff_summary(artifact_diffs: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    artifact_change_counts = {
        key: {
            "added": int(diff.get("added_count") or 0),
            "removed": int(diff.get("removed_count") or 0),
            "changed": int(diff.get("changed_count") or 0),
        }
        for key, diff in artifact_diffs.items()
    }
    total_added = sum(item["added"] for item in artifact_change_counts.values())
    total_removed = sum(item["removed"] for item in artifact_change_counts.values())
    total_changed = sum(item["changed"] for item in artifact_change_counts.values())
    changed_artifacts = [
        key
        for key, counts in artifact_change_counts.items()
        if counts["added"] or counts["removed"] or counts["changed"]
    ]
    return {
        "has_changes": bool(total_added or total_removed or total_changed),
        "total_added": total_added,
        "total_removed": total_removed,
        "total_changed": total_changed,
        "changed_artifacts": changed_artifacts,
        "artifact_change_counts": artifact_change_counts,
    }


def _record_key(row: Mapping[str, Any], key_fields: tuple[str, ...]) -> str:
    return "|".join(str(row.get(field, "")).strip() for field in key_fields)


def _dict_value(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _strip_ignored_keys(value: Any, ignored_keys: set[str]) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _strip_ignored_keys(item, ignored_keys)
            for key, item in value.items()
            if str(key) not in ignored_keys
        }
    if isinstance(value, list):
        return [_strip_ignored_keys(item, ignored_keys) for item in value]
    return value


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value
