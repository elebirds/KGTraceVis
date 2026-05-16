"""Tests for source-derived MVTec taxonomy DraftKG supplementation."""
# ruff: noqa: E501

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from kgtracevis.kg_construction.document_extraction import ParsedSourceDocument
from kgtracevis.kg_construction.mvtec_taxonomy_extraction import (
    draft_from_mvtec_taxonomy,
    extract_mvtec_taxonomy_from_document,
    parse_mvtec_defects_dict,
)
from kgtracevis.service.kg_materials import (
    KGMaterialExtractionRunRequest,
    extract_kg_material_to_structured_records,
    save_kg_material_upload,
)

FULL_DEFECTS_DICT_TEXT = """
# DS-MVTec
## defect classes
    defects_dict = {
        "bottle": {'broken_large': 1, 'broken_small': 2, 'contamination': 3},
        "cable": {'bent_wire': 1, 'cable_swap': 2, 'combined': 3, 'cut_inner_insulation': 4, 'cut_outer_insulation': 5, 'missing_cable': 6, 'missing_wire': 7, 'poke_insulation': 8},
        "capsule": {'crack': 1, 'poke': 2, 'faulty_imprint': 3, 'scratch': 4, 'squeeze': 5},
        "carpet": {'color': 1, 'cut': 2, 'hole': 3, 'metal_contamination': 4, 'thread': 5},
        "grid": {'bent': 1, 'broken': 2, 'glue': 3, 'metal_contamination': 4, 'thread': 5},
        "hazelnut": {'cut': 1, 'crack': 2, 'hole': 3, 'print': 4},
        "leather": {'color': 1, 'cut': 2, 'fold': 3, 'glue': 4, 'poke': 5},
        "metal_nut": {'scratch': 1, 'bent': 2, 'color': 3},
        "pill": {'color': 1, 'contamination': 2, 'crack': 3, 'faulty_imprint': 4, 'scratch':5, 'pill_type': 6},
        "screw": {'manipulated_front': 1, 'scratch_head': 2, 'scratch_neck': 3, 'thread_side': 4, 'thread_top': 5},
        "tile": {'crack': 1, 'glue_strip': 2, 'gray_stroke': 3, 'oil': 4, 'rough': 5},
        "toothbrush": {'contamination': 1, 'missing':2, 'messy':3},
        "transistor": {'bent_lead': 1, 'cut_lead': 2, 'damaged_case': 3, 'misplaced': 4},
        "wood": {'color': 1, 'crack': 2, 'scratch': 3, 'hole': 4, 'liquid': 5},
        "zipper": {'broken_teeth': 1, 'fabric_border': 2, 'fabric_interior': 3, 'split_teeth': 4, 'squeezed_teeth': 5}
    }
"""


def test_parse_mvtec_defects_dict_extracts_full_taxonomy() -> None:
    """DS-MVTec source text should expose all object/defect label pairs."""
    taxonomy = parse_mvtec_defects_dict(FULL_DEFECTS_DICT_TEXT)

    assert len(taxonomy) == 15
    assert sum(len(defects) for defects in taxonomy.values()) == 71
    assert taxonomy["bottle"] == ("broken_large", "broken_small", "contamination")
    assert "scratch_head" in taxonomy["screw"]


