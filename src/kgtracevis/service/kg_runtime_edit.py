"""Runtime KG edit service backed by Neo4j."""

from __future__ import annotations

import re
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from kgtracevis.kg.graph import KGEdge, KGNode
from kgtracevis.kg.import_neo4j import RELATION_PATTERN, resolve_neo4j_config
from kgtracevis.kg.neo4j_repository import Neo4jKGRepository

ScenarioName = Literal["shared", "mvtec", "tep", "wafer"]
ReviewStatus = Literal["auto", "reviewed", "rejected"]

CLAIM_BOUNDARY = (
    "runtime KG edits mutate Neo4j only; tracked CSV seed files are unchanged "
    "and a later explicit CSV import may overwrite matching Neo4j rows"
)


class RuntimeKGRepository(Protocol):
    """Writable runtime KG repository contract used by the edit service."""

    def upsert_node(self, node: KGNode) -> KGNode:
        """Create or update one KG node."""

    def delete_node(self, node_id: str) -> dict[str, int]:
        """Delete one KG node and return delete counts."""

    def upsert_edge(self, edge: KGEdge) -> KGEdge:
        """Create or update one KG edge."""

    def update_edge_confidence(self, edge_id: str, confidence: float) -> KGEdge:
        """Update one edge confidence."""

    def delete_edge(self, edge_id: str) -> dict[str, int]:
        """Delete one KG edge and return delete counts."""


class RuntimeKGNodeRequest(BaseModel):
    """Request body for creating or updating a runtime KG node."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    label: str
    scenario: ScenarioName
    aliases: list[str] = Field(default_factory=list)
    description: str = ""

    @model_validator(mode="after")
    def validate_node(self) -> RuntimeKGNodeRequest:
        """Require stable node identity and display metadata."""
        _require_text(self.id, "id")
        _require_text(self.name, "name")
        _require_text(self.label, "label")
        self.aliases = [_clean_text(alias) for alias in self.aliases if alias.strip()]
        return self


class RuntimeKGEdgeRequest(BaseModel):
    """Request body for creating or updating a runtime KG edge."""

    model_config = ConfigDict(extra="forbid")

    head: str
    relation: str
    tail: str
    scenario: ScenarioName
    source: str
    evidence: str
    confidence: float = Field(ge=0.0, le=1.0)
    review_status: ReviewStatus = "reviewed"
    feedback_count: int = Field(default=0, ge=0)
    accepted_count: int = Field(default=0, ge=0)
    rejected_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_edge(self) -> RuntimeKGEdgeRequest:
        """Require source-constrained, schema-compatible edge edits."""
        _require_text(self.head, "head")
        _require_text(self.tail, "tail")
        _require_text(self.source, "source")
        _require_text(self.evidence, "evidence")
        self.relation = self.relation.strip().upper()
        if not RELATION_PATTERN.fullmatch(self.relation):
            raise ValueError("relation must be uppercase snake case")
        return self


class RuntimeKGEdgeConfidenceRequest(BaseModel):
    """Request body for updating an edge confidence."""

    model_config = ConfigDict(extra="forbid")

    confidence: float = Field(ge=0.0, le=1.0)


class RuntimeKGNodeResponse(BaseModel):
    """Response for one edited runtime KG node."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["upserted"]
    node: dict[str, Any]
    claim_boundary: str = CLAIM_BOUNDARY


class RuntimeKGEdgeResponse(BaseModel):
    """Response for one edited runtime KG edge."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["upserted", "updated"]
    edge: dict[str, Any]
    claim_boundary: str = CLAIM_BOUNDARY


class RuntimeKGDeleteResponse(BaseModel):
    """Response for one runtime KG delete operation."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["deleted"]
    target_type: Literal["node", "edge"]
    target_id: str
    deleted_count: int
    deleted_relationship_count: int = 0
    claim_boundary: str = CLAIM_BOUNDARY


def upsert_runtime_kg_node(
    request: RuntimeKGNodeRequest,
    *,
    repository: RuntimeKGRepository | None = None,
) -> RuntimeKGNodeResponse:
    """Create or update one runtime KG node in Neo4j."""
    active_repository = repository or _runtime_repository()
    try:
        node = active_repository.upsert_node(_node_from_request(request))
        return RuntimeKGNodeResponse(status="upserted", node=_node_payload(node))
    finally:
        _close_owned_repository(active_repository, repository)


