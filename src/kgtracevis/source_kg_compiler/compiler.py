"""KGBuilder-style LLM compiler for source units and KG CSV artifacts."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from kgtracevis.kg.graph import KnowledgeGraph
from kgtracevis.source_kg_compiler.llm import safe_json_parse
from kgtracevis.source_kg_compiler.models import (
    EDGE_CSV_COLUMNS,
    NODE_CSV_COLUMNS,
    VALID_REVIEW_STATUSES,
    VALID_SCENARIOS,
    CanonicalEdge,
    CanonicalEntity,
    EntityHint,
    KnowledgeCard,
    RelationHint,
    Scenario,
    SourceKGArtifactPaths,
    SourceKGArtifacts,
    SourceKGLLMClient,
    SourceUnit,
)

SUPPORTED_SOURCE_SUFFIXES = {".csv", ".html", ".json", ".jsonl", ".md", ".txt"}
DEFAULT_CHUNK_SIZE = 8000
DEFAULT_CHUNK_OVERLAP = 800
EXPLICIT_RELATIONS = {
    "ACTS_ON",
    "AFFECTS_VARIABLE",
    "BELONGS_TO_UNIT",
    "CARRIES_COMPONENT",
    "CAUSES",
    "CONNECTS_TO",
    "FLOWS_TO",
    "HAS_ANOMALY",
    "HAS_DEFECT",
    "HAS_MORPHOLOGY",
    "HAS_PATTERN",
    "HAS_PLAUSIBLE_CAUSE",
    "HAS_VARIABLE",
    "INDICATES",
    "OCCURS_ON",
    "PART_OF",
    "POSSIBLY_CAUSES",
    "RELATED_TO",
    "REQUIRES_EVIDENCE",
    "SUGGESTS_MECHANISM",
    "SUPPORTS",
}
RELATION_TYPES = [
    "HAS_ANOMALY",
    "HAS_DEFECT",
    "HAS_PATTERN",
    "HAS_MORPHOLOGY",
    "OCCURS_ON",
    "HAS_VARIABLE",
    "AFFECTS_VARIABLE",
    "BELONGS_TO_UNIT",
    "RELATED_TO",
    "INDICATES",
    "SUPPORTS",
    "POSSIBLY_CAUSES",
    "HAS_PLAUSIBLE_CAUSE",
    "SUGGESTS_MECHANISM",
    "REQUIRES_EVIDENCE",
]
ENTITY_TYPES = [
    "Dataset",
    "Object",
    "ProcessUnit",
    "Variable",
    "Fault",
    "Anomaly",
    "Defect",
    "Pattern",
    "Morphology",
    "Location",
    "CandidateCause",
    "Mechanism",
    "EvidenceSource",
    "Other",
]
GENERIC_PLACEHOLDER_ENTITY_IDS = {
    "CandidateCause",
    "FailurePatternRecognition",
    "ManufacturingProcessInformation",
    "Pattern",
    "ProcessFailure",
    "RootCause",
    "RootCauseAnalysis",
    "WaferMap",
    "YieldImprovement",
}
TARGET_TYPE_CONSTRAINTS = {
    "HAS_ANOMALY": {"Anomaly", "Defect", "Pattern"},
    "HAS_DEFECT": {"Defect", "Anomaly"},
    "HAS_PATTERN": {"Pattern"},
    "HAS_MORPHOLOGY": {"Morphology"},
    "OCCURS_ON": {"Location", "Object", "ProcessUnit"},
    "HAS_VARIABLE": {"Variable"},
    "AFFECTS_VARIABLE": {"Variable"},
    "BELONGS_TO_UNIT": {"ProcessUnit"},
    "INDICATES": {"Fault", "CandidateCause", "Mechanism", "Anomaly"},
    "POSSIBLY_CAUSES": {"Fault", "CandidateCause", "Mechanism", "Anomaly", "Defect", "Pattern"},
    "HAS_PLAUSIBLE_CAUSE": {"CandidateCause", "Fault", "Mechanism"},
    "SUGGESTS_MECHANISM": {"Mechanism"},
    "REQUIRES_EVIDENCE": {"EvidenceSource", "Variable"},
}

KNOWLEDGE_CARD_SYSTEM_PROMPT = """You build an offline reusable RCA knowledge graph.
Extract reusable domain knowledge cards from source material.
This is not a case-specific graph for one observed sample.
Return JSON only. Do not output markdown. Do not output explanation text.
Only output the specified schema."""

ENTITY_SYSTEM_PROMPT = """You build canonical entities for an offline reusable RCA knowledge graph.
This is domain-level RCA-KG construction, not a graph for one observed sample or one case.
Return JSON only. Do not output markdown. Do not output explanation text.
Only output the specified schema."""

EDGE_SYSTEM_PROMPT = """You construct edges for an offline reusable RCA knowledge graph.
This is domain-level RCA-KG construction, not a graph for one observed sample or one case.
The graph must support reasoning path search for root-cause analysis.
Return JSON only. Do not output markdown. Do not output explanation text.
Only output the specified schema."""

DOMAIN_PROFILE_SYSTEM_PROMPT = """You extract reusable reasoning profiles for an offline RCA-KG.
This is domain-level profile construction, not a graph for one observed sample or one case.
Return JSON only. Do not output markdown. Do not output explanation text.
Only output the specified schema."""


def compile_source_kg(
    source_paths: tuple[Path, ...],
    output_dir: Path,
    *,
    llm_client: SourceKGLLMClient | None,
    default_scenario: str = "shared",
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    overwrite: bool = False,
) -> tuple[SourceKGArtifacts, SourceKGArtifactPaths, dict[str, Any], dict[str, Any]]:
    """Compile source files into KGBuilder-style LLM KG artifacts and reports."""
    started = time.perf_counter()
    if llm_client is None:
        raise ValueError(
            "source_kg_compiler requires an LLM client; deterministic mode is disabled"
        )
    if default_scenario not in VALID_SCENARIOS:
        raise ValueError(f"invalid default scenario: {default_scenario}")
    paths = artifact_paths(output_dir)
    _prepare_output_dir(output_dir, overwrite=overwrite)

    source_units = load_source_units(
        source_paths,
        default_scenario=default_scenario,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    knowledge_cards = build_knowledge_cards(source_units, llm_client=llm_client)
    entities = build_canonical_entities(knowledge_cards, llm_client=llm_client)
    edges = build_canonical_edges(knowledge_cards, entities, llm_client=llm_client)
    artifacts = SourceKGArtifacts(
        source_units=source_units,
        knowledge_cards=knowledge_cards,
        entities=entities,
        edges=edges,
    )

    write_artifacts(artifacts, paths)
    domain_profiles = build_domain_profiles(
        knowledge_cards=knowledge_cards,
        entities=entities,
        edges=edges,
        llm_client=llm_client,
    )
    _write_json(paths.domain_profiles, domain_profiles)
    _write_json(paths.domain_profile_report, domain_profiles["metadata"])
    _write_json(paths.domain_profiles_manifest, _domain_profiles_manifest(paths.domain_profiles))
    qa_report = build_qa_report(artifacts)
    _write_json(paths.qa_report, qa_report)
    validation_report = validate_generated_kg(
        paths,
        started_at=started,
        counts={
            "source_units": len(source_units),
            "knowledge_cards": len(knowledge_cards),
            "entities": len(entities),
            "edges": len(edges),
        },
        llm_metrics=_llm_metrics(llm_client),
    )
    _write_json(paths.validation_report, validation_report)
    return artifacts, paths, qa_report, validation_report


def artifact_paths(output_dir: Path) -> SourceKGArtifactPaths:
    """Return the complete output path set for a compiler run."""
    return SourceKGArtifactPaths(
        output_dir=output_dir,
        source_units=output_dir / "source_units.jsonl",
        knowledge_cards=output_dir / "knowledge_cards.jsonl",
        entities=output_dir / "entities.jsonl",
        edges=output_dir / "edges.jsonl",
        nodes_csv=output_dir / "nodes.csv",
        edges_csv=output_dir / "edges.csv",
        qa_report=output_dir / "qa_report.json",
        validation_report=output_dir / "validation_report.json",
        domain_profiles=output_dir / "domain_profiles.json",
        domain_profile_report=output_dir / "domain_profile_report.json",
        domain_profiles_manifest=output_dir / "domain_profiles" / "manifest.json",
        runtime_views_manifest=output_dir / "runtime_views" / "manifest.json",
    )


def load_source_units(
    source_paths: tuple[Path, ...],
    *,
    default_scenario: str = "shared",
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[SourceUnit]:
    """Load source files or directories into stable source units."""
    if not source_paths:
        raise ValueError("at least one source path is required")
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be non-negative and smaller than chunk_size")

    files: list[Path] = []
    for source_path in source_paths:
        path = Path(source_path)
        if not path.exists():
            raise ValueError(f"source path does not exist: {path}")
        if path.is_dir():
            files.extend(_iter_source_files(path))
        elif path.is_file():
            files.append(path)
        else:
            raise ValueError(f"source path is not a file or directory: {path}")

    unique_files = sorted({path.resolve(): path for path in files}.values(), key=_path_sort_key)
    if not unique_files:
        raise ValueError("no supported source files found")

    units: list[SourceUnit] = []
    for file_path in unique_files:
        text = file_path.read_text(encoding="utf-8")
        scenario = _infer_unit_scenario(text, default_scenario)
        source_id = _source_id(file_path)
        for chunk in _chunk_text(text, chunk_size=chunk_size, overlap=chunk_overlap):
            chunk_text = chunk["text"]
            chunk_index = int(chunk["index"])
            content_hash = _sha256(chunk_text)
            unit_hash_key = f"{file_path.as_posix()}:{chunk_index}:{content_hash}"
            unit_id = f"su_{_short_hash(unit_hash_key)}"
            units.append(
                SourceUnit(
                    unit_id=unit_id,
                    source_id=source_id,
                    scenario=_scenario(scenario),
                    material_path=file_path.as_posix(),
                    content_text=chunk_text,
                    source_span={
                        "type": "chunk",
                        "chunk_index": chunk_index,
                        "char_start": chunk["start"],
                        "char_end": chunk["end"],
                        "start_line": text.count("\n", 0, int(chunk["start"])) + 1,
                        "end_line": text.count("\n", 0, int(chunk["end"])) + 1,
                    },
                    content_hash=content_hash,
                    parser_metadata={
                        "parser": "source_kg_compiler.file_chunk.v1",
                        "source_format": file_path.suffix.lower().lstrip(".") or "text",
                        "chunk_size": chunk_size,
                        "chunk_overlap": chunk_overlap,
                    },
                )
            )
    return units


def build_knowledge_cards(
    source_units: list[SourceUnit],
    *,
    llm_client: SourceKGLLMClient,
) -> list[KnowledgeCard]:
    """Extract KGBuilder-style knowledge cards with LLM-first source grounding."""
    cards: list[KnowledgeCard] = []
    for unit in source_units:
        cards.extend(_cards_from_unit(unit))
        raw = llm_client.complete_json(
            system_prompt=KNOWLEDGE_CARD_SYSTEM_PROMPT,
            user_prompt=_knowledge_card_user_prompt(unit),
        )
        payload = safe_json_parse(raw, repairer=llm_client.repair_json)
        for item in _as_list(payload.get("cards") if isinstance(payload, dict) else payload):
            if isinstance(item, dict):
                card = _normalize_llm_card(item, unit)
                if card is not None:
                    cards.append(card)
    return _dedupe_knowledge_cards(cards)


def build_canonical_entities(
    knowledge_cards: list[KnowledgeCard],
    *,
    llm_client: SourceKGLLMClient,
) -> list[CanonicalEntity]:
    """Extract canonical entities with KGBuilder's LLM entity stage."""
    entities_by_key: dict[tuple[str, str], CanonicalEntity] = {}
    entity_id_to_key: dict[str, tuple[str, str]] = {}

    def upsert_entity(
        *,
        name: str,
        label: str,
        scenario: str,
        card: KnowledgeCard,
        entity_id: str | None = None,
        aliases: list[str] | None = None,
        description: str = "",
    ) -> CanonicalEntity:
        key = (_normalize_key(name), scenario)
        existing = entities_by_key.get(key)
        if existing is None:
            base_id = entity_id or _pascal_id(name)
            stable_id = _stable_entity_id(base_id, key, entity_id_to_key, scenario)
            existing = CanonicalEntity(
                entity_id=stable_id,
                name=name.strip(),
                label=label.strip() or "Concept",
                scenario=_scenario(scenario),
                aliases=sorted(set(aliases or [])),
                description=description.strip(),
                source_card_ids=[card.card_id],
                source_unit_ids=[card.source_unit_id],
            )
            entities_by_key[key] = existing
            entity_id_to_key[stable_id] = key
            return existing

        merged_aliases = sorted({*existing.aliases, *(aliases or [])})
        merged_card_ids = sorted({*existing.source_card_ids, card.card_id})
        merged_unit_ids = sorted({*existing.source_unit_ids, card.source_unit_id})
        entities_by_key[key] = existing.model_copy(
            update={
                "aliases": merged_aliases,
                "description": existing.description or description.strip(),
                "source_card_ids": merged_card_ids,
                "source_unit_ids": merged_unit_ids,
            }
        )
        return entities_by_key[key]

    for batch in _card_batches(knowledge_cards, batch_size=25):
        raw = llm_client.complete_json(
            system_prompt=ENTITY_SYSTEM_PROMPT,
            user_prompt=_entity_user_prompt(batch),
        )
        payload = safe_json_parse(raw, repairer=llm_client.repair_json)
        for item in _as_list(payload.get("entities") if isinstance(payload, dict) else payload):
            if not isinstance(item, dict):
                continue
            entity = _normalize_llm_entity(item, knowledge_cards)
            if entity is None:
                continue
            key = (_normalize_key(entity.entity_id), entity.scenario)
            if entity.entity_id in GENERIC_PLACEHOLDER_ENTITY_IDS:
                continue
            source_card_ids = entity.source_card_ids or _card_ids_for_scenario(
                knowledge_cards, entity.scenario
            )
            source_unit_ids = _source_units_for_cards(knowledge_cards, source_card_ids)
            first_card = _first_card_for_ids(knowledge_cards, source_card_ids, entity.scenario)
            upsert_entity(
                name=entity.name,
                label=entity.label,
                scenario=entity.scenario,
                card=first_card,
                entity_id=entity.entity_id,
                aliases=entity.aliases,
                description=entity.description,
            )
            merged = entities_by_key[key]
            entities_by_key[key] = merged.model_copy(
                update={
                    "source_card_ids": sorted({*merged.source_card_ids, *source_card_ids}),
                    "source_unit_ids": sorted({*merged.source_unit_ids, *source_unit_ids}),
                }
            )

    for card in sorted(knowledge_cards, key=lambda item: item.card_id):
        for hint in card.entity_hints:
            upsert_entity(
                name=hint.name,
                label=hint.label,
                scenario=hint.scenario,
                card=card,
                entity_id=hint.entity_id,
                aliases=hint.aliases,
                description=hint.description,
            )
        for hint in _relation_hints(card):
            upsert_entity(
                name=hint.head,
                label=hint.head_label,
                scenario=hint.scenario,
                card=card,
                entity_id=hint.head_id,
                aliases=hint.head_aliases,
            )
            upsert_entity(
                name=hint.tail,
                label=hint.tail_label,
                scenario=hint.scenario,
                card=card,
                entity_id=hint.tail_id,
                aliases=hint.tail_aliases,
            )

    return sorted(entities_by_key.values(), key=lambda item: item.entity_id)