def test_draft_from_mvtec_taxonomy_adds_source_grounded_semantic_edges() -> None:
    """Text-label taxonomy should become reviewable DraftKG, not RCA facts."""
    taxonomy = parse_mvtec_defects_dict(
        """
        defects_dict = {
            "bottle": {'broken_large': 1},
            "screw": {'scratch_head': 1}
        }
        """
    )

    draft = draft_from_mvtec_taxonomy(
        taxonomy,
        source_id="ds_mvtec_dataset_card",
        scenario="mvtec",
        source_text=FULL_DEFECTS_DICT_TEXT,
    )

    entity_ids = {entity.entity_id_suggestion for entity in draft.entities}
    relation_keys = {
        (relation.head, relation.relation, relation.tail) for relation in draft.relations
    }
    root_cause_relations = {
        relation.relation
        for relation in draft.relations
        if relation.relation == "SUGGESTS_ROOT_CAUSE"
    }
    plausible_cause_edges = [
        relation
        for relation in draft.relations
        if relation.relation == "HAS_PLAUSIBLE_CAUSE"
    ]

    assert "MVTecADDataset" in entity_ids
    assert "BottleObject" in entity_ids
    assert "BrokenLargeDefect" in entity_ids
    assert "ScratchMorphology" in entity_ids
    assert "HeadLocation" in entity_ids
    assert ("BottleObject", "HAS_ANOMALY", "BrokenLargeDefect") in relation_keys
    assert ("BrokenLargeDefect", "BELONGS_TO", "BottleObject") in relation_keys
    assert ("ScrewObject", "HAS_MORPHOLOGY", "ScratchMorphology") in relation_keys
    assert ("ScrewObject", "HAS_LOCATION", "HeadLocation") in relation_keys
    assert ("ScratchHeadDefect", "HAS_MORPHOLOGY", "ScratchMorphology") in relation_keys
    assert ("ScratchHeadDefect", "OCCURS_ON", "HeadLocation") in relation_keys
    assert ("ScratchHeadDefect", "HAS_PLAUSIBLE_CAUSE", "SurfaceDamageCause") in relation_keys
    assert plausible_cause_edges
    assert all(edge.confidence < 0.5 for edge in plausible_cause_edges)
    assert all(edge.metadata.get("hypothesis_only") for edge in plausible_cause_edges)
    assert not root_cause_relations


def test_extract_mvtec_taxonomy_from_document_records_manifest_summary() -> None:
    """The material path supplement should be manifest-recordable and optional."""
    document = ParsedSourceDocument(
        source_id="ds_mvtec_dataset_card",
        source_type="markdown",
        scenario="mvtec",
        text=FULL_DEFECTS_DICT_TEXT,
        parser="markdown",
    )

    result = extract_mvtec_taxonomy_from_document(document)

    assert result.has_candidates
    assert result.summary is not None
    assert result.summary.to_payload()["object_count"] == 15
    assert result.summary.to_payload()["object_defect_pair_count"] == 71
    assert result.summary.to_payload()["entity_count"] == len(result.draft.entities)


def test_material_extraction_merges_mvtec_taxonomy_supplement(tmp_path: Path) -> None:
    """MVTec material extraction should carry taxonomy candidates into records."""
    save_kg_material_upload(
        material_id="ds_mvtec_dataset_card",
        title="DS-MVTec dataset card",
        filename="DS-MVTec.md",
        content=FULL_DEFECTS_DICT_TEXT.encode(),
        scenario="mvtec",
        material_type="markdown",
        material_root=tmp_path,
    )

    response = extract_kg_material_to_structured_records(
        "ds_mvtec_dataset_card",
        KGMaterialExtractionRunRequest(overwrite=True),
        client=_EmptyIEClient(),
        material_root=tmp_path,
    )

    assert response.structured_records_path is not None
    assert response.extraction_manifest_path is not None
    records_path = Path(response.structured_records_path)
    manifest_path = Path(response.extraction_manifest_path)
    records = [
        json.loads(line)
        for line in records_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )
    relation_keys = {
        (record.get("head"), record.get("relation"), record.get("tail"))
        for record in records
        if record.get("record_type") == "relation"
    }

    assert response.record_count > 250
    assert ("BottleObject", "HAS_ANOMALY", "BrokenLargeDefect") in relation_keys
    assert ("BrokenLargeDefect", "BELONGS_TO", "BottleObject") in relation_keys
    assert manifest["extraction"]["candidate_augmentations"][0]["object_count"] == 15


class _EmptyIEClient:
    """No-op IE client so the test isolates deterministic supplementation."""

    def extract_candidates(
        self,
        chunk: Any,
        *,
        prompt: str,
        response_schema: dict[str, Any],
    ) -> dict[str, list[Any]]:
        del chunk, prompt, response_schema
        return {"entities": [], "relations": []}
