"""Replay review decisions through a source-to-KG construction build."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kgtracevis.kg_construction import load_source_library
from kgtracevis.kg_construction.models import (
    KGConstructionReviewDecision,
    kg_construction_artifact_paths,
)
from kgtracevis.kg_construction.publish import load_review_decisions
from kgtracevis.workflows.source_kg_construction import (
    SourceKGConstructionWorkflowConfig,
    SourceKGConstructionWorkflowResult,
    run_source_kg_construction_workflow,
)


@dataclass(frozen=True)
class ReplayKGConstructionReviewsConfig:
    """Configuration for replaying review decisions through a build."""

    output_dir: Path
    run_id: str | None = None


@dataclass(frozen=True)
class ReplayKGConstructionReviewsResult:
    """Result of replaying construction review decisions."""

    run_id: str
    output_dir: Path
    decision_count: int
    replayed_target_type_counts: dict[str, int]
    build_result: SourceKGConstructionWorkflowResult
    summary: dict[str, Any]


def replay_kg_construction_reviews(
    config: ReplayKGConstructionReviewsConfig,
) -> ReplayKGConstructionReviewsResult:
    """Rebuild a construction output directory with recorded review decisions."""
    artifact_paths = kg_construction_artifact_paths(config.output_dir)
    if not artifact_paths["source_library_manifest"].is_file():
        raise ValueError(
            "cannot replay construction reviews without source_library_manifest.json"
        )
    if not artifact_paths["manifest"].is_file():
        raise ValueError("cannot replay construction reviews without manifest")
    sources = tuple(
        record.to_construction_source()
        for record in load_source_library(artifact_paths["source_library_manifest"])
    )
    decisions = load_review_decisions(artifact_paths["review_decisions"])
    run_id = config.run_id or _run_id_from_manifest(artifact_paths["manifest"])
    build_result = run_source_kg_construction_workflow(
        SourceKGConstructionWorkflowConfig(
            output_dir=config.output_dir,
            sources=sources,
            overwrite=True,
            run_id=run_id,
            review_decisions=decisions,
        )
    )
    counts = _target_type_counts(decisions)
    summary = dict(build_result.summary)
    summary["review_replay"] = {
        "decision_count": len(decisions),
        "target_type_counts": counts,
    }
    build_result.summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    manifest = json.loads(build_result.manifest_path.read_text(encoding="utf-8"))
    manifest["summary"]["review_replay"] = summary["review_replay"]
    build_result.manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return ReplayKGConstructionReviewsResult(
        run_id=build_result.run_id,
        output_dir=build_result.output_dir,
        decision_count=len(decisions),
        replayed_target_type_counts=counts,
        build_result=build_result,
        summary=summary,
    )


def _run_id_from_manifest(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"construction manifest must be an object: {path}")
    run = payload.get("run")
    if isinstance(run, dict) and str(run.get("run_id") or ""):
        return str(run["run_id"])
    summary = payload.get("summary")
    if isinstance(summary, dict) and str(summary.get("run_id") or ""):
        return str(summary["run_id"])
    raise ValueError(f"construction manifest missing run_id: {path}")


def _target_type_counts(
    decisions: tuple[KGConstructionReviewDecision, ...],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for decision in decisions:
        counts[decision.target_type] = counts.get(decision.target_type, 0) + 1
    return dict(sorted(counts.items()))
