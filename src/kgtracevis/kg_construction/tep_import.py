"""TEP_KG import extractors."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from kgtracevis.kg_construction.draft import (
    DraftEntity,
    DraftKG,
    DraftRelation,
    KGConstructionSource,
)


class TepSemanticLiftExtractor:
    """Import TEP_KG semantic-lift JSONL rows into KGTraceVis draft KG rows."""

    name = "tep_semantic_lift"
    version = "v1"
    supported_source_types: tuple[str, ...] = ("tep_semantic_lift",)

    def extract(self, source: KGConstructionSource) -> DraftKG:
        """Extract draft KG rows from TEP semantic-lift nodes and edges."""
        nodes_path, edges_path = _resolve_semantic_lift_paths(source)
        node_rows = _read_jsonl(nodes_path)
        edge_rows = _read_jsonl(edges_path)
        id_map = {
            str(row["node_id"]): tep_external_id_to_kg_id(
                str(row["node_id"]),
                label=str(row.get("entity_type") or "Other"),
            )
            for row in node_rows
        }
        entities = tuple(
            _draft_entity_from_row(row, source=source, node_id=id_map[str(row["node_id"])])
            for row in node_rows
        )
        relations = tuple(
            relation
            for row in edge_rows
            if (
                relation := _draft_relation_from_row(row, source=source, id_map=id_map)
            )
            is not None
        )
        return DraftKG(entities=entities, relations=relations)


class TepVariableMappingExtractor:
    """Import TEP 52-channel mapping rows into KGTraceVis draft KG rows."""

    name = "tep_variable_mapping"
    version = "v1"
    supported_source_types: tuple[str, ...] = ("tep_variable_mapping",)

    def extract(self, source: KGConstructionSource) -> DraftKG:
        """Extract variable entities and alias relations from TEP mapping rows."""
        if source.path is None:
            raise ValueError("TEP variable mapping extraction requires source.path")
        rows = _read_records(source.path)
        entities: list[DraftEntity] = []
        relations: list[DraftRelation] = []
        for row in rows:
            channel = str(row.get("tep_channel") or "").strip()
            kg_entity_id = str(row.get("kg_entity_id") or "").strip()
            if not channel or not kg_entity_id:
                continue
            node_id = tep_external_id_to_kg_id(kg_entity_id, label="Variable")
            alternate_ids = _list_values(row.get("alternate_entity_ids"))
            aliases = tuple(dict.fromkeys([kg_entity_id, channel]))
            entities.append(
                DraftEntity(
                    draft_id=f"{source.source_id}:entity:{channel}",
                    source_id=source.source_id,
                    extractor_name=self.name,
                    extractor_version=self.version,
                    scenario=source.scenario or "tep",
                    entity_id_suggestion=node_id,
                    name=_variable_display_name(channel, kg_entity_id),
                    label="Variable",
                    aliases=aliases,
                    description="TEP 52-channel variable mapping",
                    evidence=_variable_mapping_evidence(row),
                    confidence=0.96,
                    metadata={
                        "external_id": kg_entity_id,
                        "tep_channel": channel,
                        "sequence_column": str(row.get("sequence_column") or channel),
                        "mapping_source": str(row.get("mapping_source") or ""),
                    },
                )
            )
            for alternate_id in alternate_ids:
                alternate_node_id = tep_external_id_to_kg_id(alternate_id, label="Variable")
                entities.append(
                    DraftEntity(
                        draft_id=f"{source.source_id}:entity:{channel}:alias:{alternate_id}",
                        source_id=source.source_id,
                        extractor_name=self.name,
                        extractor_version=self.version,
                        scenario=source.scenario or "tep",
                        entity_id_suggestion=alternate_node_id,
                        name=alternate_id,
                        label="Variable",
                        aliases=(alternate_id,),
                        description="TEP alternate variable mapping alias",
                        evidence=_variable_mapping_evidence(row),
                        confidence=0.96,
                        metadata={
                            "external_id": alternate_id,
                            "canonical_external_id": kg_entity_id,
                            "tep_channel": channel,
                            "mapping_source": str(row.get("mapping_source") or ""),
                        },
                    )
                )
                relations.append(
                    DraftRelation(
                        draft_id=f"{source.source_id}:relation:{alternate_id}->{kg_entity_id}",
                        source_id=source.source_id,
                        extractor_name=self.name,
                        extractor_version=self.version,
                        scenario=source.scenario or "tep",
                        head=alternate_node_id,
                        relation="ALIGNS_TO",
                        tail=node_id,
                        evidence=_variable_mapping_evidence(row),
                        confidence=0.96,
                        metadata={
                            "head_external_id": alternate_id,
                            "tail_external_id": kg_entity_id,
                            "relation_family": "ALIGNMENT",
                            "propagation_enabled": False,
                        },
                    )
                )
        return DraftKG(entities=tuple(entities), relations=tuple(relations))


def tep_external_id_to_kg_id(external_id: str, *, label: str) -> str:
    """Map a TEP_KG external ID to KGTraceVis PascalCase node ID."""
    if ":" in external_id:
        _, value = external_id.split(":", 1)
    else:
        value = external_id
    words = re.findall(r"[A-Za-z0-9]+", value)
    label_words = re.findall(r"[A-Za-z0-9]+", label)
    if not words:
        words = ["tep", "entity", hashlib.sha1(external_id.encode("utf-8")).hexdigest()[:8]]
    if label_words and [word.lower() for word in words[-len(label_words):]] != [
        word.lower() for word in label_words
    ]:
        words.extend(label_words)
    return "".join(word[:1].upper() + word[1:] for word in words)


def _resolve_semantic_lift_paths(source: KGConstructionSource) -> tuple[Path, Path]:
    nodes_path = source.metadata.get("nodes_path")
    edges_path = source.metadata.get("edges_path")
    if nodes_path and edges_path:
        return Path(str(nodes_path)), Path(str(edges_path))
    if source.path is None:
        raise ValueError("TEP semantic lift extraction requires source.path or metadata paths")
    base = source.path
    if base.is_dir():
        return base / "semantic_lift_nodes.jsonl", base / "semantic_lift_edges.jsonl"
    raise ValueError(
        "TEP semantic lift source.path must be a directory when metadata paths are absent"
    )


def _draft_entity_from_row(
    row: Mapping[str, Any],
    *,
    source: KGConstructionSource,
    node_id: str,
) -> DraftEntity:
    external_id = str(row["node_id"])
    label = str(row.get("entity_type") or "Other")
    aliases = _aliases_from_row(row)
    evidence = _entity_evidence(row)
    return DraftEntity(
        draft_id=f"{source.source_id}:entity:{external_id}",
        source_id=source.source_id,
        extractor_name=TepSemanticLiftExtractor.name,
        extractor_version=TepSemanticLiftExtractor.version,
        scenario=source.scenario or "tep",
        entity_id_suggestion=node_id,
        name=str(row.get("name") or external_id),
        label=label,
        aliases=aliases,
        description=str(row.get("summary") or "TEP semantic-lift node"),
        evidence=evidence,
        confidence=_float_or_default(row.get("lift_confidence"), 0.82),
        metadata={
            "external_id": external_id,
            "tep_channel": str(row.get("tep_channel") or ""),
            "variable_role": str(row.get("variable_role") or ""),
        },
    )


def _draft_relation_from_row(
    row: Mapping[str, Any],
    *,
    source: KGConstructionSource,
    id_map: Mapping[str, str],
) -> DraftRelation | None:
    head_external = str(row.get("head_id") or row.get("source") or "")
    tail_external = str(row.get("tail_id") or row.get("target") or "")
    if head_external not in id_map or tail_external not in id_map:
        return None
    relation = str(row.get("relation") or "").strip()
    if not relation:
        return None
    edge_id = str(row.get("edge_id") or f"{head_external}|{relation}|{tail_external}")
    return DraftRelation(
        draft_id=f"{source.source_id}:relation:{edge_id}",
        source_id=source.source_id,
        extractor_name=TepSemanticLiftExtractor.name,
        extractor_version=TepSemanticLiftExtractor.version,
        scenario=source.scenario or "tep",
        head=id_map[head_external],
        relation=relation,
        tail=id_map[tail_external],
        evidence=_relation_evidence(row),
        confidence=_float_or_default(row.get("confidence"), 0.6),
        metadata={
            "external_edge_id": edge_id,
            "head_external_id": head_external,
            "tail_external_id": tail_external,
            "relation_family": str(row.get("relation_family") or ""),
            "propagation_enabled": _bool_value(row.get("propagation_enabled", False)),
        },
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _read_records(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        return _read_jsonl(path)
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [dict(row) for row in data if isinstance(row, Mapping)]
        if isinstance(data, Mapping) and isinstance(data.get("records"), list):
            return [dict(row) for row in data["records"] if isinstance(row, Mapping)]
        raise ValueError(f"{path} must contain a list or records list")
    if suffix == ".csv":
        with path.open(newline="", encoding="utf-8") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    raise ValueError(f"unsupported TEP record file type: {path}")


def _aliases_from_row(row: Mapping[str, Any]) -> tuple[str, ...]:
    values: list[str] = [str(row.get("node_id") or ""), str(row.get("entity_id") or "")]
    tep_channel = str(row.get("tep_channel") or "")
    if tep_channel:
        values.append(tep_channel)
    return tuple(dict.fromkeys(value for value in values if value))


def _entity_evidence(row: Mapping[str, Any]) -> str:
    provenance_ids = _list_values(row.get("provenance_ids"))
    return "; ".join(
        part
        for part in [
            f"TEP semantic-lift node {row.get('node_id')}",
            f"provenance_ids={','.join(provenance_ids)}" if provenance_ids else "",
            f"tep_channel={row.get('tep_channel')}" if row.get("tep_channel") else "",
        ]
        if part
    )


def _relation_evidence(row: Mapping[str, Any]) -> str:
    provenance_ids = _list_values(row.get("provenance_ids"))
    support_triple_ids = _list_values(row.get("support_triple_ids"))
    raw_relations = _list_values(row.get("raw_relations"))
    return "; ".join(
        part
        for part in [
            f"TEP semantic-lift edge {row.get('edge_id')}",
            f"relation_family={row.get('relation_family')}" if row.get("relation_family") else "",
            f"provenance_ids={','.join(provenance_ids)}" if provenance_ids else "",
            f"support_triple_ids={','.join(support_triple_ids)}" if support_triple_ids else "",
            f"raw_relations={','.join(raw_relations)}" if raw_relations else "",
        ]
        if part
    )


def _variable_display_name(channel: str, external_id: str) -> str:
    if channel.startswith("xmeas_"):
        return f"{channel.upper()} process measurement"
    if channel.startswith("xmv_"):
        return f"{channel.upper()} manipulated variable"
    return external_id


def _variable_mapping_evidence(row: Mapping[str, Any]) -> str:
    parts = [
        f"TEP channel mapping {row.get('tep_channel')}",
        f"kg_entity_id={row.get('kg_entity_id')}",
        f"sequence_column={row.get('sequence_column')}",
        f"mapping_source={row.get('mapping_source')}",
    ]
    notes = str(row.get("notes") or "").strip()
    if notes:
        parts.append(notes)
    return "; ".join(part for part in parts if part and not part.endswith("=None"))


def _list_values(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [
            part.strip()
            for part in value.replace(";", "|").replace(",", "|").split("|")
            if part.strip()
        ]
    if isinstance(value, Iterable):
        return [str(part).strip() for part in value if str(part).strip()]
    return [str(value).strip()]


def _float_or_default(value: object, default: float) -> float:
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    return float(text)


def _bool_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "y"}
