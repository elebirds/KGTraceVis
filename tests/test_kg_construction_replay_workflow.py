"""Tests for replaying KG construction review decisions."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

from kgtracevis.kg_construction import KGConstructionSource
from kgtracevis.workflows.kg_construction_replay import (
    ReplayKGConstructionReviewsConfig,
    replay_kg_construction_reviews,
)
from kgtracevis.workflows.kg_construction_review import (
    ReviewKGConstructionItemConfig,
    review_kg_construction_item_artifact,
)
from kgtracevis.workflows.source_kg_construction import (
    SourceKGConstructionWorkflowConfig,
    run_source_kg_construction_workflow,
)


def test_replay_accepts_entity_merge_and_regenerates_layers(
    tmp_path: Path,
) -> None:
    """Accepted merge decisions should replay into regenerated alignment outputs."""
    build = _build_alignment_candidate(tmp_path / "accept_candidate")
    target_key = _merge_target_key(build.review_queue_path)
    review_kg_construction_item_artifact(
        ReviewKGConstructionItemConfig(
            output_dir=build.output_dir,
            action="accept",
            target_key=target_key,
            item_type="entity_merge_candidate",
            proposed_payload={"reviewed_canonical_id": "PumpA"},
        )
    )

    result = replay_kg_construction_reviews(
        ReplayKGConstructionReviewsConfig(output_dir=build.output_dir)
    )

    node_rows = _read_csv_rows(result.build_result.nodes_path)
    review_queue = json.loads(result.build_result.review_queue_path.read_text())
    decisions = _read_jsonl(result.build_result.output_dir / "review_decisions.jsonl")
    summary = json.loads(result.build_result.summary_path.read_text())

    assert [row["id"] for row in node_rows] == ["PumpA"]
    assert not any(item["item_type"] == "entity_merge_candidate" for item in review_queue)
    assert decisions[0]["target_type"] == "entity_merge_candidate"
    assert summary["review_replay"]["decision_count"] == 1
    assert summary["review_replay"]["target_type_counts"] == {
        "entity_merge_candidate": 1
    }
    assert result.decision_count == 1


def test_replay_rejects_entity_merge_and_splits_duplicate(
    tmp_path: Path,
) -> None:
    """Rejected merge decisions should split a deterministic duplicate candidate."""
    build = _build_alignment_candidate(tmp_path / "reject_candidate")
    target_key = _merge_target_key(build.review_queue_path)
    review_kg_construction_item_artifact(
        ReviewKGConstructionItemConfig(
            output_dir=build.output_dir,
            action="reject",
            target_key=target_key,
            item_type="entity_merge_candidate",
        )
    )

    result = replay_kg_construction_reviews(
        ReplayKGConstructionReviewsConfig(output_dir=build.output_dir)
    )

    node_rows = _read_csv_rows(result.build_result.nodes_path)
    review_queue = json.loads(result.build_result.review_queue_path.read_text())
    decisions = _read_jsonl(result.build_result.output_dir / "review_decisions.jsonl")

    assert [row["id"] for row in node_rows] == ["PumpA", "PumpB"]
    assert not any(item["item_type"] == "entity_merge_candidate" for item in review_queue)
    assert decisions[0]["action"] == "reject"
    assert result.replayed_target_type_counts == {"entity_merge_candidate": 1}


def test_replay_source_kg_reviews_cli_rebuilds_reviewed_alignment(
    tmp_path: Path,
) -> None:
    """Replay CLI should rebuild artifacts from source library and decisions."""
    output_dir = tmp_path / "cli_replay_candidate"
    build = _build_alignment_candidate(output_dir)
    target_key = _merge_target_key(build.review_queue_path)
    review_kg_construction_item_artifact(
        ReviewKGConstructionItemConfig(
            output_dir=build.output_dir,
            action="reject",
            target_key=target_key,
            item_type="entity_merge_candidate",
        )
    )

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/replay_source_kg_reviews.py",
            "--build-dir",
            str(output_dir),
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        text=True,
        capture_output=True,
    )

    payload = json.loads(completed.stdout)
    node_rows = _read_csv_rows(output_dir / "nodes.csv")
    assert payload["decision_count"] == 1
    assert payload["replayed_target_type_counts"] == {"entity_merge_candidate": 1}
    assert [row["id"] for row in node_rows] == ["PumpA", "PumpB"]


def test_replay_requires_reconstructable_sources(tmp_path: Path) -> None:
    """Replay should fail clearly when source library artifact is unavailable."""
    output_dir = tmp_path / "missing_sources"
    output_dir.mkdir()

    with pytest.raises(ValueError, match="source_library_manifest"):
        replay_kg_construction_reviews(
            ReplayKGConstructionReviewsConfig(output_dir=output_dir)
        )


def _build_alignment_candidate(output_dir: Path):
    return run_source_kg_construction_workflow(
        SourceKGConstructionWorkflowConfig(
            output_dir=output_dir,
            sources=(
                KGConstructionSource(
                    source_id="alignment_source",
                    source_type="manual_table",
                    scenario="shared",
                    text=_alignment_source_csv(),
                    metadata={"source_format": "csv"},
                ),
            ),
            run_id="kgbuild_replay_alignment",
        )
    )


def _alignment_source_csv() -> str:
    return "\n".join(
        [
            "id,name,label,scenario,evidence,confidence",
            "PumpA,Feed pump,Equipment,shared,pump A row,0.90",
            "PumpB,Feed pump,Equipment,shared,pump B duplicate row,0.87",
            "",
        ]
    )


def _merge_target_key(review_queue_path: Path) -> str:
    review_queue = json.loads(review_queue_path.read_text(encoding="utf-8"))
    return next(
        item["target_key"]
        for item in review_queue
        if item["item_type"] == "entity_merge_candidate"
    )


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
