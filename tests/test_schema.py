"""Tests for the unified evidence schema."""

from __future__ import annotations

from pathlib import Path

from kgtracevis.schema.validators import load_evidence_json


def test_example_evidence_files_validate() -> None:
    """All checked-in example evidence files should validate."""
    paths = sorted(Path("data/examples").glob("*.json"))
    assert paths
    for path in paths:
        evidence = load_evidence_json(path)
        assert evidence.case_id
        assert evidence.dataset in {"mvtec", "tep", "wafer"}
