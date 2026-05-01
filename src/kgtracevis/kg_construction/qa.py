"""Structured QA checks for source-constrained KG CSV files."""

from __future__ import annotations

import csv
import math
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from kgtracevis.kg.graph import REQUIRED_EDGE_COLUMNS, REQUIRED_NODE_COLUMNS
from kgtracevis.kg_construction.confidence_assigner import edge_weight
from kgtracevis.kg_construction.export_kg_csv import VALID_REVIEW_STATUS

FindingSeverity = Literal["issue", "warning"]

DEFAULT_REVIEWED_LOW_CONFIDENCE_THRESHOLD = 0.7


@dataclass(frozen=True)
class KGQAFinding:
    """One structured KG QA finding."""

    code: str
    severity: FindingSeverity
    message: str
    file: str
    row_number: int | None = None
    edge_id: str | None = None
    node_id: str | None = None
    field: str | None = None
    value: str | None = None

    def model_dump(self) -> dict[str, object]:
        """Return a JSON-serializable finding."""
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "file": self.file,
            "row_number": self.row_number,
            "edge_id": self.edge_id,
            "node_id": self.node_id,
            "field": self.field,
            "value": self.value,
        }


@dataclass(frozen=True)
class KGQAReport:
    """Structured KG QA report for CLI output and tests."""

    artifact_type: str
    artifact_scope: str
    node_paths: list[str]
    edge_paths: list[str]
    node_count: int
    edge_count: int
    findings: list[KGQAFinding] = field(default_factory=list)
    reviewed_low_confidence_threshold: float = DEFAULT_REVIEWED_LOW_CONFIDENCE_THRESHOLD
    metric_note: str = (
        "KG QA reports source-constrained CSV issues and warnings; it does not edit "
        "or invent KG facts."
    )

    @property
    def issue_count(self) -> int:
        """Return the number of issue-severity findings."""
        return sum(1 for finding in self.findings if finding.severity == "issue")

    @property
    def warning_count(self) -> int:
        """Return the number of warning-severity findings."""
        return sum(1 for finding in self.findings if finding.severity == "warning")

    @property
    def passed(self) -> bool:
        """Return whether QA found no issue-severity findings."""
        return self.issue_count == 0

    def summary(self) -> dict[str, object]:
        """Return compact counts for script output and table summaries."""
        codes = Counter(finding.code for finding in self.findings)
        return {
            "passed": self.passed,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "issue_count": self.issue_count,
            "warning_count": self.warning_count,
            "finding_codes": dict(sorted(codes.items())),
        }

    def model_dump(self) -> dict[str, object]:
        """Return a JSON-serializable QA report."""
        return {
            "artifact_type": self.artifact_type,
            "artifact_scope": self.artifact_scope,
            "node_paths": self.node_paths,
            "edge_paths": self.edge_paths,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "reviewed_low_confidence_threshold": self.reviewed_low_confidence_threshold,
            "metric_note": self.metric_note,
            "summary": self.summary(),
            "findings": [finding.model_dump() for finding in self.findings],
        }


