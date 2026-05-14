# mypy: ignore-errors
"""Minimal RBC helpers needed by the ported TEP_KG Root-KGD module."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from pathlib import Path

from kgtracevis.workflows.tep_root_kgd.assets import read_jsonl


def stable_id(prefix: str, parts: Iterable[object]) -> str:
    """Return the same stable id format used by TEP_KG."""
    payload = "|".join(str(part) for part in parts).encode("utf-8")
    return prefix + "_" + hashlib.sha1(payload).hexdigest()[:16]


def load_tep_mapping(project_root: Path) -> list[dict[str, object]]:
    """Load TEP channel-to-KG variable mapping rows."""
    rows = read_jsonl(project_root / "data" / "processed" / "kg" / "tep_variable_mapping.jsonl")
    return sorted(
        rows,
        key=lambda row: (
            str(row.get("tep_variable_family", "")),
            int(row.get("tep_variable_index", 0)),
            str(row.get("sequence_column", "")),
        ),
    )


def build_rbc(project_root: Path) -> None:
    """Placeholder for batch artifact generation, intentionally disabled here."""
    raise FileNotFoundError(
        "RBC scenario artifacts are not generated inside KGTraceVis runtime inference; "
        f"missing assets under {project_root}"
    )
