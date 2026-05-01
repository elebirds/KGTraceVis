"""Tests for the reusable analysis pipeline."""

from __future__ import annotations

from pathlib import Path

from kgtracevis.core import KGTracePipeline
from kgtracevis.schema.validators import load_evidence_json


def test_pipeline_analyzes_all_examples() -> None:
    """The v0 pipeline should produce links, scores, and paths for examples."""
    pipeline = KGTracePipeline()

    for path in sorted(Path("data/examples").glob("*.json")):
        result = pipeline.analyze(load_evidence_json(path))

        assert result.linked_entities
        assert result.consistency_score is not None
        assert result.top_k_paths