def run_kg_qa(
    node_paths: list[str | Path],
    edge_paths: list[str | Path],
    *,
    reviewed_low_confidence_threshold: float = DEFAULT_REVIEWED_LOW_CONFIDENCE_THRESHOLD,
) -> KGQAReport:
    """Inspect KG CSV rows and return structured issues and warnings."""
    node_rows, node_findings = _read_rows(node_paths, REQUIRED_NODE_COLUMNS, row_type="node")
    edge_rows, edge_findings = _read_rows(edge_paths, REQUIRED_EDGE_COLUMNS, row_type="edge")

    findings = [*node_findings, *edge_findings]
    node_ids = {
        row["id"].strip()
        for row in node_rows
        if "id" in row and row["id"].strip()
    }
    edge_ids_seen: set[str] = set()
    connected_node_ids: set[str] = set()

    for row in edge_rows:
        findings.extend(
            _check_edge_row(
                row,
                node_ids,
                edge_ids_seen,
                reviewed_low_confidence_threshold=reviewed_low_confidence_threshold,
            )
        )
        head = row.get("head", "").strip()
        tail = row.get("tail", "").strip()
        if head:
            connected_node_ids.add(head)
        if tail:
            connected_node_ids.add(tail)

    isolated_node_ids = sorted(node_ids - connected_node_ids)
    for row in node_rows:
        node_id = row.get("id", "").strip()
        if node_id in isolated_node_ids:
            findings.append(
                KGQAFinding(
                    code="isolated_node",
                    severity="warning",
                    message=f"node has no incident raw CSV edges: {node_id}",
                    file=row["_file"],
                    row_number=_row_number(row),
                    node_id=node_id,
                )
            )

    return KGQAReport(
        artifact_type="kg_qa_v0",
        artifact_scope="generated_reproducibility_output",
        node_paths=[str(path) for path in node_paths],
        edge_paths=[str(path) for path in edge_paths],
        node_count=len(node_rows),
        edge_count=len(edge_rows),
        findings=findings,
        reviewed_low_confidence_threshold=reviewed_low_confidence_threshold,
    )


def _read_rows(
    paths: list[str | Path],
    required_columns: set[str],
    *,
    row_type: str,
) -> tuple[list[dict[str, str]], list[KGQAFinding]]:
    rows: list[dict[str, str]] = []
    findings: list[KGQAFinding] = []
    for path_value in paths:
        path = Path(path_value)
        if not path.exists():
            findings.append(
                KGQAFinding(
                    code=f"missing_{row_type}_csv",
                    severity="issue",
                    message=f"{row_type} CSV file not found: {path}",
                    file=str(path),
                )
            )
            continue
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            actual_columns = set(reader.fieldnames or [])
            missing = sorted(required_columns - actual_columns)
            for column in missing:
                findings.append(
                    KGQAFinding(
                        code=f"missing_{row_type}_column",
                        severity="issue",
                        message=f"{row_type} CSV missing required column: {column}",
                        file=str(path),
                        field=column,
                    )
                )
            if missing:
                continue
            for row_number, raw_row in enumerate(reader, start=2):
                row = {key: (value or "") for key, value in raw_row.items()}
                row["_file"] = str(path)
                row["_row_number"] = str(row_number)
                rows.append(row)
    return rows, findings


