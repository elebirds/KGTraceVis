"""Source library records for RCA-oriented KG generation."""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kgtracevis.kg_construction.draft import KGConstructionSource


@dataclass(frozen=True)
class SourceLibraryRecord:
    """Registered source material before parsing or extraction."""

    source_id: str
    source_type: str
    scenario: str
    path: Path | None = None
    url: str = ""
    text: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    provenance_policy: str = "source_grounded_candidate"

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> SourceLibraryRecord:
        """Build a source library record from a JSON/CSV mapping."""
        source_id = _required_text(payload, "source_id")
        source_type = _optional_text(payload, "source_type") or _required_text(payload, "type")
        scenario = _optional_text(payload, "scenario") or "shared"
        path_value = _optional_text(payload, "path") or _optional_text(payload, "path_or_url")
        url = _optional_text(payload, "url")
        path: Path | None = None
        if path_value:
            if path_value.startswith(("http://", "https://")):
                url = path_value
            else:
                path = Path(path_value)
        metadata = _metadata_from_payload(payload.get("metadata"))
        return cls(
            source_id=source_id,
            source_type=source_type,
            scenario=scenario,
            path=path,
            url=url,
            text=_optional_text(payload, "text") or None,
            metadata=metadata,
            created_at=_optional_text(payload, "created_at"),
            provenance_policy=(
                _optional_text(payload, "provenance_policy")
                or "source_grounded_candidate"
            ),
        )

    def to_construction_source(self) -> KGConstructionSource:
        """Convert the library record into the extractor source contract."""
        metadata = dict(self.metadata)
        if self.url:
            metadata["url"] = self.url
        metadata["provenance_policy"] = self.provenance_policy
        metadata["created_at"] = self.created_at or current_utc_iso()
        return KGConstructionSource(
            source_id=self.source_id,
            source_type=self.source_type,
            scenario=self.scenario,
            path=self.path,
            text=self.text,
            metadata=metadata,
        )

    def manifest_payload(self) -> dict[str, Any]:
        """Return an audit-safe source library payload without inline text."""
        payload: dict[str, Any] = {
            "source_id": self.source_id,
            "source_type": self.source_type,
            "scenario": self.scenario,
            "path": str(self.path) if self.path is not None else "",
            "url": self.url,
            "has_text": self.text is not None,
            "metadata": _jsonable(self.metadata),
            "created_at": self.created_at,
            "provenance_policy": self.provenance_policy,
        }
        return payload


def load_source_library(path: str | Path) -> tuple[SourceLibraryRecord, ...]:
    """Load Source Library records from CSV, JSON, or JSONL."""
    source_path = Path(path)
    suffix = source_path.suffix.lower()
    if suffix == ".csv":
        with source_path.open(newline="", encoding="utf-8") as handle:
            rows = [dict(row) for row in csv.DictReader(handle)]
    elif suffix == ".jsonl":
        rows = [
            json.loads(line)
            for line in source_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    elif suffix == ".json":
        payload = json.loads(source_path.read_text(encoding="utf-8"))
        if isinstance(payload, Mapping) and isinstance(payload.get("sources"), list):
            rows = payload["sources"]
        elif isinstance(payload, list):
            rows = payload
        else:
            raise ValueError(f"{source_path} must contain a list or sources list")
    else:
        raise ValueError(f"unsupported source library file type: {source_path}")

    records = tuple(
        SourceLibraryRecord.from_mapping(row)
        for row in rows
        if isinstance(row, Mapping)
    )
    _validate_source_library(records, source_path=source_path)
    return records


def write_source_library_manifest(
    path: str | Path,
    records: Sequence[SourceLibraryRecord],
) -> Path:
    """Write an audit-safe Source Library manifest."""
    manifest_path = Path(path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "artifact_type": "source_library_manifest_v1",
        "source_count": len(records),
        "source_ids": [record.source_id for record in records],
        "sources": [record.manifest_payload() for record in records],
    }
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return manifest_path


def current_utc_iso() -> str:
    """Return the current UTC timestamp in JSON-friendly ISO format."""
    return datetime.now(timezone.utc).isoformat()


def _validate_source_library(
    records: Sequence[SourceLibraryRecord],
    *,
    source_path: Path,
) -> None:
    seen: set[str] = set()
    for record in records:
        if not record.source_id:
            raise ValueError(f"{source_path} contains a source with an empty source_id")
        if record.source_id in seen:
            raise ValueError(f"{source_path} contains duplicate source_id: {record.source_id}")
        seen.add(record.source_id)
        if not record.source_type:
            raise ValueError(f"{source_path} contains source without source_type")
        if record.path is None and not record.url and record.text is None:
            raise ValueError(
                f"{source_path} source requires path, url, or text: {record.source_id}"
            )


def _required_text(payload: Mapping[str, Any], key: str) -> str:
    value = _optional_text(payload, key)
    if not value:
        raise ValueError(f"source library record missing required field: {key}")
    return value


def _optional_text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if value is None:
        return ""
    return str(value).strip()


def _metadata_from_payload(value: object) -> dict[str, Any]:
    if value is None or value == "":
        return {}
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    if isinstance(value, str):
        payload = json.loads(value)
        if isinstance(payload, Mapping):
            return {str(key): item for key, item in payload.items()}
    raise ValueError("source library metadata must be a JSON object")


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value
