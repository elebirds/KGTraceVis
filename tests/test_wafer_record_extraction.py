"""Tests for source-derived wafer evidence record extraction."""

from __future__ import annotations

from kgtracevis.kg_construction.document_extraction import ParsedSourceDocument
from kgtracevis.kg_construction.wafer_record_extraction import (
    extract_wafer_records_from_document,
    parse_wafer_evidence_records,
)


def test_parse_wafer_evidence_records_reads_pattern_rows() -> None:
    """JSONL wafer evidence rows expose pattern-bearing source records."""
    rows = parse_wafer_evidence_records(
        '{"case_id":"c1","failure_pattern":"Near-full","zone":"wafer_surface"}\n'
        '{"case_id":"c2","score":0.5}\n'
    )

    assert len(rows) == 1
    assert rows[0]["failure_pattern"] == "Near-full"


def test_extract_wafer_records_produces_spatial_candidates_only() -> None:
    """Explicit pattern/location/morphology fields become reviewable DraftKG rows."""
    document = ParsedSourceDocument(
        source_id="wm811k_records",
        source_type="plain_text",
        scenario="wafer",
        text=(
            '{"dataset":"wafer","case_id":"c1","wafer_id":"W811K-0001",'
            '"failure_pattern":"Near-full","zone":"wafer_surface",'
            '"morphology":"dense_particles"}\n'
        ),
        parser="text",
    )

    result = extract_wafer_records_from_document(document)

    assert result.has_candidates is True
    assert result.summary is not None
    assert result.summary.claim_boundary.startswith("Wafer record supplementation")
    entity_ids = {entity.entity_id_suggestion for entity in result.draft.entities}
    relation_keys = {
        (relation.head, relation.relation, relation.tail)
        for relation in result.draft.relations
    }
    assert {"NearFullPattern", "WaferSurface", "DenseParticles", "W811K0001"} <= entity_ids
    assert ("NearFullPattern", "HAS_LOCATION", "WaferSurface") in relation_keys
    assert ("NearFullPattern", "HAS_MORPHOLOGY", "DenseParticles") in relation_keys
    assert ("NearFullPattern", "HAS_SPATIAL_SIGNATURE", "DenseParticles") in relation_keys
    assert all(
        relation.relation not in {"CAUSES", "HAS_PLAUSIBLE_CAUSE", "SUGGESTS_ROOT_CAUSE"}
        for relation in result.draft.relations
    )
