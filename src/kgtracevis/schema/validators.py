"""Validation helpers for project data files."""

from __future__ import annotations

from pathlib import Path

from kgtracevis.schema.evidence_schema import Evidence


def load_evidence_json(path: str | Path) -> Evidence:
    """Load and validate one evidence JSON file."""
    return Evidence.model_validate_json(Path(path).read_text(encoding="utf-8"))
