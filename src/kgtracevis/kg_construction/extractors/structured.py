"""Structured source record extractor."""

from __future__ import annotations

from kgtracevis.kg_construction.draft import (
    DraftEntity,
    DraftKG,
    DraftRelation,
    KGConstructionSource,
)
from kgtracevis.kg_construction.extractors.base import ExtractorRegistry
from kgtracevis.kg_construction.source_loader import load_structured_records


class StructuredRecordExtractor:
    """Extractor for explicit structured entity/relation draft rows."""

    name = "structured_record"
    version = "v1"
    supported_source_types: tuple[str, ...] = ("structured_records", "manual_table")

    def extract(self, source: KGConstructionSource) -> DraftKG:
        """Extract draft KG rows from CSV, JSON, or JSONL records."""
        if source.path is None:
            raise ValueError("structured record extraction requires source.path")
        records = load_structured_records(source.path)
        entities: list[DraftEntity] = []
        relations: list[DraftRelation] = []
        for index, record in enumerate(records, start=1):
            source_id = str(record.get("source") or record.get("source_id") or source.source_id)
            scenario = str(record.get("scenario") or source.scenario)
            evidence = str(record.get("evidence") or f"{source.path}:{index}")
            entity_id = str(
                record.get("id") or record.get("entity_id") or record.get("node_id") or ""
            )
            entity_name = str(
                record.get("name")
                or record.get("entity_name")
                or record.get("node_name")
                or ""
            )
            entity_label = str(
                record.get("label") or record.get("entity_label") or record.get("node_label") or ""
            )
            if entity_id and entity_name and entity_label:
                entities.append(
                    DraftEntity(
                        draft_id=f"{source.source_id}:entity:{index}",
                        source_id=source_id,
                        extractor_name=self.name,
                        extractor_version=self.version,
                        scenario=scenario,
                        entity_id_suggestion=entity_id,
                        canonical_id=str(record.get("canonical_id") or ""),
                        name=entity_name,
                        label=entity_label,
                        aliases=_split_aliases(
                            str(record.get("aliases") or record.get("alias") or "")
                        ),
                        description=str(record.get("description") or ""),
                        evidence=evidence,
                        confidence=_float_or_default(record.get("confidence"), 0.6),
                        metadata={
                            key: value
                            for key, value in record.items()
                            if key.startswith("metadata.")
                            or key
                            in {
                                "external_id",
                                "external_entity_id",
                                "relation_family",
                                "root_candidate",
                                "observable",
                            }
                        },
                    )
                )

            head = str(
                record.get("head") or record.get("subject") or record.get("source_node") or ""
            )
            relation = str(
                record.get("relation")
                or record.get("predicate")
                or record.get("edge_type")
                or ""
            )
            tail = str(
                record.get("tail") or record.get("object") or record.get("target_node") or ""
            )
            if head and relation and tail:
                relations.append(
                    DraftRelation(
                        draft_id=f"{source.source_id}:relation:{index}",
                        source_id=source_id,
                        extractor_name=self.name,
                        extractor_version=self.version,
                        scenario=scenario,
                        head=head,
                        relation=relation,
                        tail=tail,
                        evidence=evidence,
                        confidence=_float_or_default(record.get("confidence"), 0.6),
                        metadata={
                            key: value
                            for key, value in record.items()
                            if key
                            in {
                                "relation_family",
                                "propagation_enabled",
                                "propagation_direction",
                                "propagation_priority",
                                "attenuation",
                                "edge_weight",
                                "task_view",
                                "external_edge_id",
                                "root_candidate",
                                "observable",
                            }
                            or key.startswith("metadata.")
                        },
                    )
                )
        return DraftKG(entities=tuple(entities), relations=tuple(relations))


def default_extractor_registry() -> ExtractorRegistry:
    """Return the default source-to-KG extractor registry."""
    return ExtractorRegistry([StructuredRecordExtractor()])


def _split_aliases(value: str) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(
        part.strip()
        for part in value.replace(";", "|").replace(",", "|").split("|")
        if part.strip()
    )


def _float_or_default(value: object, default: float) -> float:
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    return float(text)
