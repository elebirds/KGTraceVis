# mypy: ignore-errors
"""Scenario dynamic feature asset loading for KGTraceVis Root-KGD inference."""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_ARTIFACT_REL_PATH = Path("data/processed/rca/scenario_dynamic_features.json")


def load_scenario_dynamic_features(project_root: Path) -> dict[str, dict[str, object]]:
    """Load cached TEP_KG dynamic feature rows keyed by scenario id if present."""
    path = project_root / DEFAULT_ARTIFACT_REL_PATH
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("scenarios", [])
    if not isinstance(rows, list):
        return {}
    return {
        str(row["scenario_id"]): row
        for row in rows
        if isinstance(row, dict) and row.get("scenario_id")
    }
