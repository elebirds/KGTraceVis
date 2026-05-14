"""Neo4j import helpers for validated KG seed rows."""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

import yaml  # type: ignore[import-untyped]

from kgtracevis.kg.graph import KGEdge, KGNode, KnowledgeGraph

DEFAULT_NEO4J_CONFIG_PATH = Path("configs/neo4j.example.yaml")
DEFAULT_NEO4J_ENV = {
    "uri": "NEO4J_URI",
    "user": "NEO4J_USER",
    "password": "NEO4J_PASSWORD",
    "database": "NEO4J_DATABASE",
}
NODE_QUERY = """
MERGE (node:KGEntity {id: $id})
SET node.name = $name,
    node.entity_label = $label,
    node.scenario = $scenario,
    node.aliases = $aliases,
    node.description = $description
"""
SCHEMA_QUERIES = (
    """
    CREATE CONSTRAINT kg_entity_id_unique IF NOT EXISTS
    FOR (node:KGEntity) REQUIRE node.id IS UNIQUE
    """,
    """
    CREATE INDEX kg_entity_scenario IF NOT EXISTS
    FOR (node:KGEntity) ON (node.scenario)
    """,
)
RELATION_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")


class Neo4jSession(Protocol):
    """Small subset of a Neo4j session used by the importer."""

    def run(self, query: str, parameters: Mapping[str, object]) -> object:
        """Run one Cypher query."""


class Neo4jDriver(Protocol):
    """Small subset of a Neo4j driver used by the importer."""

    def session(self, **kwargs: object) -> AbstractContextManager[Neo4jSession]:
        """Open a Neo4j session."""


@dataclass(frozen=True)
class Neo4jConfig:
    """Resolved Neo4j connection settings."""

    uri: str
    user: str
    password: str
    database: str = "neo4j"


@dataclass(frozen=True)
class ImportSummary:
    """Counts for a Neo4j import attempt."""

    node_count: int
    edge_count: int
    dry_run: bool


class Neo4jImportError(RuntimeError):
    """Raised when an explicitly requested Neo4j import cannot complete."""


def resolve_neo4j_config(
    *,
    uri: str | None = None,
    user: str | None = None,
    password: str | None = None,
    database: str | None = None,
    env: Mapping[str, str] | None = None,
    config_path: str | Path = DEFAULT_NEO4J_CONFIG_PATH,
) -> Neo4jConfig:
    """Resolve Neo4j settings from CLI values, environment, then YAML defaults."""
    config_data = _load_config(config_path)
    env_data = _load_env(env or os.environ)
    return Neo4jConfig(
        uri=_first_present(uri, env_data.get("uri"), config_data.get("uri")),
        user=_first_present(user, env_data.get("user"), config_data.get("user")),
        password=_first_present(
            password,
            env_data.get("password"),
            config_data.get("password"),
        ),
        database=_first_present(
            database,
            env_data.get("database"),
            config_data.get("database"),
            "neo4j",
        ),
    )


def dry_run_import(graph: KnowledgeGraph) -> ImportSummary:
    """Return import counts without opening a Neo4j connection."""
    return ImportSummary(node_count=len(graph.nodes), edge_count=len(graph.edges), dry_run=True)


def import_knowledge_graph(
    graph: KnowledgeGraph,
    driver: Neo4jDriver,
    *,
    database: str = "neo4j",
) -> ImportSummary:
    """Import validated in-memory KG rows with one Neo4j session."""
    with driver.session(database=database) as session:
        ensure_neo4j_schema(session)
        import_nodes(session, graph.nodes.values())
        import_edges(session, graph.edges)
    return ImportSummary(node_count=len(graph.nodes), edge_count=len(graph.edges), dry_run=False)


def ensure_neo4j_schema(session: Neo4jSession) -> int:
    """Create Neo4j constraints and indexes needed by the runtime KG backend."""
    count = 0
    for query in SCHEMA_QUERIES:
        session.run(query, {})
        count += 1
    return count


