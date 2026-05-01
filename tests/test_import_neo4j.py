"""Tests for optional Neo4j import helpers."""

from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace

import pytest

from kgtracevis.kg.graph import KGEdge, KGNode, KnowledgeGraph
from kgtracevis.kg.import_neo4j import (
    Neo4jConfig,
    Neo4jImportError,
    dry_run_import,
    import_knowledge_graph,
    import_knowledge_graph_with_config,
    resolve_neo4j_config,
)


class FakeSession:
    """Context-manager session that records Cypher calls."""

    def __init__(self) -> None:
        self.runs: list[tuple[str, dict[str, object]]] = []

    def __enter__(self) -> FakeSession:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def run(self, query: str, parameters: Mapping[str, object]) -> None:
        self.runs.append((query, dict(parameters)))


class FakeDriver:
    """Driver that records session options and exposes one fake session."""

    def __init__(self) -> None:
        self.session_options: dict[str, object] | None = None
        self.session_instance = FakeSession()

    def session(self, **kwargs: object) -> FakeSession:
        self.session_options = kwargs
        return self.session_instance


def test_resolve_neo4j_config_precedence(tmp_path: Path) -> None:
    """CLI values should override environment, which overrides YAML defaults."""
    config_path = tmp_path / "neo4j.yaml"
    config_path.write_text(
        "\n".join(
            [
                "uri: bolt://yaml:7687",
                "user: yaml_user",
                "password: yaml_password",
                "database: yaml_db",
            ]
        ),
        encoding="utf-8",
    )

    config = resolve_neo4j_config(
        uri="bolt://cli:7687",
        env={
            "NEO4J_URI": "bolt://env:7687",
            "NEO4J_USER": "env_user",
            "NEO4J_PASSWORD": "env_password",
        },
        config_path=config_path,
    )

    assert config == Neo4jConfig(
        uri="bolt://cli:7687",
        user="env_user",
        password="env_password",
        database="yaml_db",
    )


def test_resolve_neo4j_config_accepts_nested_yaml(tmp_path: Path) -> None:
    """Config resolution should accept a top-level neo4j mapping."""
    config_path = tmp_path / "neo4j.yaml"
    config_path.write_text(
        "\n".join(
            [
                "neo4j:",
                "  uri: bolt://nested:7687",
                "  user: nested_user",
                "  password: nested_password",
            ]
        ),
        encoding="utf-8",
    )

    config = resolve_neo4j_config(env={}, config_path=config_path)

    assert config == Neo4jConfig(
        uri="bolt://nested:7687",
        user="nested_user",
        password="nested_password",
        database="neo4j",
    )


def test_dry_run_import_does_not_need_driver() -> None:
    """Dry run should only count validated in-memory rows."""
    graph = _graph()

    summary = dry_run_import(graph)

    assert summary.node_count == 2
    assert summary.edge_count == 1
    assert summary.dry_run is True


def test_import_knowledge_graph_runs_node_and_edge_cypher() -> None:
    """Importer should send nodes and edges through one selected database session."""
    graph = _graph()
    driver = FakeDriver()

    summary = import_knowledge_graph(graph, driver, database="kgtrace")

    assert summary.node_count == 2
    assert summary.edge_count == 1
    assert summary.dry_run is False
    assert driver.session_options == {"database": "kgtrace"}
    assert len(driver.session_instance.runs) == 3

    node_query, node_params = driver.session_instance.runs[0]
    assert "MERGE (node:KGEntity {id: $id})" in node_query
    assert node_params["id"] == "ScratchDefect"
    assert node_params["aliases"] == ["scratch"]

    edge_query, edge_params = driver.session_instance.runs[-1]
    assert "MERGE (head)-[rel:`HAS_MORPHOLOGY` {edge_id: $edge_id}]->(tail)" in edge_query
    assert edge_params["source"] == "dataset_labels"
    assert edge_params["evidence"] == "structured source row"
    assert edge_params["confidence"] == 0.9
    assert edge_params["weight"] == 0.1
    assert edge_params["review_status"] == "auto"
    assert edge_params["feedback_count"] == 0
    assert edge_params["accepted_count"] == 0
    assert edge_params["rejected_count"] == 0


