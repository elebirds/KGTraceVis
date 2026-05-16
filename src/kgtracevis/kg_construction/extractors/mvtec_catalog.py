"""MVTec AD catalog extractor for RCA-oriented candidate KG construction."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from kgtracevis.kg_construction.draft import (
    DraftEntity,
    DraftKG,
    DraftRelation,
    KGConstructionSource,
)
from kgtracevis.kg_construction.parsers import ParsedSourceContent
from kgtracevis.kg_construction.source_loader import load_structured_records

CLAIM_BOUNDARY = "candidate/plausible explanation only; not a verified root-cause label"

MORPHOLOGY_NODES: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "linear": ("LinearMorphology", "Linear morphology", ("linear", "line", "line-shaped")),
    "spot": ("SpotMorphology", "Spot morphology", ("spot", "localized spot")),
    "scattered": ("ScatteredMorphology", "Scattered morphology", ("scattered", "diffuse")),
}

MECHANISM_NODES: dict[str, tuple[str, str, str, tuple[str, ...]]] = {
    "MechanicalContact": (
        "Mechanical contact",
        "RootCause",
        "Plausible contact-related candidate mechanism",
        ("mechanical contact", "contact damage"),
    ),
    "HandlingDamage": (
        "Handling damage",
        "RootCause",
        "Plausible handling or transport damage category",
        ("handling", "handling damage"),
    ),
    "AssemblyError": (
        "Assembly error",
        "RootCause",
        "Plausible assembly or placement issue",
        ("assembly error", "misassembly"),
    ),
    "MaterialDefect": (
        "Material defect",
        "RootCause",
        "Plausible material-quality candidate mechanism",
        ("material defect", "material issue"),
    ),
    "ContaminationCause": (
        "Contamination cause",
        "RootCause",
        "Plausible foreign material or residue candidate",
        ("contamination source", "foreign material"),
    ),
    "MissingComponent": (
        "Missing component",
        "RootCause",
        "Plausible missing-part candidate mechanism",
        ("missing component", "missing part"),
    ),
    "ComponentDamage": (
        "Component damage",
        "RootCause",
        "Low-confidence candidate for damaged component evidence",
        ("component damage", "damaged part"),
    ),
    "ProcessMisalignment": (
        "Process misalignment",
        "RootCause",
        "Plausible alignment or positioning candidate mechanism",
        ("process misalignment", "misalignment"),
    ),
    "PackagingPressure": (
        "Packaging pressure",
        "RootCause",
        "Plausible compression or packaging-pressure candidate mechanism",
        ("packaging pressure", "compression damage"),
    ),
    "SurfaceWear": (
        "Surface wear",
        "RootCause",
        "Plausible surface wear or abrasion candidate mechanism",
        ("surface wear", "abrasion"),
    ),
    "AdhesiveOrResidue": (
        "Adhesive or residue",
        "RootCause",
        "Low-confidence candidate for glue, residue, or surface deposit evidence",
        ("adhesive residue", "glue residue", "residue"),
    ),
    "TextureIrregularity": (
        "Texture irregularity",
        "RootCause",
        "Low-confidence candidate for irregular texture or appearance evidence",
        ("texture irregularity", "texture issue"),
    ),
    "GenericVisualDefectMechanism": (
        "Generic visual defect mechanism",
        "RootCause",
        "Fallback candidate when only visual defect semantics are available",
        ("visual defect mechanism", "generic visual mechanism"),
    ),
    "CableInsulationDamage": (
        "Cable insulation damage",
        "RootCause",
        "Object-specific candidate for cable insulation cuts, pokes, or exposed wires",
        ("cable insulation damage", "wire insulation issue"),
    ),
    "CableAssemblyOmission": (
        "Cable assembly omission",
        "RootCause",
        "Object-specific candidate for missing cable or missing wire evidence",
        ("cable assembly omission", "missing wire assembly"),
    ),
    "ZipperTeethAssembly": (
        "Zipper teeth assembly",
        "RootCause",
        "Object-specific candidate for broken, split, or squeezed zipper teeth evidence",
        ("zipper teeth assembly", "zipper teeth defect"),
    ),
    "BottleBreakage": (
        "Bottle breakage",
        "RootCause",
        "Object-specific candidate for large or small broken bottle evidence",
        ("bottle breakage", "bottle fracture"),
    ),
    "CapsuleShellDamage": (
        "Capsule shell damage",
        "RootCause",
        "Object-specific candidate for capsule crack, poke, scratch, or squeeze evidence",
        ("capsule shell damage", "capsule deformation"),
    ),
    "MetalNutSurfaceHandling": (
        "Metal nut surface handling",
        "RootCause",
        "Object-specific candidate for metal-nut surface scratch, color, or bent evidence",
        ("metal nut surface handling", "metal nut surface issue"),
    ),
    "ScrewThreadOrHeadDamage": (
        "Screw thread or head damage",
        "RootCause",
        "Object-specific candidate for screw thread, neck, or head evidence",
        ("screw thread damage", "screw head damage"),
    ),
    "PillCoatingOrHandling": (
        "Pill coating or handling",
        "RootCause",
        "Object-specific candidate for pill contamination, color, crack, or scratch evidence",
        ("pill coating issue", "pill handling damage"),
    ),
    "TextureSurfaceContamination": (
        "Texture surface contamination",
        "RootCause",
        "Object-specific candidate for texture surface color, glue, oil, or contamination evidence",
        ("texture surface contamination", "surface residue"),
    ),
    "TransistorLeadAssembly": (
        "Transistor lead assembly",
        "RootCause",
        "Object-specific candidate for bent, cut, misplaced, or damaged transistor parts",
        ("transistor lead assembly", "transistor placement issue"),
    ),
}

OBJECT_SPECIFIC_MVTEC_MECHANISMS = {
    "CableInsulationDamage",
    "CableAssemblyOmission",
    "ZipperTeethAssembly",
    "BottleBreakage",
    "CapsuleShellDamage",
    "MetalNutSurfaceHandling",
    "ScrewThreadOrHeadDamage",
    "PillCoatingOrHandling",
    "TextureSurfaceContamination",
    "TransistorLeadAssembly",
}


class MVTecCatalogExtractor:
    """Extract candidate KG rows from MVTec AD catalog CSV rows."""

    name = "mvtec_catalog"
    version = "v1"
    supported_source_types: tuple[str, ...] = ("mvtec_ad_catalog",)

    def extract(self, source: KGConstructionSource) -> DraftKG:
        """Extract draft KG rows from a catalog CSV/JSON/JSONL path."""
        if source.path is None:
            raise ValueError("mvtec_ad_catalog extraction requires source.path")
        return self._extract_rows(
            load_structured_records(source.path),
            source=source,
            evidence_reference=str(source.path),
        )

    def extract_from_parsed(
        self,
        parsed: ParsedSourceContent,
        *,
        source: KGConstructionSource,
    ) -> DraftKG:
        """Extract draft KG rows from parser output rows."""
        if parsed.kind != "rows":
            raise ValueError(f"mvtec_ad_catalog requires row parser output: {parsed.source_id}")
        return self._extract_rows(
            parsed.rows,
            source=source,
            evidence_reference=parsed.source_reference or source.source_id,
        )

    def _extract_rows(
        self,
        rows: Sequence[Mapping[str, Any]],
        *,
        source: KGConstructionSource,
        evidence_reference: str,
    ) -> DraftKG:
        entities: dict[str, DraftEntity] = {}
        relations: dict[tuple[str, str, str], DraftRelation] = {}
        for index, row in enumerate(rows, start=1):
            normalized = {str(key): value for key, value in row.items()}
            category = _required_text(normalized, "category_folder", index=index)
            defect = _required_text(normalized, "defect_folder", index=index)
            object_id = f"{_pascal(category)}Object"
            object_name = _humanize(normalized.get("category_label") or category)
            defect_name = _humanize(normalized.get("defect_official_name") or defect)
            defect_id = f"{_pascal(category)}{_pascal(defect)}Defect"
            row_evidence = _row_evidence(
                normalized,
                evidence_reference=evidence_reference,
                index=index,
            )

            _add_entity(
                entities,
                source=source,
                entity_id=object_id,
                name=object_name,
                label="Object",
                aliases=(category, object_name.lower()),
                description="MVTec AD object/category from catalog source",
                evidence=row_evidence,
                confidence=0.9,
                row_index=index,
            )
            _add_entity(
                entities,
                source=source,
                entity_id=defect_id,
                name=f"{object_name} {defect_name.lower()} defect",
                label="AnomalyType",
                aliases=_defect_aliases(category, defect, object_name, defect_name),
                description="MVTec AD official defect type from catalog source",
                evidence=row_evidence,
                confidence=0.9,
                row_index=index,
            )
            _add_relation(
                relations,
                source=source,
                head=object_id,
                relation="HAS_ANOMALY",
                tail=defect_id,
                evidence=(
                    f"MVTec AD catalog row {index} lists category '{category}' "
                    f"with official defect folder '{defect}'."
                ),
                confidence=0.84,
                row_index=index,
                relation_family="OBSERVATION",
            )

            top_class = _text(normalized.get("top_level_anomaly_class"))
            if top_class:
                class_id = f"{_pascal(top_class)}Type"
                _add_entity(
                    entities,
                    source=source,
                    entity_id=class_id,
                    name=_humanize(top_class),
                    label="DefectType",
                    aliases=(top_class, _humanize(top_class).lower()),
                    description="Semantic defect class associated with MVTec catalog rows",
                    evidence=row_evidence,
                    confidence=0.76,
                    row_index=index,
                )
                _add_relation(
                    relations,
                    source=source,
                    head=defect_id,
                    relation="BELONGS_TO",
                    tail=class_id,
                    evidence=(
                        f"MVTec AD catalog row {index} maps defect '{defect}' "
                        f"to top-level anomaly class '{top_class}'."
                    ),
                    confidence=0.76,
                    row_index=index,
                    relation_family="SEMANTIC_SUPPORT",
                )

            morphology = _infer_mvtec_morphology(defect)
            morphology_id, morphology_name, morphology_aliases = MORPHOLOGY_NODES[morphology]
            _add_entity(
                entities,
                source=source,
                entity_id=morphology_id,
                name=morphology_name,
                label="Morphology",
                aliases=morphology_aliases,
                description="Visual morphology used for MVTec evidence normalization",
                evidence=row_evidence,
                confidence=0.72,
                row_index=index,
            )
            _add_relation(
                relations,
                source=source,
                head=defect_id,
                relation="HAS_MORPHOLOGY",
                tail=morphology_id,
                evidence=(
                    f"Catalog defect label '{defect}' is deterministically mapped "
                    f"to {morphology_name}; {CLAIM_BOUNDARY}."
                ),
                confidence=0.72,
                row_index=index,
                relation_family="SEMANTIC_SUPPORT",
            )

            _add_entity(
                entities,
                source=source,
                entity_id="SurfaceLocation",
                name="Surface location",
                label="Location",
                aliases=("surface", "outer surface"),
                description="Default visual anomaly location for MVTec surface inspection",
                evidence=row_evidence,
                confidence=0.7,
                row_index=index,
            )
            _add_relation(
                relations,
                source=source,
                head=defect_id,
                relation="OCCURS_ON",
                tail="SurfaceLocation",
                evidence=(
                    "MVTec AD provides object and texture inspection images with "
                    f"pixel-level anomaly regions; row {index} is treated as a "
                    f"surface-inspection defect candidate. {CLAIM_BOUNDARY}."
                ),
                confidence=0.7,
                row_index=index,
                relation_family="SEMANTIC_SUPPORT",
            )

            mechanism_ids = (
                *_mvtec_mechanisms(defect),
                *_mvtec_object_mechanisms(object_id, defect),
            )
            for mechanism_id in mechanism_ids:
                mechanism_name, label, description, aliases = MECHANISM_NODES[mechanism_id]
                confidence = _mvtec_mechanism_confidence(mechanism_id)
                _add_entity(
                    entities,
                    source=source,
                    entity_id=mechanism_id,
                    name=mechanism_name,
                    label=label,
                    aliases=aliases,
                    description=description,
                    evidence=row_evidence,
                    confidence=confidence,
                    row_index=index,
                )
                _add_relation(
                    relations,
                    source=source,
                    head=defect_id,
                    relation="HAS_PLAUSIBLE_CAUSE",
                    tail=mechanism_id,
                    evidence=_mvtec_mechanism_evidence(defect, mechanism_id, object_id=object_id),
                    confidence=confidence,
                    row_index=index,
                    relation_family="CAUSES",
                )

        return DraftKG(
            entities=tuple(sorted(entities.values(), key=lambda item: item.entity_id_suggestion)),
            relations=tuple(sorted(relations.values(), key=lambda item: item.draft_id)),
        )


def _add_entity(
    entities: dict[str, DraftEntity],
    *,
    source: KGConstructionSource,
    entity_id: str,
    name: str,
    label: str,
    aliases: Sequence[str],
    description: str,
    evidence: str,
    confidence: float,
    row_index: int,
) -> None:
    if entity_id in entities:
        return
    entities[entity_id] = DraftEntity(
        draft_id=f"{source.source_id}:entity:{entity_id}",
        source_id=source.source_id,
        extractor_name=MVTecCatalogExtractor.name,
        extractor_version=MVTecCatalogExtractor.version,
        scenario=source.scenario or "mvtec",
        entity_id_suggestion=entity_id,
        name=name,
        label=label,
        aliases=tuple(dict.fromkeys(alias for alias in aliases if alias)),
        description=description,
        evidence=evidence,
        confidence=confidence,
        status="draft",
        metadata={"row_index": row_index},
    )


def _add_relation(
    relations: dict[tuple[str, str, str], DraftRelation],
    *,
    source: KGConstructionSource,
    head: str,
    relation: str,
    tail: str,
    evidence: str,
    confidence: float,
    row_index: int,
    relation_family: str,
) -> None:
    key = (head, relation, tail)
    if key in relations:
        return
    relations[key] = DraftRelation(
        draft_id=f"{source.source_id}:relation:{head}:{relation}:{tail}",
        source_id=source.source_id,
        extractor_name=MVTecCatalogExtractor.name,
        extractor_version=MVTecCatalogExtractor.version,
        scenario=source.scenario or "mvtec",
        head=head,
        relation=relation,
        tail=tail,
        evidence=evidence,
        confidence=confidence,
        status="draft",
        metadata={
            "row_index": row_index,
            "relation_family": relation_family,
            "confidence_policy": "mvtec_catalog_candidate",
        },
    )


def _required_text(row: Mapping[str, Any], key: str, *, index: int) -> str:
    value = _text(row.get(key))
    if not value:
        raise ValueError(f"mvtec_ad_catalog row {index} missing {key}")
    return value


def _row_evidence(
    row: Mapping[str, Any],
    *,
    evidence_reference: str,
    index: int,
) -> str:
    parts = [
        f"row={index}",
        f"category_folder={_text(row.get('category_folder'))}",
        f"defect_folder={_text(row.get('defect_folder'))}",
        f"defect_official_name={_text(row.get('defect_official_name'))}",
        f"top_level_anomaly_class={_text(row.get('top_level_anomaly_class'))}",
        f"dataset_fact_source={_text(row.get('dataset_fact_source'))}",
        f"semantic_mapping_source={_text(row.get('semantic_mapping_source'))}",
        f"source={evidence_reference}",
    ]
    return "; ".join(part for part in parts if not part.endswith("="))


def _aliases(*values: object) -> tuple[str, ...]:
    aliases: list[str] = []
    for value in values:
        text = _text(value)
        if not text:
            continue
        aliases.extend((text, text.replace("_", " "), text.lower()))
    return tuple(dict.fromkeys(alias for alias in aliases if alias))


def _defect_aliases(
    category: str,
    defect: str,
    object_name: str,
    defect_name: str,
) -> tuple[str, ...]:
    category_text = _text(category)
    defect_text = _text(defect)
    object_text = _text(object_name).lower()
    defect_human = _text(defect_name).lower()
    return _aliases(
        f"{category_text}:{defect_text}",
        f"{category_text}_{defect_text}",
        f"{category_text} {defect_text}",
        f"{object_text} {defect_human}",
        f"{object_text} {defect_human} defect",
    )


def _mvtec_mechanisms(label: str) -> tuple[str, ...]:
    token = _alias_token(label)
    if "scratch" in token:
        return ("MechanicalContact", "SurfaceWear")
    if "crack" in token:
        return ("MaterialDefect", "PackagingPressure")
    if "cut" in token or "poke" in token:
        return ("MechanicalContact", "HandlingDamage")
    if "bent" in token or "misplaced" in token or "manipulated" in token:
        return ("AssemblyError", "ProcessMisalignment")
    if "broken" in token or "damaged" in token or "split" in token:
        return ("ComponentDamage", "HandlingDamage")
    if "missing" in token:
        return ("MissingComponent", "AssemblyError")
    if "contamination" in token or "dirt" in token or "oil" in token or "liquid" in token:
        return ("ContaminationCause",)
    if "squeeze" in token:
        return ("PackagingPressure", "HandlingDamage")
    if "glue" in token:
        return ("AdhesiveOrResidue",)
    if "thread" in token or "rough" in token or "color" in token or "print" in token:
        return ("TextureIrregularity", "GenericVisualDefectMechanism")
    if "hole" in token:
        return ("MechanicalContact", "MaterialDefect")
    return ("GenericVisualDefectMechanism",)


def _mvtec_object_mechanisms(object_id: str, label: str) -> tuple[str, ...]:
    object_token = _alias_token(object_id.removesuffix("Object"))
    label_token = _alias_token(label)
    if object_token == "cable":
        if "missing" in label_token:
            return ("CableAssemblyOmission",)
        if any(part in label_token for part in ("cut", "poke", "bent")):
            return ("CableInsulationDamage",)
    if object_token == "zipper" and any(
        part in label_token for part in ("teeth", "squeeze", "broken", "split")
    ):
        return ("ZipperTeethAssembly",)
    if object_token == "bottle" and "broken" in label_token:
        return ("BottleBreakage",)
    if object_token == "capsule" and any(
        part in label_token for part in ("crack", "poke", "scratch", "squeeze")
    ):
        return ("CapsuleShellDamage",)
    if object_token == "metalnut" and any(
        part in label_token for part in ("scratch", "color", "bent")
    ):
        return ("MetalNutSurfaceHandling",)
    if object_token == "screw" and any(
        part in label_token for part in ("thread", "scratch", "manipulated")
    ):
        return ("ScrewThreadOrHeadDamage",)
    if object_token == "pill" and any(
        part in label_token for part in ("contamination", "color", "crack", "scratch")
    ):
        return ("PillCoatingOrHandling",)
    if object_token in {"carpet", "grid", "leather", "tile", "wood"} and any(
        part in label_token
        for part in ("color", "glue", "oil", "contamination", "thread", "rough", "liquid")
    ):
        return ("TextureSurfaceContamination",)
    if object_token == "transistor" and any(
        part in label_token for part in ("lead", "misplaced", "damaged")
    ):
        return ("TransistorLeadAssembly",)
    return ()


def _mvtec_mechanism_confidence(mechanism_id: str) -> float:
    if mechanism_id == "GenericVisualDefectMechanism":
        return 0.58
    if mechanism_id in OBJECT_SPECIFIC_MVTEC_MECHANISMS:
        return 0.68
    return 0.66


def _mvtec_mechanism_evidence(label: str, mechanism_id: str, *, object_id: str) -> str:
    object_name = _humanize(object_id.removesuffix("Object"))
    label_text = label.replace("_", " ")
    mechanism_name = MECHANISM_NODES[mechanism_id][0]
    if mechanism_id in OBJECT_SPECIFIC_MVTEC_MECHANISMS:
        return (
            "MVTec AD provides object-level defect test images and pixel anomaly "
            f"masks; for the {object_name} object, source label '{label_text}' "
            f"is mapped to {mechanism_name} as an object-specific candidate "
            f"investigation target. This is {CLAIM_BOUNDARY}."
        )
    return (
        "MVTec AD is an industrial anomaly detection/localization benchmark "
        "with defect test images and pixel-level anomaly annotations; source "
        f"label '{label_text}' is mapped to {mechanism_name} as a candidate "
        f"visual investigation path for KGTraceVis. This is {CLAIM_BOUNDARY}."
    )


def _infer_mvtec_morphology(label: str) -> str:
    token = _alias_token(label)
    if any(part in token for part in ("scratch", "crack", "cut", "thread", "split")):
        return "linear"
    if any(part in token for part in ("contamination", "color", "oil", "liquid")):
        return "scattered"
    return "spot"


def _pascal(value: object) -> str:
    parts = re.split(r"[^A-Za-z0-9]+", _text(value))
    return "".join(part[:1].upper() + part[1:] for part in parts if part)


def _humanize(value: object) -> str:
    text = _text(value).replace("_", " ")
    return " ".join(text.split()).capitalize()


def _alias_token(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", _text(value).lower())


def _text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()
