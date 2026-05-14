# mypy: ignore-errors
"""Asset governance utilities for Plan 02."""

# ruff: noqa

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


MATERIAL_EXTENSIONS = {
    ".txt": "doc",
    ".md": "doc",
    ".pdf": "doc",
    ".m": "code",
    ".c": "code",
    ".h": "code",
    ".mdl": "model",
    ".mat": "data",
    ".csv": "data",
    ".mexw64": "binary",
}


@dataclass(frozen=True)
class AssetRecord:
    asset_id: str
    relative_path: str
    source_tier: str
    version: str
    sha256: str
    size_bytes: int
    content_type: str
    status: str
    trust_score: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classify_asset(path: Path) -> str:
    return MATERIAL_EXTENSIONS.get(path.suffix.lower(), "other")


def make_asset_id(relative_path: str) -> str:
    stable = relative_path.replace("\\", "/").lower().encode("utf-8")
    return "asset_" + hashlib.sha1(stable).hexdigest()[:16]


def inventory_materials(project_root: Path, materials_dir: Path) -> list[AssetRecord]:
    records: list[AssetRecord] = []
    for path in sorted(materials_dir.rglob("*")):
        if not path.is_file():
            continue
        relative_path = path.relative_to(project_root).as_posix()
        content_type = classify_asset(path)
        source_tier = "publication_supplement" if relative_path.startswith("materials/") else "local"
        trust_score = 0.9 if source_tier == "publication_supplement" else 0.5
        records.append(
            AssetRecord(
                asset_id=make_asset_id(relative_path),
                relative_path=relative_path,
                source_tier=source_tier,
                version="local-2026-04-30",
                sha256=sha256_file(path),
                size_bytes=path.stat().st_size,
                content_type=content_type,
                status="accepted",
                trust_score=trust_score,
            )
        )
    return records


def write_jsonl(records: Iterable[object], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            if hasattr(record, "to_dict"):
                payload = record.to_dict()
            else:
                payload = record
            handle.write(json.dumps(payload, sort_keys=True, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(json.loads(line))
    return records