def test_import_rejects_invalid_relation_type() -> None:
    """Dynamic Neo4j relation types should stay inside the KG relation contract."""
    graph = KnowledgeGraph(
        nodes=[
            _node("ScratchDefect", aliases=("scratch",)),
            _node("LinearMorphology", label="Morphology"),
        ],
        edges=[
            KGEdge(
                head="ScratchDefect",
                relation="has morphology",
                tail="LinearMorphology",
                scenario="mvtec",
                source="dataset_labels",
                evidence="structured source row",
                confidence=0.9,
                weight=0.1,
                review_status="auto",
                feedback_count=0,
                accepted_count=0,
                rejected_count=0,
            )
        ],
    )

    with pytest.raises(ValueError, match="invalid Neo4j relation type"):
        import_knowledge_graph(graph, FakeDriver())


def test_real_import_requires_complete_config() -> None:
    """A requested real import should fail clearly before trying incomplete config."""
    with pytest.raises(Neo4jImportError, match="connection settings are incomplete"):
        import_knowledge_graph_with_config(
            _graph(),
            Neo4jConfig(uri="", user="", password="", database="neo4j"),
        )


def test_real_import_wraps_unavailable_database(monkeypatch: pytest.MonkeyPatch) -> None:
    """A requested real import should explain how to recover when Neo4j is unavailable."""

    class FailingGraphDatabase:
        @staticmethod
        def driver(*_args: object, **_kwargs: object) -> object:
            raise RuntimeError("connection refused")

    monkeypatch.setitem(
        sys.modules,
        "neo4j",
        SimpleNamespace(GraphDatabase=FailingGraphDatabase),
    )

    with pytest.raises(Neo4jImportError, match="rerun with --dry-run"):
        import_knowledge_graph_with_config(
            _graph(),
            Neo4jConfig(
                uri="bolt://localhost:7687",
                user="neo4j",
                password="password",
                database="neo4j",
            ),
        )


def test_real_import_does_not_relabel_invalid_kg_relation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """KG validation failures should stay distinct from Neo4j connectivity errors."""

    class ConnectedDriver(FakeDriver):
        def verify_connectivity(self) -> None:
            return None

        def close(self) -> None:
            return None

    class ConnectedGraphDatabase:
        @staticmethod
        def driver(*_args: object, **_kwargs: object) -> ConnectedDriver:
            return ConnectedDriver()

    graph = KnowledgeGraph(
        nodes=[
            _node("ScratchDefect", aliases=("scratch",)),
            _node("LinearMorphology", label="Morphology"),
        ],
        edges=[
            KGEdge(
                head="ScratchDefect",
                relation="has morphology",
                tail="LinearMorphology",
                scenario="mvtec",
                source="dataset_labels",
                evidence="structured source row",
                confidence=0.9,
                weight=0.1,
                review_status="auto",
                feedback_count=0,
                accepted_count=0,
                rejected_count=0,
            )
        ],
    )
    monkeypatch.setitem(
        sys.modules,
        "neo4j",
        SimpleNamespace(GraphDatabase=ConnectedGraphDatabase),
    )

    with pytest.raises(ValueError, match="invalid Neo4j relation type"):
        import_knowledge_graph_with_config(
            graph,
            Neo4jConfig(
                uri="bolt://localhost:7687",
                user="neo4j",
                password="password",
                database="neo4j",
            ),
        )


def _graph() -> KnowledgeGraph:
    return KnowledgeGraph(
        nodes=[
            _node("ScratchDefect", aliases=("scratch",)),
            _node("LinearMorphology", label="Morphology"),
        ],
        edges=[
            KGEdge(
                head="ScratchDefect",
                relation="HAS_MORPHOLOGY",
                tail="LinearMorphology",
                scenario="mvtec",
                source="dataset_labels",
                evidence="structured source row",
                confidence=0.9,
                weight=0.1,
                review_status="auto",
                feedback_count=0,
                accepted_count=0,
                rejected_count=0,
            )
        ],
    )


def _node(
    node_id: str,
    *,
    label: str = "AnomalyType",
    aliases: tuple[str, ...] = (),
) -> KGNode:
    return KGNode(
        id=node_id,
        name=node_id,
        label=label,
        scenario="mvtec",
        aliases=aliases,
        description="test node",
    )