def import_nodes(session: Neo4jSession, nodes: Iterable[KGNode]) -> int:
    """Import KG nodes into Neo4j and return the number of rows sent."""
    count = 0
    for node in nodes:
        session.run(NODE_QUERY, _node_parameters(node))
        count += 1
    return count


def import_edges(session: Neo4jSession, edges: Iterable[KGEdge]) -> int:
    """Import KG edges into Neo4j and return the number of rows sent."""
    count = 0
    for edge in edges:
        session.run(_edge_query(edge.relation), _edge_parameters(edge))
        count += 1
    return count


def import_knowledge_graph_with_config(
    graph: KnowledgeGraph,
    config: Neo4jConfig,
) -> ImportSummary:
    """Open a real Neo4j driver, verify connectivity, and import the KG."""
    _require_complete_config(config)
    driver = None
    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(config.uri, auth=(config.user, config.password))
        driver.verify_connectivity()
        return import_knowledge_graph(graph, cast(Neo4jDriver, driver), database=config.database)
    except ValueError:
        raise
    except Exception as exc:  # pragma: no cover - exercised by script integration paths.
        raise Neo4jImportError(
            "Neo4j import was requested but the database is unavailable or rejected "
            f"the connection at {config.uri}. Start Neo4j, fix credentials, or rerun "
            f"with --dry-run. Original error: {exc}"
        ) from exc
    finally:
        if driver is not None:
            driver.close()


def _load_config(config_path: str | Path) -> dict[str, str]:
    path = Path(config_path)
    if not path.exists():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} must contain a mapping")

    raw_config = loaded.get("neo4j", loaded)
    if not isinstance(raw_config, dict):
        raise ValueError(f"{path} neo4j config must contain a mapping")
    return {
        key: str(value)
        for key, value in raw_config.items()
        if key in DEFAULT_NEO4J_ENV and value is not None
    }


def _load_env(env: Mapping[str, str]) -> dict[str, str]:
    return {
        key: env[env_name]
        for key, env_name in DEFAULT_NEO4J_ENV.items()
        if env.get(env_name)
    }


def _first_present(*values: str | None) -> str:
    for value in values:
        if value:
            return value
    return ""


def _require_complete_config(config: Neo4jConfig) -> None:
    missing = [
        field
        for field in ("uri", "user", "password", "database")
        if not getattr(config, field)
    ]
    if missing:
        raise Neo4jImportError(
            "Neo4j import was requested but connection settings are incomplete: "
            f"{', '.join(missing)}. Provide CLI arguments, NEO4J_* environment "
            "variables, or a config YAML file."
        )


def _node_parameters(node: KGNode) -> dict[str, object]:
    return {
        "id": node.id,
        "name": node.name,
        "label": node.label,
        "scenario": node.scenario,
        "aliases": list(node.aliases),
        "description": node.description,
    }


def _edge_query(relation: str) -> str:
    if not RELATION_PATTERN.fullmatch(relation):
        raise ValueError(f"invalid Neo4j relation type: {relation}")
    return f"""
MATCH (head:KGEntity {{id: $head}})
MATCH (tail:KGEntity {{id: $tail}})
MERGE (head)-[rel:`{relation}` {{edge_id: $edge_id}}]->(tail)
SET rel.scenario = $scenario,
    rel.source = $source,
    rel.evidence = $evidence,
    rel.confidence = $confidence,
    rel.weight = $weight,
    rel.review_status = $review_status,
    rel.feedback_count = $feedback_count,
    rel.accepted_count = $accepted_count,
    rel.rejected_count = $rejected_count
"""


def _edge_parameters(edge: KGEdge) -> dict[str, object]:
    return {
        "edge_id": edge.edge_id,
        "head": edge.head,
        "tail": edge.tail,
        "scenario": edge.scenario,
        "source": edge.source,
        "evidence": edge.evidence,
        "confidence": edge.confidence,
        "weight": edge.weight,
        "review_status": edge.review_status,
        "feedback_count": edge.feedback_count,
        "accepted_count": edge.accepted_count,
        "rejected_count": edge.rejected_count,
    }