def _check_edge_row(
    row: dict[str, str],
    node_ids: set[str],
    edge_ids_seen: set[str],
    *,
    reviewed_low_confidence_threshold: float,
) -> list[KGQAFinding]:
    findings: list[KGQAFinding] = []
    edge_id = _edge_id(row)
    file_path = row["_file"]
    row_number = _row_number(row)

    for field_name in ("source", "evidence"):
        if not row.get(field_name, "").strip():
            findings.append(
                KGQAFinding(
                    code="missing_provenance",
                    severity="issue",
                    message=f"edge is missing required provenance field: {field_name}",
                    file=file_path,
                    row_number=row_number,
                    edge_id=edge_id,
                    field=field_name,
                    value=row.get(field_name, ""),
                )
            )

    findings.extend(_check_endpoint(row, "head", node_ids, edge_id))
    findings.extend(_check_endpoint(row, "tail", node_ids, edge_id))

    if edge_id in edge_ids_seen:
        findings.append(
            KGQAFinding(
                code="duplicate_edge_id",
                severity="issue",
                message=f"duplicate raw CSV edge id: {edge_id}",
                file=file_path,
                row_number=row_number,
                edge_id=edge_id,
            )
        )
    edge_ids_seen.add(edge_id)

    confidence = _parse_float(row, "confidence", edge_id, findings)
    weight = _parse_float(row, "weight", edge_id, findings)
    if confidence is not None:
        if not 0.0 <= confidence <= 1.0:
            findings.append(
                KGQAFinding(
                    code="invalid_confidence",
                    severity="issue",
                    message=f"confidence must be in [0, 1] for {edge_id}",
                    file=file_path,
                    row_number=row_number,
                    edge_id=edge_id,
                    field="confidence",
                    value=row.get("confidence", ""),
                )
            )
        if (
            weight is not None
            and 0.0 <= confidence <= 1.0
            and not math.isclose(weight, edge_weight(confidence), abs_tol=1e-6)
        ):
            findings.append(
                KGQAFinding(
                    code="weight_contract_violation",
                    severity="issue",
                    message=f"weight must equal 1 - confidence for {edge_id}",
                    file=file_path,
                    row_number=row_number,
                    edge_id=edge_id,
                    field="weight",
                    value=row.get("weight", ""),
                )
            )

    review_status = row.get("review_status", "").strip()
    if review_status not in VALID_REVIEW_STATUS:
        findings.append(
            KGQAFinding(
                code="invalid_review_status",
                severity="issue",
                message=f"invalid review_status for {edge_id}: {review_status}",
                file=file_path,
                row_number=row_number,
                edge_id=edge_id,
                field="review_status",
                value=review_status,
            )
        )
    if (
        review_status == "reviewed"
        and confidence is not None
        and confidence < reviewed_low_confidence_threshold
    ):
        findings.append(
            KGQAFinding(
                code="reviewed_low_confidence",
                severity="warning",
                message=f"reviewed edge has low confidence for {edge_id}",
                file=file_path,
                row_number=row_number,
                edge_id=edge_id,
                field="confidence",
                value=row.get("confidence", ""),
            )
        )

    for field_name in ("feedback_count", "accepted_count", "rejected_count"):
        counter = _parse_int(row, field_name, edge_id, findings)
        if counter is not None and counter < 0:
            findings.append(
                KGQAFinding(
                    code="negative_feedback_counter",
                    severity="issue",
                    message=f"feedback counter must be non-negative for {edge_id}",
                    file=file_path,
                    row_number=row_number,
                    edge_id=edge_id,
                    field=field_name,
                    value=row.get(field_name, ""),
                )
            )

    return findings


def _check_endpoint(
    row: dict[str, str],
    field_name: str,
    node_ids: set[str],
    edge_id: str,
) -> list[KGQAFinding]:
    node_id = row.get(field_name, "").strip()
    if node_id in node_ids:
        return []
    return [
        KGQAFinding(
            code="missing_edge_endpoint",
            severity="issue",
            message=f"edge {field_name} is not present in node CSV rows: {node_id}",
            file=row["_file"],
            row_number=_row_number(row),
            edge_id=edge_id,
            node_id=node_id,
            field=field_name,
            value=node_id,
        )
    ]


def _parse_float(
    row: dict[str, str],
    field_name: str,
    edge_id: str,
    findings: list[KGQAFinding],
) -> float | None:
    value = row.get(field_name, "").strip()
    try:
        return float(value)
    except ValueError:
        findings.append(
            KGQAFinding(
                code=f"invalid_{field_name}",
                severity="issue",
                message=f"{field_name} must be numeric for {edge_id}",
                file=row["_file"],
                row_number=_row_number(row),
                edge_id=edge_id,
                field=field_name,
                value=value,
            )
        )
        return None


def _parse_int(
    row: dict[str, str],
    field_name: str,
    edge_id: str,
    findings: list[KGQAFinding],
) -> int | None:
    value = row.get(field_name, "").strip()
    try:
        return int(value)
    except ValueError:
        findings.append(
            KGQAFinding(
                code="invalid_feedback_counter",
                severity="issue",
                message=f"feedback counter must be an integer for {edge_id}",
                file=row["_file"],
                row_number=_row_number(row),
                edge_id=edge_id,
                field=field_name,
                value=value,
            )
        )
        return None


def _edge_id(row: dict[str, str]) -> str:
    return "|".join(
        row.get(field_name, "").strip()
        for field_name in ("head", "relation", "tail", "scenario")
    )


def _row_number(row: dict[str, str]) -> int:
    return int(row["_row_number"])
