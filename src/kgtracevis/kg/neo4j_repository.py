"""Scenario-aware Neo4j runtime repository for KG queries."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Protocol, cast

from kgtracevis.kg.graph import (
    KGEdge,
    KGNode,
    KnowledgeGraph,
    LinkCandidate,
    _match_score,
    split_aliases,
)
from kgtracevis.kg.import_neo4j import RELATION_PATTERN, Neo4jConfig

NODE_QUERY = """
MATCH (node:KGEntity)
WHERE node.scenario IN $scenarios
RETURN node.id AS id,
       node.name AS name,
       node.entity_label AS label,
       node.scenario AS scenario,
       node.aliases AS aliases,
       node.description AS description
"""
HAS_EDGE_QUERY = """
MATCH (:KGEntity {{id: $head}})-[rel:`{relation}`]->(:KGEntity {{id: $tail}})
WHERE rel.scenario IN $scenarios
RETURN rel.edge_id AS edge_id
LIMIT 1
"""
OUTGOING_QUERY = """
MATCH (:KGEntity {{id: $head}})-[rel{relation_clause}]->(tail:KGEntity)
WHERE rel.scenario IN $scenarios
RETURN tail.id AS tail,
       type(rel) AS relation,
       rel.scenario AS scenario,
       rel.source AS source,
       rel.evidence AS evidence,
       rel.confidence AS confidence,
       rel.weight AS weight,
       rel.review_status AS review_status,
       rel.feedback_count AS feedback_count,
       rel.accepted_count AS accepted_count,
       rel.rejected_count AS rejected_count
"""
EDGE_BETWEEN_QUERY = """
MATCH (:KGEntity {id: $head})-[rel]->(:KGEntity {id: $tail})
WHERE rel.scenario IN $scenarios
RETURN type(rel) AS relation,
       rel.scenario AS scenario,
       rel.source AS source,
       rel.evidence AS evidence,
       rel.confidence AS confidence,
       rel.weight AS weight,
       rel.review_status AS review_status,
       rel.feedback_count AS feedback_count,
       rel.accepted_count AS accepted_count,
       rel.rejected_count AS rejected_count
"""
EDGES_QUERY = """
MATCH (head:KGEntity)-[rel]->(tail:KGEntity)
WHERE rel.scenario IN $scenarios
  AND head.scenario IN $scenarios
  AND tail.scenario IN $scenarios
RETURN head.id AS head,
       tail.id AS tail,
       type(rel) AS relation,
       rel.scenario AS scenario,
       rel.source AS source,
       rel.evidence AS evidence,
       rel.confidence AS confidence,
       rel.weight AS weight,
       rel.review_status AS review_status,
       rel.feedback_count AS feedback_count,
       rel.accepted_count AS accepted_count,
       rel.rejected_count AS rejected_count
