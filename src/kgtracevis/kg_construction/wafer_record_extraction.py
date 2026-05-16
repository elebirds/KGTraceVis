"""Source-derived wafer evidence-record extraction.

This module converts explicit WM811K-style JSONL evidence records into DraftKG
candidate rows. It does not derive process root causes; it only preserves
source-provided pattern, wafer, location, and morphology fields as reviewable
KG construction candidates.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from kgtracevis.kg_construction.document_extraction import ParsedSourceDocument
from kgtracevis.kg_construction.draft import DraftEntity, DraftKG, DraftRelation

EXTRACTOR_NAME = "wafer_evidence_record_extractor"
EXTRACTOR_VERSION = "v1"


@dataclass(frozen=True)
class WaferRecordExtractionSummary:
    """Audit summary for deterministic wafer evidence-record supplementation."""

    extractor_name: str
    extractor_version: str
    source_id: str
    record_count: int
    entity_count: int
    relation_count: int
    claim_boundary: str = (
        "Wafer record supplementation is explicit evidence-record DraftKG "
        "candidate material. It records pattern/location/morphology fields only "
        "and does not derive process RCA facts or publish KG."
    )

    def to_payload(self) -> dict[str, Any]:
        """Return JSON-serializable manifest payload."""
        return {
            "extractor_name": self.extractor_name,
            "extractor_version": self.extractor_version,
            "source_id": self.source_id,
            "record_count": self.record_count,
            "entity_count": self.entity_count,
            "relation_count": self.relation_count,
            "claim_boundary": self.claim_boundary,
        }


@dataclass(frozen=True)
class WaferRecordExtractionResult:
    """DraftKG supplement plus its audit summary."""

    draft: DraftKG
    summary: WaferRecordExtractionSummary | None = None

    @property
    def has_candidates(self) -> bool:
        """Return True when extraction found source-grounded wafer rows."""
        return bool(self.draft.entities or self.draft.relations)


def extract_wafer_records_from_document(
    document: ParsedSourceDocument,
) -> WaferRecordExtractionResult:
    """Extract explicit wafer evidence-record candidates from JSONL-like text."""
    if document.scenario != "wafer":
        return WaferRecordExtractionResult(draft=DraftKG())
    rows = parse_wafer_evidence_records(document.text)
    if not rows:
        return WaferRecordExtractionResult(draft=DraftKG())
    draft = draft_from_wafer_evidence_records(
        rows,
        source_id=document.source_id,
        scenario=document.scenario,
    )
    summary = WaferRecordExtractionSummary(
        extractor_name=EXTRACTOR_NAME,
        extractor_version=EXTRACTOR_VERSION,
        source_id=document.source_id,
        record_count=len(rows),
        entity_count=len(draft.entities),
        relation_count=len(draft.relations),
    )
    return WaferRecordExtractionResult(draft=draft, summary=summary)


def parse_wafer_evidence_records(text: str) -> tuple[dict[str, Any], ...]:
    """Parse JSONL records that expose wafer pattern evidence fields."""
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        raw = line.strip()
        if not raw or not raw.startswith("{"):
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(value, dict):
            continue
        pattern = _text(value.get("failure_pattern") or value.get("predicted_pattern"))
        if pattern:
            rows.append({"__raw_line__": raw, **value})
    return tuple(rows)


def draft_from_wafer_evidence_records(
    rows: tuple[Mapping[str, Any], ...],
    *,
    source_id: str,
    scenario: str,
) -> DraftKG:
    """Build DraftKG candidates from explicit wafer evidence-record fields."""
    entity_by_id: dict[str, DraftEntity] = {}
    relation_by_key: dict[tuple[str, str, str], DraftRelation] = {}
    for index, row in enumerate(rows, start=1):
        evidence = _text(row.get("__raw_line__")) or json.dumps(row, sort_keys=True)
        pattern = _text(row.get("failure_pattern") or row.get("predicted_pattern"))
        if not pattern:
            continue
        pattern_id = f"{_pascal_id(pattern)}Pattern"
        _add_entity(
            entity_by_id,
            source_id=source_id,
            scenario=scenario,
            entity_id=pattern_id,
            name=f"{_display_label(pattern)} pattern",
            label="DefectType",
            evidence=evidence,
            index=index,
        )
        wafer_id_value = _text(row.get("wafer_id") or row.get("case_id"))
        if wafer_id_value:
            wafer_id = _pascal_id(wafer_id_value)
            _add_entity(
                entity_by_id,
                source_id=source_id,
                scenario=scenario,
                entity_id=wafer_id,
                name=wafer_id_value,
                label="Wafer",
                evidence=evidence,
                index=index,
            )
            _add_relation(
                relation_by_key,
                source_id=source_id,
                scenario=scenario,
                head=wafer_id,
                relation="HAS_ANOMALY",
                tail=pattern_id,
                evidence=evidence,
                index=index,
            )
        zone = _text(row.get("zone") or row.get("location"))
        if zone:
            location_id = _pascal_id(zone)
            _add_entity(
                entity_by_id,
                source_id=source_id,
                scenario=scenario,
                entity_id=location_id,
                name=_display_label(zone),
                label="Location",
                evidence=evidence,
                index=index,
            )
            _add_relation(
                relation_by_key,
                source_id=source_id,
                scenario=scenario,
                head=pattern_id,
                relation="HAS_LOCATION",
                tail=location_id,
                evidence=evidence,
                index=index,
            )
        morphology = _text(row.get("morphology"))
        if morphology:
            morphology_id = _pascal_id(morphology)
            _add_entity(
                entity_by_id,
                source_id=source_id,
                scenario=scenario,
                entity_id=morphology_id,
                name=_display_label(morphology),
                label="Morphology",
                evidence=evidence,
                index=index,
            )
            _add_relation(
                relation_by_key,
                source_id=source_id,
                scenario=scenario,
                head=pattern_id,
                relation="HAS_MORPHOLOGY",
                tail=morphology_id,
                evidence=evidence,
                index=index,
            )
            _add_relation(
                relation_by_key,
                source_id=source_id,
                scenario=scenario,
                head=pattern_id,
                relation="HAS_SPATIAL_SIGNATURE",
                tail=morphology_id,
                evidence=evidence,
                index=index,
            )
    return DraftKG(
        entities=tuple(entity_by_id.values()),
        relations=tuple(relation_by_key.values()),
    )


def _add_entity(
    entity_by_id: dict[str, DraftEntity],
    *,
    source_id: str,
    scenario: str,
    entity_id: str,
    name: str,
    label: str,
    evidence: str,
    index: int,
) -> None:
    if entity_id in entity_by_id:
        return
    entity_by_id[entity_id] = DraftEntity(
        draft_id=f"{source_id}:wafer_record_entity:{index}:{entity_id}",
        source_id=source_id,
        extractor_name=EXTRACTOR_NAME,
        extractor_version=EXTRACTOR_VERSION,
        scenario=scenario,
        entity_id_suggestion=entity_id,
        name=name,
        label=label,
        evidence=evidence,
        confidence=0.82,
        status="draft",
        metadata={"extractor": EXTRACTOR_NAME, "record_index": index},
    )


def _add_relation(
    relation_by_key: dict[tuple[str, str, str], DraftRelation],
    *,
    source_id: str,
    scenario: str,
    head: str,
    relation: str,
    tail: str,
    evidence: str,
    index: int,
) -> None:
    key = (head, relation, tail)
    if key in relation_by_key:
        return
    relation_by_key[key] = DraftRelation(
        draft_id=f"{source_id}:wafer_record_relation:{index}:{head}:{relation}:{tail}",
        source_id=source_id,
        extractor_name=EXTRACTOR_NAME,
        extractor_version=EXTRACTOR_VERSION,
        scenario=scenario,
        head=head,
        relation=relation,
        tail=tail,
        evidence=evidence,
        confidence=0.82,
        status="draft",
        metadata={"extractor": EXTRACTOR_NAME, "record_index": index},
    )


def _text(value: object) -> str:
    return str(value or "").strip()


def _pascal_id(value: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", value)
    return "".join(word[:1].upper() + word[1:] for word in words) or "Unknown"


def _display_label(value: str) -> str:
    return re.sub(r"[_-]+", " ", value).strip().title()
