"""Source-derived MVTec defect taxonomy extraction.

This module turns raw or near-raw MVTec dataset-card material into DraftKG
candidate rows. It deliberately avoids mask/image-derived facts and RCA claims:
all output is grounded in text labels such as the DS-MVTec ``defects_dict``.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from kgtracevis.kg_construction.document_extraction import ParsedSourceDocument
from kgtracevis.kg_construction.draft import DraftEntity, DraftKG, DraftRelation

EXTRACTOR_NAME = "mvtec_source_taxonomy"
EXTRACTOR_VERSION = "v1"

OBJECT_DEFECT_CONFIDENCE = 0.86
DEFECT_OBJECT_SUPPORT_CONFIDENCE = 0.84
DATASET_COMPONENT_CONFIDENCE = 0.82
LABEL_SEMANTIC_CONFIDENCE = 0.74
OBJECT_LABEL_SEMANTIC_CONFIDENCE = 0.68
LABEL_MECHANISM_HYPOTHESIS_CONFIDENCE = 0.42


@dataclass(frozen=True)
class MVTecTaxonomyExtractionSummary:
    """Audit summary for deterministic MVTec taxonomy supplementation."""

    extractor_name: str
    extractor_version: str
    source_id: str
    object_count: int
    object_defect_pair_count: int
    entity_count: int
    relation_count: int
    claim_boundary: str = (
        "MVTec taxonomy supplementation is source-label grounded DraftKG candidate "
        "material. It does not derive verified factory RCA facts and does not publish KG."
    )

    def to_payload(self) -> dict[str, Any]:
        """Return JSON-serializable manifest payload."""
        return {
            "extractor_name": self.extractor_name,
            "extractor_version": self.extractor_version,
            "source_id": self.source_id,
            "object_count": self.object_count,
            "object_defect_pair_count": self.object_defect_pair_count,
            "entity_count": self.entity_count,
            "relation_count": self.relation_count,
            "claim_boundary": self.claim_boundary,
        }


@dataclass(frozen=True)
class MVTecTaxonomyExtractionResult:
    """DraftKG supplement plus its audit summary."""

    draft: DraftKG
    summary: MVTecTaxonomyExtractionSummary | None = None

    @property
    def has_candidates(self) -> bool:
        """Return True when extraction found source-grounded taxonomy rows."""
        return bool(self.draft.entities or self.draft.relations)


_MORPHOLOGY_PHRASES: tuple[tuple[str, str, str], ...] = (
    ("faulty_imprint", "FaultyImprintMorphology", "faulty imprint"),
    ("metal_contamination", "ContaminationMorphology", "metal contamination"),
    ("glue_strip", "GlueResidueMorphology", "glue strip"),
    ("gray_stroke", "StrokeMorphology", "gray stroke"),
    ("broken", "BrokenMorphology", "broken"),
    ("crack", "CrackMorphology", "crack"),
    ("scratch", "ScratchMorphology", "scratch"),
    ("cut", "CutMorphology", "cut"),
    ("hole", "HoleMorphology", "hole"),
    ("contamination", "ContaminationMorphology", "contamination"),
    ("color", "ColorAnomalyMorphology", "color anomaly"),
    ("bent", "BentMorphology", "bent"),
    ("glue", "GlueResidueMorphology", "glue"),
    ("thread", "ThreadAnomalyMorphology", "thread anomaly"),
    ("poke", "PokeMorphology", "poke"),
    ("squeeze", "SqueezeMorphology", "squeeze"),
    ("squeezed", "SqueezeMorphology", "squeezed"),
    ("fold", "FoldMorphology", "fold"),
    ("oil", "OilStainMorphology", "oil stain"),
    ("rough", "RoughTextureMorphology", "rough texture"),
    ("missing", "MissingPartMorphology", "missing part"),
    ("messy", "MessyArrangementMorphology", "messy arrangement"),
    ("manipulated", "ManipulatedMorphology", "manipulated"),
    ("damaged", "DamagedMorphology", "damaged"),
    ("misplaced", "MisplacementMorphology", "misplaced"),
    ("split", "SplitMorphology", "split"),
    ("print", "ImprintAnomalyMorphology", "print anomaly"),
    ("liquid", "LiquidStainMorphology", "liquid stain"),
    ("combined", "CombinedDefectMorphology", "combined defect"),
)

_LOCATION_PHRASES: tuple[tuple[str, str, str], ...] = (
    ("inner_insulation", "InnerInsulationLocation", "inner insulation"),
    ("outer_insulation", "OuterInsulationLocation", "outer insulation"),
    ("cable", "CableBodyLocation", "cable body"),
    ("wire", "WireLocation", "wire"),
    ("front", "FrontLocation", "front"),
    ("head", "HeadLocation", "head"),
    ("neck", "NeckLocation", "neck"),
    ("side", "SideLocation", "side"),
    ("top", "TopLocation", "top"),
    ("lead", "LeadLocation", "lead"),
    ("case", "CaseLocation", "case"),
    ("teeth", "TeethLocation", "teeth"),
    ("fabric_border", "FabricBorderLocation", "fabric border"),
    ("fabric_interior", "FabricInteriorLocation", "fabric interior"),
    ("strip", "StripLocation", "strip"),
    ("stroke", "StrokeLocation", "stroke"),
)

_CAUSE_CATEGORY_PHRASES: tuple[tuple[str, str, str], ...] = (
    ("faulty_imprint", "MarkingOrImprintIssueCause", "marking or imprint issue"),
    ("metal_contamination", "ContaminationOrResidueCause", "contamination or residue"),
    ("glue_strip", "ContaminationOrResidueCause", "contamination or residue"),
    ("gray_stroke", "AppearanceShiftCause", "appearance shift"),
    ("broken", "SurfaceDamageCause", "surface damage"),
    ("crack", "SurfaceDamageCause", "surface damage"),
    ("scratch", "SurfaceDamageCause", "surface damage"),
    ("cut", "SurfaceDamageCause", "surface damage"),
    ("hole", "SurfaceDamageCause", "surface damage"),
    ("poke", "SurfaceDamageCause", "surface damage"),
    ("rough", "SurfaceDamageCause", "surface damage"),
    ("damaged", "SurfaceDamageCause", "surface damage"),
    ("split", "SurfaceDamageCause", "surface damage"),
    ("contamination", "ContaminationOrResidueCause", "contamination or residue"),
    ("oil", "ContaminationOrResidueCause", "contamination or residue"),
    ("liquid", "ContaminationOrResidueCause", "contamination or residue"),
    ("glue", "ContaminationOrResidueCause", "contamination or residue"),
    ("color", "AppearanceShiftCause", "appearance shift"),
    ("bent", "AssemblyOrDeformationCause", "assembly or deformation issue"),
    ("squeeze", "AssemblyOrDeformationCause", "assembly or deformation issue"),
    ("squeezed", "AssemblyOrDeformationCause", "assembly or deformation issue"),
    ("fold", "AssemblyOrDeformationCause", "assembly or deformation issue"),
    ("manipulated", "AssemblyOrDeformationCause", "assembly or deformation issue"),
    ("misplaced", "AssemblyOrDeformationCause", "assembly or deformation issue"),
    ("missing", "AssemblyOrDeformationCause", "assembly or deformation issue"),
    ("cable_swap", "AssemblyOrDeformationCause", "assembly or deformation issue"),
    ("combined", "AssemblyOrDeformationCause", "assembly or deformation issue"),
    ("thread", "TextileOrThreadIssueCause", "textile or thread issue"),
    ("fabric_border", "TextileOrThreadIssueCause", "textile or thread issue"),
    ("fabric_interior", "TextileOrThreadIssueCause", "textile or thread issue"),
    ("print", "MarkingOrImprintIssueCause", "marking or imprint issue"),
)


def extract_mvtec_taxonomy_from_document(
    document: ParsedSourceDocument,
) -> MVTecTaxonomyExtractionResult:
    """Extract source-grounded MVTec object/defect candidates from a document."""
    if document.scenario != "mvtec":
        return MVTecTaxonomyExtractionResult(draft=DraftKG())
    taxonomy = parse_mvtec_defects_dict(document.text)
    if not taxonomy:
        return MVTecTaxonomyExtractionResult(draft=DraftKG())
    draft = draft_from_mvtec_taxonomy(
        taxonomy,
        source_id=document.source_id,
        scenario=document.scenario,
        source_text=document.text,
    )
    summary = MVTecTaxonomyExtractionSummary(
        extractor_name=EXTRACTOR_NAME,
        extractor_version=EXTRACTOR_VERSION,
        source_id=document.source_id,
        object_count=len(taxonomy),
        object_defect_pair_count=sum(len(defects) for defects in taxonomy.values()),
        entity_count=len(draft.entities),
        relation_count=len(draft.relations),
    )
    return MVTecTaxonomyExtractionResult(draft=draft, summary=summary)


def parse_mvtec_defects_dict(text: str) -> dict[str, tuple[str, ...]]:
    """Parse a Python-literal ``defects_dict`` block from source text."""
    literal = _extract_defects_dict_literal(text)
    if not literal:
        return {}
    try:
        value = ast.literal_eval(literal)
    except (SyntaxError, ValueError) as exc:
        raise ValueError("invalid MVTec defects_dict literal") from exc
    if not isinstance(value, dict):
        raise ValueError("MVTec defects_dict must be a dict")
    taxonomy: dict[str, tuple[str, ...]] = {}
    for object_name, defects in value.items():
        object_key = _normalized_label(str(object_name))
        if not object_key:
            continue
        if not isinstance(defects, dict):
            raise ValueError(f"MVTec defects for {object_key} must be a dict")
        defect_labels = tuple(
            _normalized_label(str(defect_name))
            for defect_name in defects
            if _normalized_label(str(defect_name))
        )
        if defect_labels:
            taxonomy[object_key] = defect_labels
    return taxonomy


def draft_from_mvtec_taxonomy(
    taxonomy: Mapping[str, tuple[str, ...]],
    *,
    source_id: str,
    scenario: str,
    source_text: str,
) -> DraftKG:
    """Build DraftKG candidate rows from parsed MVTec object/defect taxonomy."""
    entity_by_id: dict[str, DraftEntity] = {}
    relations: list[DraftRelation] = []

    dataset_evidence = _dataset_evidence(source_text)
    _add_entity(
        entity_by_id,
        DraftEntity(
            draft_id=f"{source_id}:mvtec_taxonomy:entity:MVTecADDataset",
            source_id=source_id,
            extractor_name=EXTRACTOR_NAME,
            extractor_version=EXTRACTOR_VERSION,
            scenario=scenario,
            entity_id_suggestion="MVTecADDataset",
            name="MVTec AD dataset",
            label="Dataset",
            aliases=("MVTec AD", "MAD"),
            description=(
                "MVTec anomaly detection dataset context from source material."
            ),
            evidence=dataset_evidence,
            confidence=DATASET_COMPONENT_CONFIDENCE,
            status="draft",
            metadata=_metadata("dataset_anchor"),
        ),
    )

    relation_index = 0
    object_semantic_relation_keys: set[tuple[str, str, str]] = set()
    for object_name, defect_labels in taxonomy.items():
        object_id = f"{_pascal_case(object_name)}Object"
        object_evidence = _line_evidence_for_object(source_text, object_name)
        _add_entity(
            entity_by_id,
            DraftEntity(
                draft_id=f"{source_id}:mvtec_taxonomy:entity:{object_id}",
                source_id=source_id,
                extractor_name=EXTRACTOR_NAME,
                extractor_version=EXTRACTOR_VERSION,
                scenario=scenario,
                entity_id_suggestion=object_id,
                name=_display_name(object_name),
                label="Object",
                aliases=(object_name,),
                description=f"MVTec object category: {_display_name(object_name)}.",
                evidence=object_evidence,
                confidence=DATASET_COMPONENT_CONFIDENCE,
                status="draft",
                metadata=_metadata("object_category"),
            ),
        )
        relation_index += 1
        relations.append(
            DraftRelation(
                draft_id=f"{source_id}:mvtec_taxonomy:relation:{relation_index}",
                source_id=source_id,
                extractor_name=EXTRACTOR_NAME,
                extractor_version=EXTRACTOR_VERSION,
                scenario=scenario,
                head="MVTecADDataset",
                relation="HAS_COMPONENT",
                tail=object_id,
                evidence=object_evidence,
                confidence=DATASET_COMPONENT_CONFIDENCE,
                status="draft",
                metadata=_metadata("dataset_object_membership", "PART_OF"),
            )
        )
        for defect_label in defect_labels:
            defect_id = f"{_pascal_case(defect_label)}Defect"
            defect_evidence = _defect_evidence(object_name, defect_label, object_evidence)
            _add_entity(
                entity_by_id,
                DraftEntity(
                    draft_id=f"{source_id}:mvtec_taxonomy:entity:{defect_id}",
                    source_id=source_id,
                    extractor_name=EXTRACTOR_NAME,
                    extractor_version=EXTRACTOR_VERSION,
                    scenario=scenario,
                    entity_id_suggestion=defect_id,
                    name=f"{_display_name(defect_label)} defect",
                    label="Defect",
                    aliases=(defect_label, _display_name(defect_label)),
                    description=(
                        "MVTec defect label candidate extracted from source taxonomy."
                    ),
                    evidence=defect_evidence,
                    confidence=OBJECT_DEFECT_CONFIDENCE,
                    status="draft",
                    metadata=_metadata("defect_label"),
                ),
            )
            relation_index += 1
            relations.append(
                DraftRelation(
                    draft_id=f"{source_id}:mvtec_taxonomy:relation:{relation_index}",
                    source_id=source_id,
                    extractor_name=EXTRACTOR_NAME,
                    extractor_version=EXTRACTOR_VERSION,
                    scenario=scenario,
                    head=object_id,
                    relation="HAS_ANOMALY",
                    tail=defect_id,
                    evidence=defect_evidence,
                    confidence=OBJECT_DEFECT_CONFIDENCE,
                    status="draft",
                    metadata=_metadata("object_defect_taxonomy", "OBSERVATION"),
                )
            )
            relation_index += 1
            relations.append(
                DraftRelation(
                    draft_id=f"{source_id}:mvtec_taxonomy:relation:{relation_index}",
                    source_id=source_id,
                    extractor_name=EXTRACTOR_NAME,
                    extractor_version=EXTRACTOR_VERSION,
                    scenario=scenario,
                    head=defect_id,
                    relation="BELONGS_TO",
                    tail=object_id,
                    evidence=defect_evidence,
                    confidence=DEFECT_OBJECT_SUPPORT_CONFIDENCE,
                    status="draft",
                    metadata=_metadata("defect_object_taxonomy", "SEMANTIC_SUPPORT"),
                )
            )
            relation_index = _add_object_label_semantic_relations(
                object_id=object_id,
                defect_label=defect_label,
                defect_evidence=defect_evidence,
                source_id=source_id,
                scenario=scenario,
                relations=relations,
                relation_index=relation_index,
                relation_keys=object_semantic_relation_keys,
            )
            relation_index = _add_label_semantic_relations(
                defect_id=defect_id,
                defect_label=defect_label,
                defect_evidence=defect_evidence,
                source_id=source_id,
                scenario=scenario,
                entity_by_id=entity_by_id,
                relations=relations,
                relation_index=relation_index,
            )
            relation_index = _add_label_mechanism_hypotheses(
                defect_id=defect_id,
                defect_label=defect_label,
                defect_evidence=defect_evidence,
                source_id=source_id,
                scenario=scenario,
                entity_by_id=entity_by_id,
                relations=relations,
                relation_index=relation_index,
            )

    return DraftKG(entities=tuple(entity_by_id.values()), relations=tuple(relations))


def _add_object_label_semantic_relations(
    *,
    object_id: str,
    defect_label: str,
    defect_evidence: str,
    source_id: str,
    scenario: str,
    relations: list[DraftRelation],
    relation_index: int,
    relation_keys: set[tuple[str, str, str]],
) -> int:
    for _, morphology_id, _ in _matches(defect_label, _MORPHOLOGY_PHRASES):
        relation_index = _append_once(
            relations,
            relation_keys,
            relation_index=relation_index,
            source_id=source_id,
            scenario=scenario,
            head=object_id,
            relation="HAS_MORPHOLOGY",
            tail=morphology_id,
            evidence=defect_evidence,
            confidence=OBJECT_LABEL_SEMANTIC_CONFIDENCE,
            evidence_role="object_label_morphology",
        )
    for _, location_id, _ in _matches(defect_label, _LOCATION_PHRASES):
        relation_index = _append_once(
            relations,
            relation_keys,
            relation_index=relation_index,
            source_id=source_id,
            scenario=scenario,
            head=object_id,
            relation="HAS_LOCATION",
            tail=location_id,
            evidence=defect_evidence,
            confidence=OBJECT_LABEL_SEMANTIC_CONFIDENCE,
            evidence_role="object_label_location",
        )
    return relation_index


def _add_label_semantic_relations(
    *,
    defect_id: str,
    defect_label: str,
    defect_evidence: str,
    source_id: str,
    scenario: str,
    entity_by_id: dict[str, DraftEntity],
    relations: list[DraftRelation],
    relation_index: int,
) -> int:
    for phrase, morphology_id, morphology_name in _matches(defect_label, _MORPHOLOGY_PHRASES):
        _add_entity(
            entity_by_id,
            DraftEntity(
                draft_id=f"{source_id}:mvtec_taxonomy:entity:{morphology_id}",
                source_id=source_id,
                extractor_name=EXTRACTOR_NAME,
                extractor_version=EXTRACTOR_VERSION,
                scenario=scenario,
                entity_id_suggestion=morphology_id,
                name=morphology_name,
                label="Morphology",
                aliases=(phrase.replace("_", " "),),
                description="Visual defect morphology inferred from the defect label text.",
                evidence=defect_evidence,
                confidence=LABEL_SEMANTIC_CONFIDENCE,
                status="draft",
                metadata=_metadata("defect_label_morphology"),
            ),
        )
        relation_index += 1
        relations.append(
            DraftRelation(
                draft_id=f"{source_id}:mvtec_taxonomy:relation:{relation_index}",
                source_id=source_id,
                extractor_name=EXTRACTOR_NAME,
                extractor_version=EXTRACTOR_VERSION,
                scenario=scenario,
                head=defect_id,
                relation="HAS_MORPHOLOGY",
                tail=morphology_id,
                evidence=defect_evidence,
                confidence=LABEL_SEMANTIC_CONFIDENCE,
                status="draft",
                metadata=_metadata("defect_label_morphology", "SEMANTIC_SUPPORT"),
            )
        )
    for phrase, location_id, location_name in _matches(defect_label, _LOCATION_PHRASES):
        _add_entity(
            entity_by_id,
            DraftEntity(
                draft_id=f"{source_id}:mvtec_taxonomy:entity:{location_id}",
                source_id=source_id,
                extractor_name=EXTRACTOR_NAME,
                extractor_version=EXTRACTOR_VERSION,
                scenario=scenario,
                entity_id_suggestion=location_id,
                name=location_name,
                label="Location",
                aliases=(phrase.replace("_", " "),),
                description="Visual defect location inferred from the defect label text.",
                evidence=defect_evidence,
                confidence=LABEL_SEMANTIC_CONFIDENCE,
                status="draft",
                metadata=_metadata("defect_label_location"),
            ),
        )
        relation_index += 1
        relations.append(
            DraftRelation(
                draft_id=f"{source_id}:mvtec_taxonomy:relation:{relation_index}",
                source_id=source_id,
                extractor_name=EXTRACTOR_NAME,
                extractor_version=EXTRACTOR_VERSION,
                scenario=scenario,
                head=defect_id,
                relation="OCCURS_ON",
                tail=location_id,
                evidence=defect_evidence,
                confidence=LABEL_SEMANTIC_CONFIDENCE,
                status="draft",
                metadata=_metadata("defect_label_location", "SEMANTIC_SUPPORT"),
            )
        )
    return relation_index


def _add_label_mechanism_hypotheses(
    *,
    defect_id: str,
    defect_label: str,
    defect_evidence: str,
    source_id: str,
    scenario: str,
    entity_by_id: dict[str, DraftEntity],
    relations: list[DraftRelation],
    relation_index: int,
) -> int:
    for phrase, cause_id, cause_name in _matches(defect_label, _CAUSE_CATEGORY_PHRASES):
        _add_entity(
            entity_by_id,
            DraftEntity(
                draft_id=f"{source_id}:mvtec_taxonomy:entity:{cause_id}",
                source_id=source_id,
                extractor_name=EXTRACTOR_NAME,
                extractor_version=EXTRACTOR_VERSION,
                scenario=scenario,
                entity_id_suggestion=cause_id,
                name=cause_name,
                label="CauseCategory",
                aliases=(phrase.replace("_", " "),),
                description=(
                    "Review-only plausible visual mechanism category inferred from "
                    "the defect label text; not a verified MVTec root cause."
                ),
                evidence=defect_evidence,
                confidence=LABEL_MECHANISM_HYPOTHESIS_CONFIDENCE,
                status="draft",
                metadata=_metadata("defect_label_mechanism_hypothesis"),
            ),
        )
        relation_index += 1
        relations.append(
            DraftRelation(
                draft_id=f"{source_id}:mvtec_taxonomy:relation:{relation_index}",
                source_id=source_id,
                extractor_name=EXTRACTOR_NAME,
                extractor_version=EXTRACTOR_VERSION,
                scenario=scenario,
                head=defect_id,
                relation="HAS_PLAUSIBLE_CAUSE",
                tail=cause_id,
                evidence=(
                    f"{defect_evidence} | review-only label-derived mechanism "
                    "hypothesis; missing factory/process evidence"
                ),
                confidence=LABEL_MECHANISM_HYPOTHESIS_CONFIDENCE,
                status="draft",
                metadata={
                    **_metadata("defect_label_mechanism_hypothesis", "CAUSES"),
                    "hypothesis_only": True,
                    "missing_evidence": "factory process logs; reviewed causal annotation",
                },
            )
        )
    return relation_index


def _extract_defects_dict_literal(text: str) -> str:
    match = re.search(r"\bdefects_dict\s*=", text)
    if not match:
        return ""
    start = text.find("{", match.end())
    if start < 0:
        return ""
    depth = 0
    quote = ""
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            continue
        if char in {"'", '"'}:
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise ValueError("unterminated MVTec defects_dict literal")


def _matches(
    defect_label: str,
    phrase_map: tuple[tuple[str, str, str], ...],
) -> tuple[tuple[str, str, str], ...]:
    matches: list[tuple[str, str, str]] = []
    padded = f"_{defect_label}_"
    for phrase, entity_id, name in phrase_map:
        if f"_{phrase}_" in padded:
            matches.append((phrase, entity_id, name))
    return tuple(matches)


def _line_evidence_for_object(source_text: str, object_name: str) -> str:
    needle = f'"{object_name}"'
    fallback = object_name
    for line in source_text.splitlines():
        if needle in line or f"'{object_name}'" in line:
            return line.strip()
    return fallback


def _defect_evidence(object_name: str, defect_label: str, object_evidence: str) -> str:
    if defect_label in object_evidence:
        return object_evidence
    return f"{object_name}: {defect_label}"


def _dataset_evidence(source_text: str) -> str:
    for line in source_text.splitlines():
        stripped = line.strip()
        if "MVTec" in stripped or "defect classes" in stripped:
            return stripped[:500]
    return "MVTec defect taxonomy source material"


def _add_entity(entity_by_id: dict[str, DraftEntity], entity: DraftEntity) -> None:
    entity_by_id.setdefault(entity.entity_id_suggestion, entity)


def _append_once(
    relations: list[DraftRelation],
    relation_keys: set[tuple[str, str, str]],
    *,
    relation_index: int,
    source_id: str,
    scenario: str,
    head: str,
    relation: str,
    tail: str,
    evidence: str,
    confidence: float,
    evidence_role: str,
) -> int:
    key = (head, relation, tail)
    if key in relation_keys:
        return relation_index
    relation_keys.add(key)
    relation_index += 1
    relations.append(
        DraftRelation(
            draft_id=f"{source_id}:mvtec_taxonomy:relation:{relation_index}",
            source_id=source_id,
            extractor_name=EXTRACTOR_NAME,
            extractor_version=EXTRACTOR_VERSION,
            scenario=scenario,
            head=head,
            relation=relation,
            tail=tail,
            evidence=evidence,
            confidence=confidence,
            status="draft",
            metadata=_metadata(evidence_role, "SEMANTIC_SUPPORT"),
        )
    )
    return relation_index


def _metadata(evidence_role: str, relation_family: str = "") -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "evidence_role": evidence_role,
        "source_grounding": "text_label",
        "rca_claim": False,
    }
    if relation_family:
        metadata["relation_family"] = relation_family
    return metadata


def _normalized_label(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", value.strip().lower()).strip("_")


def _pascal_case(value: str) -> str:
    return "".join(part.capitalize() for part in _normalized_label(value).split("_") if part)


def _display_name(value: str) -> str:
    return " ".join(part for part in _normalized_label(value).split("_") if part).title()
