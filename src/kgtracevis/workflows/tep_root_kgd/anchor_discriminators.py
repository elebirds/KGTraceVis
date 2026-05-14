# mypy: ignore-errors
"""Anchor discriminator asset loading for KGTraceVis Root-KGD inference."""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_ARTIFACT_REL_PATH = Path("data/processed/rca/anchor_discriminators.json")


def load_anchor_discriminators(project_root: Path) -> dict[str, dict[str, object]]:
    """Load TEP_KG anchor discriminator rows keyed by anchor id."""
    path = project_root / DEFAULT_ARTIFACT_REL_PATH
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("anchors", [])
    if not isinstance(rows, list):
        return {}
    return {
        str(row["anchor_id"]): row
        for row in rows
        if isinstance(row, dict) and row.get("anchor_id")
    }