def build_canonical_edges(
    knowledge_cards: list[KnowledgeCard],
    entities: list[CanonicalEntity],
    *,
    llm_client: SourceKGLLMClient,
) -> list[CanonicalEdge]:
    """Build KGBuilder-style edges from cards and canonical entities."""
    entity_by_id = {entity.entity_id: entity for entity in entities}
    edges_by_key: dict[tuple[str, str, str, str], CanonicalEdge] = {}

    def upsert_edge(edge: CanonicalEdge) -> None:
        if edge.head not in entity_by_id or edge.tail not in entity_by_id:
            return
        if not _edge_matches_type_constraints(edge, entity_by_id):
            return
        key = (edge.head, edge.relation, edge.tail, edge.scenario)
        existing = edges_by_key.get(key)
        if existing is None:
            edges_by_key[key] = edge
            return
        edges_by_key[key] = existing.model_copy(
            update={
                "source_card_ids": sorted({*existing.source_card_ids, *edge.source_card_ids}),
                "source_unit_ids": sorted({*existing.source_unit_ids, *edge.source_unit_ids}),
                "confidence": max(existing.confidence, edge.confidence),
                "weight": round(1.0 - max(existing.confidence, edge.confidence), 4),
                "evidence": existing.evidence or edge.evidence,
                "source": existing.source or edge.source,
            }
        )

    for batch_cards, batch_entities in _edge_batches(knowledge_cards, entities, batch_size=25):
        raw = llm_client.complete_json(
            system_prompt=EDGE_SYSTEM_PROMPT,
            user_prompt=_edge_user_prompt(batch_cards, batch_entities),
        )
        payload = safe_json_parse(raw, repairer=llm_client.repair_json)
        for item in _as_list(payload.get("edges") if isinstance(payload, dict) else payload):
            if not isinstance(item, dict):
                continue
            edge = _normalize_llm_edge(item, knowledge_cards)
            if edge is not None:
                upsert_edge(edge)

    for card in sorted(knowledge_cards, key=lambda item: item.card_id):
        for hint in _relation_hints(card):
            head = _resolve_entity_id(hint.head_id or hint.head, entity_by_id, hint.scenario)
            tail = _resolve_entity_id(hint.tail_id or hint.tail, entity_by_id, hint.scenario)
            if head is None or tail is None:
                continue
            relation = _relation_name(hint.relation)
            confidence = round(float(hint.confidence), 4)
            upsert_edge(
                CanonicalEdge(
                    edge_id=_edge_id(head, relation, tail, hint.scenario),
                    head=head,
                    relation=relation,
                    tail=tail,
                    scenario=hint.scenario,
                    source=hint.source,
                    evidence=hint.evidence,
                    source_card_ids=[card.card_id],
                    source_unit_ids=[card.source_unit_id],
                    confidence=confidence,
                    weight=round(1.0 - confidence, 4),
                    review_status=hint.review_status,
                )
            )

    return sorted(
        edges_by_key.values(),
        key=lambda item: (item.head, item.relation, item.tail, item.scenario),
    )


