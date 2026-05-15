"""Source registry and source text loading utilities."""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any

SOURCE_REGISTRY_COLUMNS = {
    "source_id",
    "title",
    "type",
    "path_or_url",
    "used_for",
    "notes",
}


@dataclass(frozen=True)
class SourceRecord:
    """One registered KG construction source."""

    source_id: str
    title: str
    source_type: str
    path_or_url: str
    used_for: str
    notes: str = ""

    @classmethod
    def from_row(cls, row: Mapping[str, str]) -> SourceRecord:
        """Build a source record from a source registry CSV row."""
        return cls(
            source_id=row["source_id"].strip(),
            title=row["title"].strip(),
            source_type=row["type"].strip(),
            path_or_url=row["path_or_url"].strip(),
            used_for=row["used_for"].strip(),
            notes=row.get("notes", "").strip(),
        )


def load_source_registry(path: str | Path = "data/kg/source_registry.csv") -> list[SourceRecord]:
    """Load and validate the source registry CSV."""
    registry_path = Path(path)
    with registry_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        _require_columns(registry_path, reader.fieldnames, SOURCE_REGISTRY_COLUMNS)
        records = [SourceRecord.from_row(row) for row in reader]

    source_ids: set[str] = set()
    for record in records:
        if not record.source_id:
            raise ValueError(f"{registry_path} contains a source with an empty source_id")
        if record.source_id in source_ids:
            raise ValueError(f"{registry_path} contains duplicate source_id: {record.source_id}")
        source_ids.add(record.source_id)
    return records


def load_source_text(
    source: SourceRecord,
    *,
    base_dir: str | Path = ".",
    max_bytes: int = 1_000_000,
) -> str:
    """Load local text for a source registry record.

    URLs are intentionally rejected here; v0 KG construction is source-constrained
    and does not scrape remote content.
    """
    if _looks_like_url(source.path_or_url):
        raise ValueError(f"remote source loading is not supported: {source.source_id}")

    source_path = _resolve_local_path(source.path_or_url, base_dir=base_dir)
    if source_path.is_dir():
        return _load_directory_text(source_path, max_bytes=max_bytes)
    if not source_path.exists():
        raise ValueError(f"source path does not exist for {source.source_id}: {source_path}")
    return _read_text_file(source_path, max_bytes=max_bytes)


def load_structured_records(path: str | Path) -> list[dict[str, Any]]:
    """Load structured CSV, JSON, or JSONL records for candidate extraction."""
    record_path = Path(path)
    suffix = record_path.suffix.lower()
    if suffix == ".csv":
        with record_path.open(newline="", encoding="utf-8") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    if suffix == ".jsonl":
        with record_path.open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]
    if suffix == ".json":
        with record_path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, list):
            return [dict(item) for item in data if isinstance(item, Mapping)]
        if isinstance(data, Mapping) and isinstance(data.get("records"), list):
            return [dict(item) for item in data["records"] if isinstance(item, Mapping)]
        raise ValueError(f"{record_path} must contain a list or a records list")
    raise ValueError(f"unsupported structured source type: {record_path}")


def load_structured_record_text(
    text: str,
    *,
    source_format: str,
) -> list[dict[str, Any]]:
    """Load structured CSV, JSON, or JSONL records from inline source text."""
    normalized_format = source_format.lower().lstrip(".")
    if normalized_format == "csv":
        return [dict(row) for row in csv.DictReader(StringIO(text))]
    if normalized_format == "jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    if normalized_format == "json":
        data = json.loads(text)
        if isinstance(data, list):
            return [dict(item) for item in data if isinstance(item, Mapping)]
        if isinstance(data, Mapping) and isinstance(data.get("records"), list):
            return [dict(item) for item in data["records"] if isinstance(item, Mapping)]
        raise ValueError("structured JSON source text must contain a list or records list")
    raise ValueError(f"unsupported structured source text format: {source_format}")


def _resolve_local_path(path_or_url: str, *, base_dir: str | Path) -> Path:
    path = Path(path_or_url)
    if path.is_absolute():
        return path
    return Path(base_dir) / path


def _load_directory_text(path: Path, *, max_bytes: int) -> str:
    text_parts: list[str] = []
    remaining = max_bytes
    for child in sorted(path.rglob("*")):
        if child.is_dir() or child.suffix.lower() not in {".txt", ".md", ".csv", ".json", ".jsonl"}:
            continue
        content = _read_text_file(child, max_bytes=remaining)
        text_parts.append(f"# {child.relative_to(path)}\n{content}")
        remaining -= len(content.encode("utf-8"))
        if remaining <= 0:
            break
    return "\n\n".join(text_parts)


def _read_text_file(path: Path, *, max_bytes: int) -> str:
    with path.open("rb") as handle:
        content = handle.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise ValueError(f"source file is larger than max_bytes: {path}")
    return content.decode("utf-8")


def _looks_like_url(value: str) -> bool:
    lowered = value.lower()
    return lowered.startswith(("http://", "https://"))


def _require_columns(path: Path, actual: Sequence[str] | None, required: set[str]) -> None:
    actual_set = set(actual or [])
    missing = sorted(required - actual_set)
    if missing:
        raise ValueError(f"{path} missing required columns: {', '.join(missing)}")
