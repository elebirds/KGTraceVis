"""Artifact models for the source KG compiler."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

Scenario = Literal["shared", "mvtec", "tep", "wafer"]
ReviewStatus = Literal["auto", "reviewed", "rejected"]

VALID_SCENARIOS: set[str] = {"shared", "mvtec", "tep", "wafer"}
VALID_REVIEW_STATUSES: set[str] = {"auto", "reviewed", "rejected"}

NODE_CSV_COLUMNS = ["id", "name", "label", "scenario", "aliases", "description"]
EDGE_CSV_COLUMNS = [
    "head",
    "relation",
    "tail",
    "scenario",
    "source",
    "evidence",
    "confidence",
    "weight",
    "review_status",
    "feedback_count",
    "accepted_count",
    "rejected_count",
]


class SourceUnit(BaseModel):
    """A standardized source file unit handed to the compiler."""

    unit_id: str
    source_id: str
    scenario: Scenario
    material_path: str
    content_text: str
    source_span: dict[str, Any]
    content_hash: str
    parser_metadata: dict[str, Any]


class EntityHint(BaseModel):
    """An explicit entity hint parsed from a source unit."""

    name: str
    label: str = "Concept"
    entity_id: str | None = None
    scenario: Scenario
    aliases: list[str] = Field(default_factory=list)
    description: str = ""


class RelationHint(BaseModel):
    """An explicit relation hint parsed from a source unit."""

    head: str
    relation: str
    tail: str
    scenario: Scenario
    confidence: float = 0.75
    source: str
    evidence: str
    head_id: str | None = None
    tail_id: str | None = None
    head_label: str = "Concept"
    tail_label: str = "Concept"
    head_aliases: list[str] = Field(default_factory=list)
    tail_aliases: list[str] = Field(default_factory=list)
    review_status: ReviewStatus = "auto"


class KnowledgeCard(BaseModel):
    """A reusable semantic card derived from one source unit."""

    card_id: str
    source_unit_id: str
    scenario: Scenario
    claim: str
    entities_mentioned: list[str]
    relation_hints: list[RelationHint | str] = Field(default_factory=list)
    entity_hints: list[EntityHint] = Field(default_factory=list)
    evidence_text: str
    source_path: str
    content_hash: str


class CanonicalEntity(BaseModel):
    """A canonical reusable KG entity."""

    entity_id: str
    name: str
    label: str
    scenario: Scenario
    aliases: list[str] = Field(default_factory=list)
    description: str = ""
    source_card_ids: list[str] = Field(default_factory=list)
    source_unit_ids: list[str] = Field(default_factory=list)


class CanonicalEdge(BaseModel):
    """A canonical reusable KG edge with review-compatible provenance."""

    edge_id: str
    head: str
    relation: str
    tail: str
    scenario: Scenario
    source: str
    evidence: str
    source_card_ids: list[str]
    source_unit_ids: list[str]
    confidence: float
    weight: float
    review_status: ReviewStatus
    feedback_count: int = 0
    accepted_count: int = 0
    rejected_count: int = 0


class SourceKGArtifacts(BaseModel):
    """In-memory compiler artifact bundle before export."""

    source_units: list[SourceUnit]
    knowledge_cards: list[KnowledgeCard]
    entities: list[CanonicalEntity]
    edges: list[CanonicalEdge]


class SourceKGArtifactPaths(BaseModel):
    """Paths written by the source KG compiler."""

    output_dir: Path
    source_units: Path
    knowledge_cards: Path
    entities: Path
    edges: Path
    nodes_csv: Path
    edges_csv: Path
    qa_report: Path
    validation_report: Path
    domain_profiles: Path
    domain_profile_report: Path
    domain_profiles_manifest: Path
    runtime_views_manifest: Path


class SourceKGLLMClient(Protocol):
    """Minimal OpenAI-compatible JSON completion interface used by the compiler."""

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> str:
        """Return raw model text intended to be JSON."""
        ...

    def repair_json(self, broken_json: str, error: str) -> str:
        """Return repaired JSON text for a failed parse."""
        ...