def build_domain_profiles(
    *,
    knowledge_cards: list[KnowledgeCard],
    entities: list[CanonicalEntity],
    edges: list[CanonicalEdge],
    llm_client: SourceKGLLMClient,
) -> dict[str, Any]:
    """Extract reusable KGBuilder-style domain reasoning profiles."""
    deterministic = _deterministic_domain_profiles(entities, edges)
    raw = llm_client.complete_json(
        system_prompt=DOMAIN_PROFILE_SYSTEM_PROMPT,
        user_prompt=_domain_profile_user_prompt(knowledge_cards, entities, edges),
    )
    payload = safe_json_parse(raw, repairer=llm_client.repair_json)
    llm_payload = payload if isinstance(payload, dict) else {}
    profiles = _merge_profile_payloads(deterministic, llm_payload)
    return {
        "artifact_type": "domain_reasoning_profiles_v0",
        "generated_at": _utc_now(),
        "method": "llm_profile_extraction_plus_deterministic_compiler",
        "llm_profile_extraction_ok": bool(llm_payload),
        "llm_profile_extraction_error": "",
        "profiles": profiles["profiles"],
        "metadata": {
            "num_cards": len(knowledge_cards),
            "num_entities": len(entities),
            "num_edges": len(edges),
            "profile_counts": _profile_counts(profiles),
        },
    }


def write_artifacts(artifacts: SourceKGArtifacts, paths: SourceKGArtifactPaths) -> None:
    """Write compiler artifacts to JSONL, CSV, and placeholder manifests."""
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    paths.domain_profiles_manifest.parent.mkdir(parents=True, exist_ok=True)
    paths.runtime_views_manifest.parent.mkdir(parents=True, exist_ok=True)

    _write_jsonl(paths.source_units, artifacts.source_units)
    _write_jsonl(paths.knowledge_cards, artifacts.knowledge_cards)
    _write_jsonl(paths.entities, artifacts.entities)
    _write_jsonl(paths.edges, artifacts.edges)
    _write_nodes_csv(paths.nodes_csv, artifacts.entities)
    _write_edges_csv(paths.edges_csv, artifacts.edges)
    _write_json(paths.runtime_views_manifest, _placeholder_manifest("runtime_views"))


def build_qa_report(artifacts: SourceKGArtifacts) -> dict[str, Any]:
    """Build artifact-level QA for generated compiler outputs."""
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    entity_ids = [entity.entity_id for entity in artifacts.entities]
    duplicate_entity_ids = sorted(
        entity_id for entity_id, count in Counter(entity_ids).items() if count > 1
    )
    for entity_id in duplicate_entity_ids:
        errors.append({"check": "duplicate_entity_id", "entity_id": entity_id})

    for entity in artifacts.entities:
        for field_name in ("entity_id", "name", "label", "scenario"):
            if not getattr(entity, field_name):
                errors.append(
                    {
                        "check": "required_entity_field",
                        "entity_id": entity.entity_id,
                        "field": field_name,
                    }
                )
        if entity.scenario not in VALID_SCENARIOS:
            errors.append(
                {
                    "check": "valid_entity_scenario",
                    "entity_id": entity.entity_id,
                    "scenario": entity.scenario,
                }
            )

    endpoints = set(entity_ids)
    edge_ids = [edge.edge_id for edge in artifacts.edges]
    duplicate_edge_ids = sorted(
        edge_id for edge_id, count in Counter(edge_ids).items() if count > 1
    )
    for edge_id in duplicate_edge_ids:
        errors.append({"check": "duplicate_edge_id", "edge_id": edge_id})

    connected: set[str] = set()
    for edge in artifacts.edges:
        connected.update({edge.head, edge.tail})
        if edge.head not in endpoints:
            errors.append({"check": "edge_endpoint", "edge_id": edge.edge_id, "missing": edge.head})
        if edge.tail not in endpoints:
            errors.append({"check": "edge_endpoint", "edge_id": edge.edge_id, "missing": edge.tail})
        if edge.head == edge.tail:
            errors.append({"check": "self_edge", "edge_id": edge.edge_id})
        if edge.scenario not in VALID_SCENARIOS:
            errors.append(
                {"check": "valid_edge_scenario", "edge_id": edge.edge_id, "scenario": edge.scenario}
            )
        if edge.review_status not in VALID_REVIEW_STATUSES:
            errors.append(
                {
                    "check": "valid_review_status",
                    "edge_id": edge.edge_id,
                    "review_status": edge.review_status,
                }
            )
        for field_name in ("source", "evidence", "review_status"):
            if not getattr(edge, field_name):
                errors.append(
                    {
                        "check": "required_edge_provenance",
                        "edge_id": edge.edge_id,
                        "field": field_name,
                    }
                )
        if not 0.0 <= edge.confidence <= 1.0:
            errors.append({"check": "confidence_range", "edge_id": edge.edge_id})
        if not 0.0 <= edge.weight <= 1.0:
            errors.append({"check": "weight_range", "edge_id": edge.edge_id})
        if min(edge.feedback_count, edge.accepted_count, edge.rejected_count) < 0:
            errors.append({"check": "feedback_counter_range", "edge_id": edge.edge_id})

    isolated_nodes = sorted(set(entity_ids) - connected)
    for entity_id in isolated_nodes:
        warnings.append({"check": "isolated_node", "entity_id": entity_id})

    return {
        "artifact_type": "source_kg_compiler_qa_report_v1",
        "status": "passed" if not errors else "failed",
        "errors": errors,
        "warnings": warnings,
        "checks": {
            "schema_validity": {"error_count": len(errors)},
            "endpoint_validity": {
                "error_count": sum(1 for error in errors if error["check"] == "edge_endpoint")
            },
            "duplicate_entities": {"duplicate_ids": duplicate_entity_ids},
            "duplicate_edges": {"duplicate_ids": duplicate_edge_ids},
            "self_edges": {
                "error_count": sum(1 for error in errors if error["check"] == "self_edge")
            },
            "isolated_nodes": {"warning_count": len(isolated_nodes), "node_ids": isolated_nodes},
            "required_field_coverage": _required_field_coverage(artifacts),
        },
        "scenario_counts": {
            "entities": dict(
                sorted(Counter(entity.scenario for entity in artifacts.entities).items())
            ),
            "edges": dict(sorted(Counter(edge.scenario for edge in artifacts.edges).items())),
        },
        "counts": {
            "source_units": len(artifacts.source_units),
            "knowledge_cards": len(artifacts.knowledge_cards),
            "entities": len(artifacts.entities),
            "edges": len(artifacts.edges),
        },
    }