"""


class Neo4jResult(Protocol):
    """Small iterable result subset returned by Neo4j sessions."""

    def __iter__(self) -> Iterator[Mapping[str, Any]]:
        """Iterate over result records."""


class Neo4jSession(Protocol):
    """Small subset of a Neo4j session used by the repository."""

    def run(self, query: str, parameters: Mapping[str, object]) -> Neo4jResult:
        """Run one Cypher query."""


class Neo4jDriver(Protocol):
    """Small subset of a Neo4j driver used by the repository."""

    def session(self, **kwargs: object) -> AbstractContextManager[Neo4jSession]:
        """Open a Neo4j session."""

    def close(self) -> None:
        """Close the driver."""


@dataclass(frozen=True)
class Neo4jKGRepository:
    """Runtime KG repository backed by Neo4j."""

    config: Neo4jConfig
    driver: Neo4jDriver

    @classmethod
    def connect(cls, config: Neo4jConfig) -> Neo4jKGRepository:
        """Create a repository using the real Neo4j Python driver."""
        missing = [
            field
            for field in ("uri", "user", "password", "database")
            if not getattr(config, field)
        ]
        if missing:
            raise ValueError(f"Neo4j repository config is incomplete: {', '.join(missing)}")
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(config.uri, auth=(config.user, config.password))
        driver.verify_connectivity()
        return cls(config=config, driver=cast(Neo4jDriver, driver))

    def close(self) -> None:
        """Close the underlying Neo4j driver."""
        self.driver.close()

    def candidates(
        self,
        mention: str | None,
        *,
        scenario: str | None = None,
        top_k: int = 5,
        min_score: float = 0.55,
    ) -> list[LinkCandidate]:
        """Return top-k entity candidates scoped to a dataset scenario plus shared KG."""
        normalized_mention = "" if mention is None else "".join(
            ch.lower() if ch.isalnum() else "" for ch in mention
        )
        if not normalized_mention:
            return []

        candidates: list[LinkCandidate] = []
        for node in self.nodes(scenario=scenario):
            best: LinkCandidate | None = None
            for term in node.searchable_terms:
                score, match_type = _match_score(normalized_mention, term, node)
                if score < min_score:
                    continue
                candidate = LinkCandidate(
                    entity_id=node.id,
                    name=node.name,
                    label=node.label,
                    scenario=node.scenario,
                    score=score,
                    match_type=match_type,
                    matched_term=term,
                )
                if best is None or candidate.score > best.score:
                    best = candidate
            if best is not None:
                candidates.append(best)
        candidates.sort(key=lambda item: (-item.score, item.entity_id))
        return candidates[:top_k]

    def nodes(self, *, scenario: str | None = None) -> list[KGNode]:
        """Return KG nodes scoped to a dataset scenario plus shared KG."""
        with self.driver.session(database=self.config.database) as session:
            records = session.run(NODE_QUERY, {"scenarios": _scenario_values(scenario)})
            return [_node_from_record(record) for record in records]

    def has_edge(self, head: str, relation: str, tail: str, *, scenario: str | None = None) -> bool:
        """Return whether a scoped relation exists between two KG nodes."""
        _require_relation(relation)
        query = HAS_EDGE_QUERY.format(relation=relation)
        with self.driver.session(database=self.config.database) as session:
            records = list(
                session.run(
                    query,
                    {
                        "head": head,
                        "tail": tail,
                        "scenarios": _scenario_values(scenario),
                    },
                )
            )
        return bool(records)

    def outgoing(
        self,
        node_id: str,
        relation: str | None = None,
        *,
        scenario: str | None = None,
    ) -> list[KGEdge]:
        """Return scoped outgoing KG edges, optionally filtered by relation."""
        relation_clause = ""
        if relation is not None:
            _require_relation(relation)
            relation_clause = f":`{relation}`"
        query = OUTGOING_QUERY.format(relation_clause=relation_clause)
        with self.driver.session(database=self.config.database) as session:
            records = session.run(
                query,
                {
                    "head": node_id,
                    "scenarios": _scenario_values(scenario),
                },
            )
            return [_edge_from_record(node_id, record) for record in records]

    def edge_between(
        self,
        head: str,
        tail: str,
        *,
        scenario: str | None = None,
    ) -> list[KGEdge]:
        """Return scoped KG edges between two nodes."""
        with self.driver.session(database=self.config.database) as session:
            records = session.run(
                EDGE_BETWEEN_QUERY,
                {
                    "head": head,
                    "tail": tail,
                    "scenarios": _scenario_values(scenario),
                },
            )
            return [_edge_from_record(head, record, tail=tail) for record in records]

    def to_knowledge_graph(self, *, scenario: str | None = None) -> KnowledgeGraph:
        """Load a scenario-scoped Neo4j snapshot into the reusable graph contract."""
        scenarios = _scenario_values(scenario)
        nodes = self.nodes(scenario=scenario)
        with self.driver.session(database=self.config.database) as session:
            records = session.run(EDGES_QUERY, {"scenarios": scenarios})
            edges = [_edge_from_record(str(record["head"]), record) for record in records]
        return KnowledgeGraph(nodes, edges)


def _scenario_values(scenario: str | None) -> list[str]:
    if not scenario:
        return ["shared", "mvtec", "tep", "wafer"]
    return ["shared", scenario]


def _require_relation(relation: str) -> None:
    if not RELATION_PATTERN.fullmatch(relation):
        raise ValueError(f"invalid Neo4j relation type: {relation}")


def _node_from_record(record: Mapping[str, Any]) -> KGNode:
    aliases = record.get("aliases") or ()
    if isinstance(aliases, str):
        aliases = split_aliases(aliases)
    return KGNode(
        id=str(record["id"]),
        name=str(record.get("name") or ""),
        label=str(record.get("label") or ""),
        scenario=str(record.get("scenario") or ""),
        aliases=tuple(str(alias) for alias in aliases),
        description=str(record.get("description") or ""),
    )


def _edge_from_record(head: str, record: Mapping[str, Any], *, tail: str | None = None) -> KGEdge:
    return KGEdge(
        head=head,
        relation=str(record["relation"]),
        tail=str(tail or record["tail"]),
        scenario=str(record.get("scenario") or ""),
        source=str(record.get("source") or ""),
        evidence=str(record.get("evidence") or ""),
        confidence=float(record.get("confidence") or 0),
        weight=float(record.get("weight") or 0),
        review_status=str(record.get("review_status") or "auto"),
        feedback_count=int(record.get("feedback_count") or 0),
        accepted_count=int(record.get("accepted_count") or 0),
        rejected_count=int(record.get("rejected_count") or 0),
    )
