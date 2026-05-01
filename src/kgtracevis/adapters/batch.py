"""Batch loaders and writers for unified evidence generation."""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from kgtracevis.adapters.ds_mvtec_adapter import evidence_from_mvtec_record
from kgtracevis.adapters.tep_adapter import evidence_from_tep_record
from kgtracevis.adapters.wafer_adapter import evidence_from_wafer_record
from kgtracevis.schema.evidence_schema import DatasetName, Evidence

DatasetAdapter = Callable[[Mapping[str, Any]], Evidence]

DATASET_ADAPTERS: dict[DatasetName, DatasetAdapter] = {
    "mvtec": evidence_from_mvtec_record,
    "tep": evidence_from_tep_record,
    "wafer": evidence_from_wafer_record,
}


@dataclass(frozen=True)
class BatchEvidenceSummary:
    """Compact counts for generated evidence records."""

    total_count: int
    by_dataset: dict[str, int]
    by_source: dict[str, int]

    def model_dump(self) -> dict[str, object]:
        """Return a JSON-serializable summary mapping."""
        return {
            "total_count": self.total_count,
            "by_dataset": self.by_dataset,
            "by_source": self.by_source,
        }


def load_records(path: str | Path) -> list[dict[str, Any]]:
    """Load record dictionaries from JSON, JSONL, or CSV."""
    input_path = Path(path)
    suffix = input_path.suffix.lower()
    if suffix == ".json":
        return _load_json_records(input_path)
    if suffix == ".jsonl":
        return _load_jsonl_records(input_path)
    if suffix == ".csv":
        return _load_csv_records(input_path)
    raise ValueError(f"unsupported input format for {input_path}: expected .json, .jsonl, or .csv")


def evidence_from_records(
    records: Sequence[Mapping[str, Any]],
    *,
    dataset: DatasetName | None = None,
) -> list[Evidence]:
    """Convert batch input records into validated evidence objects."""
    evidence_items: list[Evidence] = []
    for index, record in enumerate(records, start=1):
        record_dataset = dataset or _dataset_from_record(record, index=index)
        adapter = DATASET_ADAPTERS[record_dataset]
        evidence_items.append(adapter(record))
    return evidence_items


def summarize_evidence(evidence_items: Iterable[Evidence]) -> BatchEvidenceSummary:
    """Summarize generated evidence by dataset and source."""
    items = list(evidence_items)
    by_dataset: Counter[str] = Counter(item.dataset for item in items)
    by_source: Counter[str] = Counter(item.source for item in items)
    return BatchEvidenceSummary(
        total_count=len(items),
        by_dataset=dict(sorted(by_dataset.items())),
        by_source=dict(sorted(by_source.items())),
    )


def write_evidence_files(
    evidence_items: Sequence[Evidence],
    output_dir: str | Path,
    *,
    overwrite: bool = False,
) -> list[Path]:
    """Write one JSON file per evidence object under an output directory."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    destinations = [_evidence_path(output_path, evidence) for evidence in evidence_items]
    _ensure_unique_destinations(destinations)
    for destination in destinations:
        _ensure_can_write(destination, overwrite=overwrite)

    written: list[Path] = []
    for evidence, destination in zip(evidence_items, destinations, strict=True):
        destination.write_text(_evidence_json(evidence), encoding="utf-8")
        written.append(destination)
    return written


def write_evidence_jsonl(
    evidence_items: Sequence[Evidence],
    output_path: str | Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Write all evidence objects to one JSONL file."""
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    _ensure_can_write(destination, overwrite=overwrite)
    lines = [_evidence_json(evidence, indent=None) for evidence in evidence_items]
    destination.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return destination


def _load_json_records(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return _validate_record_list(payload, path=path)
    if isinstance(payload, Mapping) and "records" in payload:
        records = payload["records"]
        if isinstance(records, list):
            return _validate_record_list(records, path=path)
    raise ValueError(f"{path} must contain a JSON list or an object with a 'records' list")


def _load_jsonl_records(path: Path) -> list[dict[str, Any]]:
    records: list[Any] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            payload = json.loads(stripped)
            if not isinstance(payload, Mapping):
                raise ValueError(f"{path}:{line_number} must contain a JSON object")
            records.append(dict(payload))
    return cast(list[dict[str, Any]], records)


def _load_csv_records(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"{path} is missing a CSV header row")
        return [dict(row) for row in reader]


def _validate_record_list(items: Sequence[Any], *, path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, Mapping):
            raise ValueError(f"{path} record {index} must be an object")
        records.append(dict(item))
    return records


def _dataset_from_record(record: Mapping[str, Any], *, index: int) -> DatasetName:
    raw_dataset = record.get("dataset")
    if raw_dataset is None or str(raw_dataset).strip() == "":
        raise ValueError(
            f"record {index} is missing dataset; pass --dataset or include per-record dataset"
        )
    dataset = str(raw_dataset).strip().lower()
    if dataset not in DATASET_ADAPTERS:
        valid = ", ".join(DATASET_ADAPTERS)
        raise ValueError(
            f"record {index} has unsupported dataset {raw_dataset!r}; expected one of: {valid}"
        )
    return cast(DatasetName, dataset)


def _ensure_can_write(path: Path, *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"{path} already exists; pass --overwrite to replace it")


def _ensure_unique_destinations(paths: Sequence[Path]) -> None:
    seen: set[Path] = set()
    duplicates: list[str] = []
    for path in paths:
        if path in seen:
            duplicates.append(str(path))
        seen.add(path)
    if duplicates:
        duplicate_list = ", ".join(sorted(set(duplicates)))
        raise ValueError(f"multiple evidence records would write the same file: {duplicate_list}")


def _evidence_path(output_dir: Path, evidence: Evidence) -> Path:
    return output_dir / f"{_safe_filename(evidence.case_id)}.json"


def _evidence_json(evidence: Evidence, *, indent: int | None = 2) -> str:
    return json.dumps(evidence.model_dump(mode="json"), indent=indent, sort_keys=False)


def _safe_filename(case_id: str) -> str:
    filename = re.sub(r"[^A-Za-z0-9_.-]+", "_", case_id).strip("._")
    return filename or "unknown_case"
