"""Candidate entity extraction utilities."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from kgtracevis.kg.graph import KGNode, split_aliases


@dataclass(frozen=True)
class CandidateEntity:
    """A source-constrained candidate KG node."""

    id: str
    name: str
    label: str
    scenario: str
    aliases: tuple[str, ...] = ()
    description: str = ""
    source: str = ""
    evidence: str = ""

    def to_kg_node(self) -> KGNode:
        """Convert the candidate to the KG node CSV contract."""
        return KGNode(
            id=self.id,
            name=self.name,
            label=self.label,
            scenario=self.scenario,
            aliases=self.aliases,
            description=self.description,
        )


def extract_candidate_entities(
    records: Iterable[Mapping[str, Any]],
    *,
    source_id: str = "",
) -> list[CandidateEntity]:
    """Extract candidate entities from structured source records.

    Records must explicitly provide entity fields. This helper does not infer
    industrial facts from prose.
    """
    entities: list[CandidateEntity] = []
    for record in records:
        entity = _entity_from_record(record, source_id=source_id)
        if entity is not None:
            entities.append(entity)
    return entities


def _entity_from_record(
    record: Mapping[str, Any],
    *,
    source_id: str,
) -> CandidateEntity | None:
    entity_id = _string_value(record, "id", "entity_id", "node_id")
    name = _string_value(record, "name", "entity_name", "node_name")
    label = _string_value(record, "label", "entity_label", "node_label", "type")
    scenario = _string_value(record, "scenario")

    if not any((entity_id, name, label, scenario)):
        return None
    missing = [
        field
        for field, value in {
            "id/entity_id/node_id": entity_id,
            "name/entity_name/node_name": name,
            "label/entity_label/node_label/type": label,
            "scenario": scenario,
        }.items()
        if not value
    ]
    if missing:
        raise ValueError(f"candidate entity missing required fields: {', '.join(missing)}")

    alias_value = _string_value(record, "aliases", "alias")
    aliases = tuple(dict.fromkeys(split_aliases(alias_value)))
    source = _string_value(record, "source", "source_id") or source_id
    if not source:
        raise ValueError("candidate entity missing required source/source_id")
    evidence = _string_value(record, "evidence") or _compact_json(record)
    return CandidateEntity(
        id=entity_id,
        name=name,
        label=label,
        scenario=scenario,
        aliases=aliases,
        description=_string_value(record, "description"),
        source=source,
        evidence=evidence,
    )


def _string_value(record: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _compact_json(record: Mapping[str, Any]) -> str:
    return json.dumps(dict(record), sort_keys=True, separators=(",", ":"))