def delete_runtime_kg_node(
    node_id: str,
    *,
    repository: RuntimeKGRepository | None = None,
) -> RuntimeKGDeleteResponse:
    """Delete one runtime KG node and its incident relationships."""
    active_repository = repository or _runtime_repository()
    try:
        counts = active_repository.delete_node(_clean_target_id(node_id))
        deleted = int(counts.get("deleted_node_count") or 0)
        if deleted < 1:
            raise ValueError(f"unknown KG node: {node_id}")
        return RuntimeKGDeleteResponse(
            status="deleted",
            target_type="node",
            target_id=node_id,
            deleted_count=deleted,
            deleted_relationship_count=int(
                counts.get("deleted_relationship_count") or 0
            ),
        )
    finally:
        _close_owned_repository(active_repository, repository)


def upsert_runtime_kg_edge(
    request: RuntimeKGEdgeRequest,
    *,
    repository: RuntimeKGRepository | None = None,
) -> RuntimeKGEdgeResponse:
    """Create or update one source-constrained runtime KG edge in Neo4j."""
    active_repository = repository or _runtime_repository()
    try:
        edge = active_repository.upsert_edge(_edge_from_request(request))
        return RuntimeKGEdgeResponse(status="upserted", edge=edge.model_dump())
    finally:
        _close_owned_repository(active_repository, repository)


def update_runtime_kg_edge_confidence(
    edge_id: str,
    request: RuntimeKGEdgeConfidenceRequest,
    *,
    repository: RuntimeKGRepository | None = None,
) -> RuntimeKGEdgeResponse:
    """Update one runtime KG edge confidence and derived weight."""
    active_repository = repository or _runtime_repository()
    try:
        edge = active_repository.update_edge_confidence(
            _clean_target_id(edge_id),
            request.confidence,
        )
        return RuntimeKGEdgeResponse(status="updated", edge=edge.model_dump())
    finally:
        _close_owned_repository(active_repository, repository)


def delete_runtime_kg_edge(
    edge_id: str,
    *,
    repository: RuntimeKGRepository | None = None,
) -> RuntimeKGDeleteResponse:
    """Delete runtime KG edge relationships by stable edge ID."""
    active_repository = repository or _runtime_repository()
    try:
        counts = active_repository.delete_edge(_clean_target_id(edge_id))
        deleted = int(counts.get("deleted_edge_count") or 0)
        if deleted < 1:
            raise ValueError(f"unknown KG edge: {edge_id}")
        return RuntimeKGDeleteResponse(
            status="deleted",
            target_type="edge",
            target_id=edge_id,
            deleted_count=deleted,
        )
    finally:
        _close_owned_repository(active_repository, repository)


def _runtime_repository() -> Neo4jKGRepository:
    return Neo4jKGRepository.connect(resolve_neo4j_config())


def _close_owned_repository(
    active_repository: RuntimeKGRepository,
    injected_repository: RuntimeKGRepository | None,
) -> None:
    if injected_repository is not None:
        return
    close = getattr(active_repository, "close", None)
    if callable(close):
        close()


def _node_from_request(request: RuntimeKGNodeRequest) -> KGNode:
    return KGNode(
        id=request.id.strip(),
        name=request.name.strip(),
        label=request.label.strip(),
        scenario=request.scenario,
        aliases=tuple(request.aliases),
        description=request.description.strip(),
    )


def _edge_from_request(request: RuntimeKGEdgeRequest) -> KGEdge:
    confidence = round(request.confidence, 6)
    return KGEdge(
        head=request.head.strip(),
        relation=request.relation.strip().upper(),
        tail=request.tail.strip(),
        scenario=request.scenario,
        source=request.source.strip(),
        evidence=request.evidence.strip(),
        confidence=confidence,
        weight=round(1.0 - confidence, 6),
        review_status=request.review_status,
        feedback_count=request.feedback_count,
        accepted_count=request.accepted_count,
        rejected_count=request.rejected_count,
    )


def _node_payload(node: KGNode) -> dict[str, Any]:
    return {
        "id": node.id,
        "name": node.name,
        "label": node.label,
        "scenario": node.scenario,
        "aliases": list(node.aliases),
        "description": node.description,
    }


def _require_text(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def _clean_target_id(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("target id must not be empty")
    return cleaned