def validate_generated_kg(
    paths: SourceKGArtifactPaths,
    *,
    started_at: float | None = None,
    counts: dict[str, int] | None = None,
    llm_metrics: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Validate generated CSVs without loading default KG layers."""
    validation_started = time.perf_counter()
    graph = KnowledgeGraph.from_csv(paths.nodes_csv, paths.edges_csv)
    finished = time.perf_counter()
    started = validation_started if started_at is None else started_at
    return {
        "artifact_type": "source_kg_compiler_validation_report_v1",
        "status": "passed",
        "strict_generated_only": True,
        "default_kg_layers_loaded": False,
        "loaded_node_files": [paths.nodes_csv.as_posix()],
        "loaded_edge_files": [paths.edges_csv.as_posix()],
        "forbidden_default_layers": [
            "data/kg/nodes.csv",
            "data/kg/mvtec_nodes.csv",
            "data/kg/tep_nodes.csv",
            "data/kg/wafer_nodes.csv",
            "data/kg/edges.csv",
            "data/kg/mvtec_rca_reference.csv",
            "data/kg/mvtec_edges.csv",
            "data/kg/tep_edges.csv",
            "data/kg/wafer_edges.csv",
        ],
        "metrics": {
            "runtime_seconds": round(finished - started, 6),
            "validation_runtime_seconds": round(finished - validation_started, 6),
            "counts": {
                **(counts or {}),
                "loaded_nodes": len(graph.nodes),
                "loaded_edges": len(graph.edges),
            },
            "file_paths_loaded": {
                "nodes": [paths.nodes_csv.as_posix()],
                "edges": [paths.edges_csv.as_posix()],
            },
            "artifact_sizes_bytes": _artifact_sizes(paths),
            "performance_baseline": {
                "name": "KGBuilder",
                "status": "not_run",
                "reason": (
                    "Run KGBuilder on comparable source materials and compare runtime, "
                    "LLM calls, token volume, artifact sizes, and KG counts."
                ),
            },
            "llm_calls": (llm_metrics or {}).get("llm_calls", 0),
            "llm_input_tokens": (llm_metrics or {}).get("llm_input_tokens", 0),
            "llm_output_tokens": (llm_metrics or {}).get("llm_output_tokens", 0),
            "llm_total_tokens": (llm_metrics or {}).get("llm_total_tokens", 0),
            "mode": "llm_kgbuilder_style",
        },
    }


def _knowledge_card_user_prompt(unit: SourceUnit) -> str:
    return f"""Extract reusable RCA knowledge cards from this source unit.

Each card must contain:
- card_id
- scenario
- claim
- entities_mentioned
- relation_hints
- source_chunk_id
- source_material_ids
- evidence_text

Rules:
- Extract only claims grounded in the provided source text.
- Do not invent industrial facts or verified causal relations.
- This is offline reusable RCA-KG construction, not one case/sample graph.
- Keep evidence_text as exact or near-exact source text when possible.
- Relation hints may be strings such as "CableObject HAS_ANOMALY BentCableDefect".
- Prefer compact reusable cards. Output at most 35 cards for this source unit.
- Output JSON object exactly like:
{{
  "cards": [
    {{
      "card_id": "card_0001",
      "scenario": "mvtec",
      "claim": "...",
      "entities_mentioned": ["CableObject", "BentCableDefect"],
      "relation_hints": ["CableObject HAS_ANOMALY BentCableDefect"],
      "source_chunk_id": "{unit.unit_id}",
      "source_material_ids": ["{unit.source_id}"],
      "evidence_text": "..."
    }}
  ]
}}

Default scenario: {unit.scenario}
Source chunk id: {unit.unit_id}
Source material ids: ["{unit.source_id}"]
Source path: {unit.material_path}

Source text:
{unit.content_text}
"""


def _entity_user_prompt(cards: list[KnowledgeCard]) -> str:
    return f"""Extract canonical KG entities from these knowledge cards.

Entity type must be one of:
{json.dumps(ENTITY_TYPES, ensure_ascii=False)}

Each entity must contain:
- entity_id
- canonical_name
- entity_type
- aliases
- description
- scenario
- source_card_ids

Rules:
- This is offline reusable RCA-KG construction, not a single sample/case graph.
- Canonical names should use CamelCase, e.g. CableObject, BentWireDefect, RingPattern.
- Merge aliases that refer to the same reusable concept.
- Include objects, process units, variables, faults, anomalies, defects, patterns,
  morphology, locations, candidate causes, mechanisms, and evidence sources.
- Keep descriptions concise, one sentence maximum.
- Prefer compact reusable entities. For this batch, output at most 45 entities.
- Output JSON object exactly like:
{{
  "entities": [
    {{
      "entity_id": "CableObject",
      "canonical_name": "CableObject",
      "entity_type": "Object",
      "aliases": ["cable"],
      "description": "...",
      "scenario": "mvtec",
      "source_card_ids": ["card_0001"]
    }}
  ]
}}

Knowledge cards:
{json.dumps([_card_payload(card) for card in cards], ensure_ascii=False, indent=2)}
"""


def _edge_user_prompt(cards: list[KnowledgeCard], entities: list[CanonicalEntity]) -> str:
    return f"""Build RCA-KG edges from knowledge cards and canonical entities.

Allowed relation types:
{json.dumps(RELATION_TYPES, ensure_ascii=False)}

Each edge must contain:
- edge_id
- source
- relation
- target
- scenario
- evidence
- source_card_ids
- confidence
- review_status

Rules:
- This is offline reusable RCA-KG construction, not a single sample/case graph.
- Use only entity_id values from the provided canonical entities for source and target.
- Prefer useful RCA reasoning relations, not only RELATED_TO.
- Prefer compact, high-value edges that support path search.
  For this batch, output at most 70 edges.
- Keep evidence concise, one sentence maximum.
- Include relationships such as:
  1. anomaly/defect to object/unit, e.g. CableObject HAS_ANOMALY BentWireDefect
  2. anomaly/defect to morphology/pattern/location
  3. fault/anomaly to variable/process unit
  4. anomaly/pattern to candidate cause/mechanism
  5. candidate cause to required evidence
- Default confidence to 0.7 and review_status to "auto".
- Output JSON object exactly like:
{{
  "edges": [
    {{
      "edge_id": "edge_0001",
      "source": "CableObject",
      "relation": "HAS_ANOMALY",
      "target": "BentWireDefect",
      "scenario": "mvtec",
      "evidence": "...",
      "source_card_ids": ["card_0001"],
      "confidence": 0.7,
      "review_status": "auto"
    }}
  ]
}}

Canonical entities:
{json.dumps([_entity_payload(entity) for entity in entities], ensure_ascii=False, indent=2)}

Knowledge cards:
{json.dumps([_card_payload(card) for card in cards], ensure_ascii=False, indent=2)}
"""


def _domain_profile_user_prompt(
    cards: list[KnowledgeCard],
    entities: list[CanonicalEntity],
    edges: list[CanonicalEdge],
) -> str:
    return f"""Extract compact reasoning profiles from these RCA-KG artifacts.

The profiles must be reusable and explainable. They will be compiled into runtime RCA views.

Output JSON object exactly like:
{{
  "profiles": {{
    "tep": {{
      "fault_profiles": [
        {{
          "fault_anchor_id": "faultanchor:reactor_heat_transfer",
          "anchor_name": "Reactor heat-transfer disturbance",
          "fault_numbers": [17],
          "support_targets": ["equipment:reactor", "variable:xmeas_9"],
          "diagnostic_variables": ["variable:xmeas_9", "variable:xmeas_21"],
          "source_card_ids": ["card_0001"],
          "source_edge_ids": ["edge_0001"],
          "rationale": "..."
        }}
      ],
      "unit_observation_profiles": [
        {{
          "unit_id": "equipment:reactor",
          "observed_variables": ["variable:xmeas_7", "variable:xmeas_9"],
          "source_edge_ids": ["edge_0002"]
        }}
      ]
    }},
    "wafer": {{
      "pattern_profiles": [
        {{
          "pattern_id": "DonutPattern",
          "pattern_name": "DonutPattern",
          "candidate_causes": ["RadialProcessNonuniformityCause"],
          "morphologies": ["RingPattern"],
          "locations": ["CenterLocation"],
          "evidence_requirements": ["RadialMetrologyEvidence"],
          "source_edge_ids": ["edge_0003"]
        }}
      ]
    }},
    "mvtec": {{
      "object_defect_profiles": [
        {{
          "object_id": "CableObject",
          "defect_id": "BentCableDefect",
          "candidate_causes": ["FixtureMisalignmentCause"],
          "morphologies": ["LinearMorphology"],
          "locations": ["SurfaceLocation"],
          "evidence_requirements": ["VisualInspectionEvidence"],
          "source_edge_ids": ["edge_0004"]
        }}
      ]
    }}
  }}
}}

Rules:
- Use IDs from the provided entities/edges whenever possible.
- For TEP, use Root-KGD runtime IDs for support_targets and diagnostic_variables,
  e.g. variable:xmeas_9.
- Do not invent sample-specific evidence.
- Keep each profile concise and reusable.
- Prefer high-value RCA reasoning profiles over exhaustive lists.

Compact entities:
{json.dumps([_compact_entity(entity) for entity in entities], ensure_ascii=False)}

Compact edges:
{json.dumps([_compact_edge(edge) for edge in edges], ensure_ascii=False)}

Representative cards:
{json.dumps([_card_payload(card) for card in cards[:90]], ensure_ascii=False)}
"""


def _normalize_llm_card(item: dict[str, Any], unit: SourceUnit) -> KnowledgeCard | None:
    claim = str(item.get("claim") or "").strip()
    if not claim:
        return None
    scenario = _scenario(str(item.get("scenario") or unit.scenario))
    relation_hints: list[RelationHint | str] = []
    for value in _as_list(item.get("relation_hints")):
        if isinstance(value, dict):
            relation_hints.append(_relation_hint_from_dict(value, unit, scenario))
        else:
            text = str(value).strip()
            parsed = _parse_relation_hint_from_text(text, unit, scenario)
            relation_hints.append(parsed or text)
    return KnowledgeCard(
        card_id=str(item.get("card_id") or _pascal_id(claim)).strip(),
        source_unit_id=str(item.get("source_chunk_id") or unit.unit_id),
        scenario=scenario,
        claim=claim,
        entities_mentioned=[
            str(value).strip()
            for value in _as_list(item.get("entities_mentioned"))
            if str(value).strip()
        ],
        relation_hints=relation_hints,
        entity_hints=[],
        evidence_text=str(item.get("evidence_text") or claim).strip(),
        source_path=unit.material_path,
        content_hash=unit.content_hash,
    )


def _normalize_llm_entity(
    item: dict[str, Any],
    knowledge_cards: list[KnowledgeCard],
) -> CanonicalEntity | None:
    canonical_name = str(item.get("canonical_name") or item.get("entity_id") or "").strip()
    if not canonical_name:
        return None
    entity_id = _pascal_id(canonical_name)
    label = str(item.get("entity_type") or item.get("label") or "Other").strip()
    if label not in ENTITY_TYPES:
        label = "Other"
    scenario = _scenario(
        str(
            item.get("scenario")
            or _scenario_from_card_ids(knowledge_cards, item.get("source_card_ids"))
        )
    )
    source_card_ids = [
        str(value).strip()
        for value in _as_list(item.get("source_card_ids"))
        if str(value).strip()
    ]
    return CanonicalEntity(
        entity_id=entity_id,
        name=entity_id,
        label=label,
        scenario=scenario,
        aliases=sorted(
            {
                str(value).strip()
                for value in _as_list(item.get("aliases"))
                if str(value).strip()
            }
        ),
        description=str(item.get("description") or "").strip()[:240],
        source_card_ids=source_card_ids,
        source_unit_ids=_source_units_for_cards(knowledge_cards, source_card_ids),
    )


def _normalize_llm_edge(
    item: dict[str, Any],
    knowledge_cards: list[KnowledgeCard],
) -> CanonicalEdge | None:
    head = str(item.get("source") or item.get("head") or "").strip()
    tail = str(item.get("target") or item.get("tail") or "").strip()
    if not head or not tail:
        return None
    relation = str(item.get("relation") or "RELATED_TO").upper().strip()
    if relation not in RELATION_TYPES:
        relation = "RELATED_TO"
    try:
        confidence = float(item.get("confidence", 0.7))
    except (TypeError, ValueError):
        confidence = 0.7
    confidence = max(0.0, min(1.0, round(confidence, 4)))
    source_card_ids = [
        str(value).strip()
        for value in _as_list(item.get("source_card_ids"))
        if str(value).strip()
    ]
    scenario = _scenario(
        str(item.get("scenario") or _scenario_from_card_ids(knowledge_cards, source_card_ids))
    )
    review_status = str(item.get("review_status") or "auto")
    if review_status not in VALID_REVIEW_STATUSES:
        review_status = "auto"
    return CanonicalEdge(
        edge_id=_edge_id(head, relation, tail, scenario),
        head=head,
        relation=relation,
        tail=tail,
        scenario=scenario,
        source=_edge_source(source_card_ids),
        evidence=str(item.get("evidence") or "").strip() or f"{head} {relation} {tail}",
        source_card_ids=source_card_ids,
        source_unit_ids=_source_units_for_cards(knowledge_cards, source_card_ids),
        confidence=confidence,
        weight=round(1.0 - confidence, 4),
        review_status=cast(Any, review_status),
    )


def _dedupe_knowledge_cards(cards: list[KnowledgeCard]) -> list[KnowledgeCard]:
    deduped: list[KnowledgeCard] = []
    seen: set[tuple[str, str]] = set()
    for card in sorted(cards, key=lambda item: (item.source_unit_id, item.card_id, item.claim)):
        key = (card.scenario, _normalize_key(card.claim))
        if not card.claim or key in seen:
            continue
        seen.add(key)
        deduped.append(card.model_copy(update={"card_id": f"card_{len(deduped) + 1:04d}"}))
    return deduped


def _card_batches(cards: list[KnowledgeCard], *, batch_size: int) -> list[list[KnowledgeCard]]:
    grouped: dict[str, list[KnowledgeCard]] = defaultdict(list)
    for card in cards:
        grouped[card.scenario].append(card)
    batches: list[list[KnowledgeCard]] = []
    for scenario in sorted(grouped):
        scenario_cards = sorted(grouped[scenario], key=lambda item: item.card_id)
        for start in range(0, len(scenario_cards), batch_size):
            batches.append(scenario_cards[start : start + batch_size])
    return batches


def _edge_batches(
    cards: list[KnowledgeCard],
    entities: list[CanonicalEntity],
    *,
    batch_size: int,
) -> list[tuple[list[KnowledgeCard], list[CanonicalEntity]]]:
    entities_by_scenario: dict[str, list[CanonicalEntity]] = defaultdict(list)
    for entity in entities:
        entities_by_scenario[entity.scenario].append(entity)
    batches: list[tuple[list[KnowledgeCard], list[CanonicalEntity]]] = []
    for batch in _card_batches(cards, batch_size=batch_size):
        scenario = batch[0].scenario
        batch_entities = entities_by_scenario.get(scenario, []) + entities_by_scenario.get(
            "shared", []
        )
        batches.append((batch, sorted(batch_entities, key=lambda item: item.entity_id)))
    return batches


def _cards_from_unit(unit: SourceUnit) -> list[KnowledgeCard]:
    cards: list[KnowledgeCard] = []
    for line_number, line in enumerate(unit.content_text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.lower().startswith("relation:"):
            hint = _parse_relation_hint(stripped, unit)
            cards.append(_card_from_relation_hint(unit, line_number, stripped, hint))
        elif stripped.lower().startswith("entity:"):
            hint = _parse_entity_hint(stripped, unit)
            cards.append(
                KnowledgeCard(
                    card_id=f"kc_{_short_hash(f'{unit.unit_id}:{line_number}:{stripped}')}",
                    source_unit_id=unit.unit_id,
                    scenario=hint.scenario,
                    claim=f"Entity {hint.name}",
                    entities_mentioned=[hint.name],
                    relation_hints=[],
                    entity_hints=[hint],
                    evidence_text=stripped,
                    source_path=unit.material_path,
                    content_hash=unit.content_hash,
                )
            )
        else:
            hint = _parse_explicit_relation_line(stripped, unit)
            if hint is not None:
                cards.append(_card_from_relation_hint(unit, line_number, stripped, hint))
    return cards


def _relation_hint_from_dict(
    item: dict[str, Any],
    unit: SourceUnit,
    scenario: Scenario,
) -> RelationHint:
    head = str(item.get("head") or item.get("source") or "").strip()
    relation = str(item.get("relation") or "RELATED_TO").strip()
    tail = str(item.get("tail") or item.get("target") or "").strip()
    if not head or not tail:
        raise ValueError("relation hint object must include head/source and tail/target")
    try:
        confidence = float(item.get("confidence", 0.7))
    except (TypeError, ValueError):
        confidence = 0.7
    return RelationHint(
        head=head,
        relation=relation,
        tail=tail,
        scenario=_scenario(str(item.get("scenario") or scenario)),
        confidence=max(0.0, min(1.0, confidence)),
        source=str(item.get("source_material") or item.get("provenance_source") or unit.source_id),
        evidence=str(item.get("evidence") or f"{head} {_relation_name(relation)} {tail}"),
        head_id=str(item.get("head_id") or item.get("source_id") or "") or None,
        tail_id=str(item.get("tail_id") or item.get("target_id") or "") or None,
        head_label=str(item.get("head_label") or _infer_entity_label(head)),
        tail_label=str(item.get("tail_label") or _infer_entity_label(tail)),
        review_status="auto",
    )


def _parse_relation_hint_from_text(
    text: str,
    unit: SourceUnit,
    scenario: Scenario,
) -> RelationHint | None:
    relation_pattern = "|".join(
        sorted(EXPLICIT_RELATIONS | set(RELATION_TYPES), key=len, reverse=True)
    )
    match = re.match(
        rf"^\s*(?:[-*]\s*)?([A-Z][A-Za-z0-9]+)\s+({relation_pattern})\s+"
        rf"([A-Z][A-Za-z0-9]+)\.?\s*$",
        text,
    )
    if match is None:
        return None
    head, relation, tail = match.groups()
    return RelationHint(
        head=head,
        relation=relation,
        tail=tail,
        scenario=scenario,
        confidence=0.7,
        source=unit.source_id,
        evidence=text.lstrip("-* ").rstrip("."),
        head_label=_infer_entity_label(head),
        tail_label=_infer_entity_label(tail),
        review_status="auto",
    )


def _parse_relation_hint_from_claim(text: str, card: KnowledgeCard) -> RelationHint | None:
    unit = SourceUnit(
        unit_id=card.source_unit_id,
        source_id=Path(card.source_path).stem,
        scenario=card.scenario,
        material_path=card.source_path,
        content_text=card.evidence_text,
        source_span={},
        content_hash=card.content_hash,
        parser_metadata={},
    )
    return _parse_relation_hint_from_text(text, unit, card.scenario)


def _card_from_relation_hint(
    unit: SourceUnit,
    line_number: int,
    raw_line: str,
    hint: RelationHint,
) -> KnowledgeCard:
    return KnowledgeCard(
        card_id=f"kc_{_short_hash(f'{unit.unit_id}:{line_number}:{raw_line}')}",
        source_unit_id=unit.unit_id,
        scenario=hint.scenario,
        claim=f"{hint.head} {_relation_name(hint.relation)} {hint.tail}",
        entities_mentioned=[hint.head, hint.tail],
        relation_hints=[hint],
        entity_hints=[],
        evidence_text=hint.evidence,
        source_path=unit.material_path,
        content_hash=unit.content_hash,
    )


def _parse_relation_hint(line: str, unit: SourceUnit) -> RelationHint:
    payload = line.split(":", 1)[1].strip()
    parts = [part.strip() for part in payload.split("|")]
    if len(parts) < 3:
        raise ValueError(f"relation hint must include head | relation | tail: {line}")
    head, relation, tail = parts[:3]
    options = _parse_options(parts[3:])
    scenario = _scenario(options.get("scenario", unit.scenario))
    confidence = float(options.get("confidence", "0.75"))
    if not 0.0 <= confidence <= 1.0:
        raise ValueError(f"relation confidence must be in [0, 1]: {line}")
    review_status = options.get("review_status", "auto")
    if review_status not in VALID_REVIEW_STATUSES:
        raise ValueError(f"invalid review_status in relation hint: {review_status}")
    return RelationHint(
        head=head,
        relation=relation,
        tail=tail,
        scenario=scenario,
        confidence=confidence,
        source=options.get("source", unit.source_id),
        evidence=options.get("evidence", line),
        head_id=options.get("head_id"),
        tail_id=options.get("tail_id"),
        head_label=options.get("head_label", options.get("label", "Concept")),
        tail_label=options.get("tail_label", options.get("label", "Concept")),
        head_aliases=_split_aliases(options.get("head_aliases", "")),
        tail_aliases=_split_aliases(options.get("tail_aliases", "")),
        review_status=review_status,  # type: ignore[arg-type]
    )


def _parse_entity_hint(line: str, unit: SourceUnit) -> EntityHint:
    payload = line.split(":", 1)[1].strip()
    parts = [part.strip() for part in payload.split("|")]
    if not parts or not parts[0]:
        raise ValueError(f"entity hint must include an entity name: {line}")
    options = _parse_options(parts[1:])
    return EntityHint(
        name=parts[0],
        label=options.get("label", "Concept"),
        entity_id=options.get("id"),
        scenario=_scenario(options.get("scenario", unit.scenario)),
        aliases=_split_aliases(options.get("aliases", "")),
        description=options.get("description", ""),
    )


def _parse_explicit_relation_line(line: str, unit: SourceUnit) -> RelationHint | None:
    """Parse KGBuilder-style explicit relation lines.

    KGBuilder source notes use human-readable bullets such as
    ``- CableObject HAS_ANOMALY BentCableDefect.``. Keeping this deterministic
    fast path lets the bypass reuse those source notes without needing LLM calls.
    """
    relation_pattern = "|".join(sorted(EXPLICIT_RELATIONS, key=len, reverse=True))
    match = re.match(
        rf"^\s*(?:[-*]\s*)?([A-Z][A-Za-z0-9]+)\s+({relation_pattern})\s+"
        rf"([A-Z][A-Za-z0-9]+)\.?\s*$",
        line,
    )
    if match is None:
        return None
    head, relation, tail = match.groups()
    return RelationHint(
        head=head,
        relation=relation,
        tail=tail,
        scenario=unit.scenario,
        confidence=0.75,
        source=unit.source_id,
        evidence=line.lstrip("-* ").rstrip("."),
        head_label=_infer_entity_label(head),
        tail_label=_infer_entity_label(tail),
        review_status="auto",
    )


def _prepare_output_dir(output_dir: Path, *, overwrite: bool) -> None:
    if output_dir.exists() and any(output_dir.iterdir()):
        if not overwrite:
            raise ValueError(f"output directory is not empty: {output_dir}")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)


def _iter_source_files(directory: Path) -> list[Path]:
    return [
        path
        for path in directory.rglob("*")
        if path.is_file()
        and not any(part.startswith(".") for part in path.parts)
        and path.suffix.lower() in SUPPORTED_SOURCE_SUFFIXES
    ]


def _chunk_text(text: str, *, chunk_size: int, overlap: int) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    start = 0
    index = 1
    text_length = len(text)
    while start < text_length:
        end = min(start + chunk_size, text_length)
        if end < text_length:
            newline = text.rfind("\n", start + max(1000, chunk_size // 2), end)
            if newline > start:
                end = newline
        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append(
                {
                    "index": index,
                    "start": start,
                    "end": end,
                    "text": chunk_text,
                }
            )
            index += 1
        if end >= text_length:
            break
        start = max(0, end - overlap)
    return chunks


def _write_jsonl(path: Path, records: list[Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record.model_dump(mode="json"), sort_keys=True) + "\n")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_nodes_csv(path: Path, entities: list[CanonicalEntity]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=NODE_CSV_COLUMNS)
        writer.writeheader()
        for entity in entities:
            writer.writerow(
                {
                    "id": entity.entity_id,
                    "name": entity.name,
                    "label": entity.label,
                    "scenario": entity.scenario,
                    "aliases": "|".join(entity.aliases),
                    "description": entity.description,
                }
            )


def _write_edges_csv(path: Path, edges: list[CanonicalEdge]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=EDGE_CSV_COLUMNS)
        writer.writeheader()
        for edge in edges:
            writer.writerow(
                {
                    "head": edge.head,
                    "relation": edge.relation,
                    "tail": edge.tail,
                    "scenario": edge.scenario,
                    "source": edge.source,
                    "evidence": edge.evidence,
                    "confidence": _format_float(edge.confidence),
                    "weight": _format_float(edge.weight),
                    "review_status": edge.review_status,
                    "feedback_count": edge.feedback_count,
                    "accepted_count": edge.accepted_count,
                    "rejected_count": edge.rejected_count,
                }
            )


def _placeholder_manifest(kind: str) -> dict[str, Any]:
    return {
        "artifact_type": f"source_kg_compiler_{kind}_manifest_v1",
        "status": "not_generated",
        "reason": (
            "The first source_kg_compiler slice emits canonical KG artifacts only. "
            "Domain profile and runtime view generation requires profile/projector inputs "
            "planned for a later slice."
        ),
        "missing_inputs": [
            "domain profile extraction policy",
            "scenario runtime projection policy",
            "runtime view validation cases",
        ],
    }


def _domain_profiles_manifest(domain_profiles_path: Path) -> dict[str, Any]:
    return {
        "artifact_type": "source_kg_compiler_domain_profiles_manifest_v1",
        "status": "generated",
        "domain_profiles": domain_profiles_path.as_posix(),
        "method": "llm_profile_extraction_plus_deterministic_compiler",
    }


def _card_payload(card: KnowledgeCard) -> dict[str, Any]:
    return {
        "card_id": card.card_id,
        "scenario": card.scenario,
        "claim": card.claim,
        "entities_mentioned": card.entities_mentioned,
        "relation_hints": [
            (
                hint
                if isinstance(hint, str)
                else f"{hint.head} {_relation_name(hint.relation)} {hint.tail}"
            )
            for hint in card.relation_hints
        ],
        "source_chunk_id": card.source_unit_id,
        "source_material_ids": [Path(card.source_path).stem],
        "evidence_text": card.evidence_text,
    }


def _entity_payload(entity: CanonicalEntity) -> dict[str, Any]:
    return {
        "entity_id": entity.entity_id,
        "canonical_name": entity.name,
        "entity_type": entity.label,
        "aliases": entity.aliases,
        "description": entity.description,
        "scenario": entity.scenario,
        "source_card_ids": entity.source_card_ids,
    }


def _compact_entity(entity: CanonicalEntity) -> dict[str, Any]:
    return {
        "entity_id": entity.entity_id,
        "entity_type": entity.label,
        "scenario": entity.scenario,
        "aliases": entity.aliases[:4],
    }


def _compact_edge(edge: CanonicalEdge) -> dict[str, Any]:
    return {
        "edge_id": edge.edge_id,
        "source": edge.head,
        "relation": edge.relation,
        "target": edge.tail,
        "scenario": edge.scenario,
        "source_card_ids": edge.source_card_ids[:4],
    }


def _deterministic_domain_profiles(
    entities: list[CanonicalEntity],
    edges: list[CanonicalEdge],
) -> dict[str, Any]:
    entity_by_id = {entity.entity_id: entity for entity in entities}
    edges_by_head: dict[str, list[CanonicalEdge]] = defaultdict(list)
    for edge in edges:
        edges_by_head[edge.head].append(edge)
    return {
        "profiles": {
            "tep": {"fault_profiles": [], "unit_observation_profiles": []},
            "wafer": {
                "pattern_profiles": _dedupe_profile_rows(
                    _deterministic_wafer_profiles(entity_by_id, edges_by_head)
                )
            },
            "mvtec": {
                "object_defect_profiles": _dedupe_profile_rows(
                    _deterministic_mvtec_profiles(entity_by_id, edges_by_head)
                )
            },
        }
    }


def _deterministic_wafer_profiles(
    entity_by_id: dict[str, CanonicalEntity],
    edges_by_head: dict[str, list[CanonicalEdge]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entity_id, entity in sorted(entity_by_id.items()):
        if entity.scenario != "wafer" or entity.label != "Pattern":
            continue
        profile = _profile_from_source_edges(entity_id, edges_by_head)
        if not any(profile[key] for key in ("candidate_causes", "morphologies", "locations")):
            continue
        rows.append(
            {
                "pattern_id": entity_id,
                "pattern_name": entity.name,
                "aliases": entity.aliases,
                **profile,
            }
        )
    return rows


def _deterministic_mvtec_profiles(
    entity_by_id: dict[str, CanonicalEntity],
    edges_by_head: dict[str, list[CanonicalEdge]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for object_id, entity in sorted(entity_by_id.items()):
        if entity.scenario != "mvtec" or entity.label != "Object":
            continue
        for edge in edges_by_head.get(object_id, []):
            if edge.relation not in {"HAS_ANOMALY", "HAS_DEFECT"}:
                continue
            defect = entity_by_id.get(edge.tail)
            if defect is None or defect.label not in {"Defect", "Anomaly", "Pattern"}:
                continue
            rows.append(
                {
                    "object_id": object_id,
                    "defect_id": defect.entity_id,
                    "defect_name": defect.name,
                    "aliases": defect.aliases,
                    **_profile_from_source_edges(defect.entity_id, edges_by_head),
                }
            )
    return rows


def _profile_from_source_edges(
    source_id: str,
    edges_by_head: dict[str, list[CanonicalEdge]],
) -> dict[str, Any]:
    candidate_causes: list[str] = []
    morphologies: list[str] = []
    locations: list[str] = []
    evidence_requirements: list[str] = []
    source_edge_ids: list[str] = []
    for edge in edges_by_head.get(source_id, []):
        if edge.relation in {"POSSIBLY_CAUSES", "HAS_PLAUSIBLE_CAUSE", "SUGGESTS_MECHANISM"}:
            candidate_causes.append(edge.tail)
        elif edge.relation == "HAS_MORPHOLOGY":
            morphologies.append(edge.tail)
        elif edge.relation == "OCCURS_ON":
            locations.append(edge.tail)
        elif edge.relation == "REQUIRES_EVIDENCE":
            evidence_requirements.append(edge.tail)
        source_edge_ids.append(edge.edge_id)
    return {
        "candidate_causes": sorted(set(candidate_causes)),
        "morphologies": sorted(set(morphologies)),
        "locations": sorted(set(locations)),
        "evidence_requirements": sorted(set(evidence_requirements)),
        "source_edge_ids": sorted(set(source_edge_ids)),
        "generation_source": "deterministic_kg_edges",
    }


def _merge_profile_payloads(
    deterministic: dict[str, Any],
    llm_payload: dict[str, Any],
) -> dict[str, Any]:
    profiles = json.loads(json.dumps(deterministic.get("profiles", {})))
    incoming = llm_payload.get("profiles", {}) if isinstance(llm_payload, dict) else {}
    if not isinstance(incoming, dict):
        return {"profiles": profiles}
    for scenario, scenario_payload in incoming.items():
        if not isinstance(scenario_payload, dict):
            continue
        scenario_profiles = profiles.setdefault(str(scenario), {})
        for key, rows in scenario_payload.items():
            if not isinstance(rows, list):
                continue
            existing = scenario_profiles.setdefault(str(key), [])
            existing.extend(row for row in rows if isinstance(row, dict))
            scenario_profiles[str(key)] = _dedupe_profile_rows(existing)
    return {"profiles": profiles}


def _dedupe_profile_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    output: list[dict[str, Any]] = []
    for row in rows:
        key = (
            str(row.get("fault_anchor_id") or row.get("pattern_id") or row.get("object_id") or ""),
            str(row.get("unit_id") or row.get("defect_id") or row.get("pattern_name") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(_normalize_profile_row(row))
    return output


def _normalize_profile_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    for key in (
        "fault_numbers",
        "support_targets",
        "diagnostic_variables",
        "observed_variables",
        "candidate_causes",
        "morphologies",
        "locations",
        "evidence_requirements",
        "source_card_ids",
        "source_edge_ids",
        "aliases",
    ):
        if key in normalized:
            normalized[key] = [
                str(value) for value in _as_list(normalized.get(key)) if value != ""
            ]
    return normalized


def _profile_counts(payload: dict[str, Any]) -> dict[str, int]:
    profiles = payload.get("profiles", {})
    return {
        "tep_fault_profiles": len(profiles.get("tep", {}).get("fault_profiles", [])),
        "tep_unit_observation_profiles": len(
            profiles.get("tep", {}).get("unit_observation_profiles", [])
        ),
        "wafer_pattern_profiles": len(profiles.get("wafer", {}).get("pattern_profiles", [])),
        "mvtec_object_defect_profiles": len(
            profiles.get("mvtec", {}).get("object_defect_profiles", [])
        ),
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _relation_hints(card: KnowledgeCard) -> list[RelationHint]:
    hints: list[RelationHint] = []
    for hint in card.relation_hints:
        if isinstance(hint, RelationHint):
            hints.append(hint)
            continue
        parsed = _parse_relation_hint_from_claim(hint, card)
        if parsed is not None:
            hints.append(parsed)
    return hints


def _edge_matches_type_constraints(
    edge: CanonicalEdge,
    entity_by_id: dict[str, CanonicalEntity],
) -> bool:
    if edge.head == edge.tail:
        return False
    allowed_targets = TARGET_TYPE_CONSTRAINTS.get(edge.relation)
    if not allowed_targets:
        return True
    target = entity_by_id.get(edge.tail)
    if target is None:
        return False
    return target.label in allowed_targets


def _resolve_entity_id(
    value: str,
    entity_by_id: dict[str, CanonicalEntity],
    scenario: str,
) -> str | None:
    if value in entity_by_id:
        return value
    pascal = _pascal_id(value)
    if pascal in entity_by_id:
        return pascal
    normalized = _normalize_key(value)
    for entity_id, entity in entity_by_id.items():
        if entity.scenario != scenario and entity.scenario != "shared":
            continue
        if _normalize_key(entity_id) == normalized or _normalize_key(entity.name) == normalized:
            return entity_id
        if any(_normalize_key(alias) == normalized for alias in entity.aliases):
            return entity_id
    return None


def _source_units_for_cards(cards: list[KnowledgeCard], card_ids: list[str]) -> list[str]:
    wanted = set(card_ids)
    return sorted({card.source_unit_id for card in cards if card.card_id in wanted})


def _card_ids_for_scenario(cards: list[KnowledgeCard], scenario: str) -> list[str]:
    return sorted(card.card_id for card in cards if card.scenario == scenario)


def _first_card_for_ids(
    cards: list[KnowledgeCard],
    card_ids: list[str],
    scenario: str,
) -> KnowledgeCard:
    wanted = set(card_ids)
    for card in cards:
        if card.card_id in wanted:
            return card
    for card in cards:
        if card.scenario == scenario:
            return card
    if not cards:
        raise ValueError("cannot extract entities from an empty card set")
    return cards[0]


def _scenario_from_card_ids(cards: list[KnowledgeCard], card_ids: Any) -> str:
    wanted = {str(value) for value in _as_list(card_ids)}
    for card in cards:
        if card.card_id in wanted:
            return card.scenario
    return cards[0].scenario if cards else "shared"


def _edge_source(card_ids: list[str]) -> str:
    if not card_ids:
        return "llm_auto"
    return "cards:" + "|".join(card_ids[:8])


def _edge_id(head: str, relation: str, tail: str, scenario: str) -> str:
    return f"edge_{_short_hash('|'.join((head, relation, tail, scenario)), length=16)}"


def _llm_metrics(llm_client: SourceKGLLMClient) -> dict[str, int]:
    return {
        "llm_calls": int(getattr(llm_client, "calls", 0) or 0),
        "llm_input_tokens": int(getattr(llm_client, "input_tokens", 0) or 0),
        "llm_output_tokens": int(getattr(llm_client, "output_tokens", 0) or 0),
        "llm_total_tokens": int(getattr(llm_client, "total_tokens", 0) or 0),
    }


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _required_field_coverage(artifacts: SourceKGArtifacts) -> dict[str, Any]:
    entity_fields = ["entity_id", "name", "label", "scenario"]
    edge_fields = ["head", "relation", "tail", "scenario", "source", "evidence", "review_status"]
    return {
        "entities": _coverage(artifacts.entities, entity_fields),
        "edges": _coverage(artifacts.edges, edge_fields),
    }


def _coverage(records: list[Any], fields: list[str]) -> dict[str, float]:
    if not records:
        return {field: 1.0 for field in fields}
    coverage: dict[str, float] = {}
    for field in fields:
        present = sum(1 for record in records if bool(getattr(record, field)))
        coverage[field] = round(present / len(records), 4)
    return coverage


def _artifact_sizes(paths: SourceKGArtifactPaths) -> dict[str, int]:
    artifact_paths = {
        "source_units": paths.source_units,
        "knowledge_cards": paths.knowledge_cards,
        "entities": paths.entities,
        "edges": paths.edges,
        "nodes_csv": paths.nodes_csv,
        "edges_csv": paths.edges_csv,
        "qa_report": paths.qa_report,
        "domain_profiles": paths.domain_profiles,
        "domain_profile_report": paths.domain_profile_report,
        "domain_profiles_manifest": paths.domain_profiles_manifest,
        "runtime_views_manifest": paths.runtime_views_manifest,
    }
    return {
        name: path.stat().st_size
        for name, path in artifact_paths.items()
        if path.exists()
    }


def _parse_options(parts: list[str]) -> dict[str, str]:
    options: dict[str, str] = {}
    for part in parts:
        if not part:
            continue
        if "=" not in part:
            raise ValueError(f"hint option must use key=value syntax: {part}")
        key, value = part.split("=", 1)
        options[key.strip().lower()] = value.strip()
    return options


def _infer_unit_scenario(text: str, default_scenario: str) -> str:
    for line in text.splitlines()[:10]:
        match = re.match(r"\s*scenario\s*:\s*([a-zA-Z0-9_-]+)\s*$", line, flags=re.I)
        if match:
            return _scenario(match.group(1))
    return _scenario(default_scenario)


def _scenario(value: str) -> Scenario:
    normalized = value.strip().lower()
    if normalized == "generic":
        normalized = "shared"
    if normalized not in VALID_SCENARIOS:
        raise ValueError(f"invalid scenario: {value}")
    return normalized  # type: ignore[return-value]


def _relation_name(value: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", value)
    if not words:
        raise ValueError("relation name cannot be empty")
    return "_".join(word.upper() for word in words)


def _pascal_id(value: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", value)
    if not words:
        return "Entity"
    entity_id = "".join(word[:1].upper() + word[1:] for word in words)
    if entity_id[0].isdigit():
        entity_id = f"Entity{entity_id}"
    return entity_id


def _infer_entity_label(entity_id: str) -> str:
    label_suffixes = (
        ("Object", "Object"),
        ("Defect", "Defect"),
        ("Pattern", "Pattern"),
        ("Morphology", "Morphology"),
        ("Location", "Location"),
        ("Cause", "CandidateCause"),
        ("Mechanism", "Mechanism"),
        ("Evidence", "EvidenceSource"),
        ("Fault", "Fault"),
        ("ProcessUnit", "ProcessUnit"),
        ("Unit", "ProcessUnit"),
        ("Variable", "Variable"),
        ("Anomaly", "Anomaly"),
    )
    for suffix, label in label_suffixes:
        if entity_id.endswith(suffix):
            return label
    return "Concept"


def _stable_entity_id(
    base_id: str,
    key: tuple[str, str],
    entity_id_to_key: dict[str, tuple[str, str]],
    scenario: str,
) -> str:
    candidate = _pascal_id(base_id)
    existing_key = entity_id_to_key.get(candidate)
    if existing_key is None or existing_key == key:
        return candidate
    prefix = "Shared" if scenario == "shared" else _pascal_id(scenario)
    candidate = f"{prefix}{candidate}"
    existing_key = entity_id_to_key.get(candidate)
    if existing_key is None or existing_key == key:
        return candidate
    return f"{candidate}{_short_hash('|'.join(key), length=6)}"


def _source_id(path: Path) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", path.stem.lower()).strip("_")
    return slug or f"source_{_short_hash(path.as_posix(), length=8)}"


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _split_aliases(value: str) -> list[str]:
    if not value:
        return []
    return sorted({part.strip() for part in re.split(r"[;,]", value) if part.strip()})


def _first_nonempty_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _path_sort_key(path: Path) -> str:
    return path.as_posix()


def _short_hash(value: str, *, length: int = 12) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:length]


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _format_float(value: float) -> str:
    return f"{value:.4f}".rstrip("0").rstrip(".")
