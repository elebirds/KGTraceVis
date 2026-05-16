"""Tests for the Neo4j runtime KG repository."""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from kgtracevis.kg.graph import KGEdge, KGNode
from kgtracevis.kg.import_neo4j import Neo4jConfig
from kgtracevis.kg.neo4j_repository import Neo4jKGRepository


class FakeSession:
    """Context-manager session with query-pattern fixtures."""

    def __init__(self) -> None:
        self.runs: list[tuple[str, dict[str, object]]] = []

    def __enter__(self) -> FakeSession:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def run(self, query: str, parameters: Mapping[str, object]) -> list[dict[str, object]]:
        self.runs.append((query, dict(parameters)))
        if "MERGE (node:KGEntity {id: $id})" in query:
            return [
                {
                    "id": parameters["id"],
                    "name": parameters["name"],
                    "label": parameters["label"],
                    "scenario": parameters["scenario"],
                    "aliases": parameters["aliases"],
                    "description": parameters["description"],
                }
            ]
        if "DETACH DELETE node" in query:
            return [{"deleted_node_count": 1, "deleted_relationship_count": 2}]
        if "MERGE (head)-[rel:" in query:
            return [_edge_record(parameters)]
        if "SET rel.confidence = $confidence" in query:
            return [
                _edge_record(
                    {
                        **parameters,
                        "head": "ScratchDefect",
                        "tail": "LinearMorphology",
                        "relation": "HAS_MORPHOLOGY",
                        "scenario": "mvtec",
                        "source": "manual_api",
                        "evidence": "operator edit",
                        "review_status": "reviewed",
                        "feedback_count": 0,
                        "accepted_count": 0,
                        "rejected_count": 0,
                    }
                )
            ]
        if "deleted_edge_count" in query:
            return [{"deleted_edge_count": 1}]
        if "RETURN node.id AS id" in query:
            return [
                {
                    "id": "ScratchDefect",
                    "name": "Scratch defect",
                    "label": "AnomalyType",
                    "scenario": "mvtec",
                    "aliases": ["scratch"],
                    "description": "test node",
                },
                {
                    "id": "NearfullDefect",
                    "name": "Near-full defect",
                    "label": "AnomalyType",
                    "scenario": "wafer",
                    "aliases": ["nearfull"],
                    "description": "test node",
                },
                {
                    "id": "LinearMorphology",
                    "name": "Linear morphology",
                    "label": "Morphology",
                    "scenario": "mvtec",
                    "aliases": ["linear"],
                    "description": "test node",
                },
            ]
        if "RETURN rel.edge_id AS edge_id" in query:
            return [{"edge_id": "ScratchDefect|HAS_MORPHOLOGY|LinearMorphology|mvtec"}]
        if "RETURN tail.id AS tail" in query:
            return [
                {
                    "tail": "LinearMorphology",
                    "relation": "HAS_MORPHOLOGY",
                    "scenario": "mvtec",
                    "source": "dataset_labels",
                    "evidence": "structured source row",
                    "confidence": 0.9,
                    "weight": 0.1,
                    "review_status": "auto",
                    "feedback_count": 0,
                    "accepted_count": 0,
                    "rejected_count": 0,
                }
            ]
        if "RETURN head.id AS head" in query:
            return [
                {
                    "head": "ScratchDefect",
                    "tail": "LinearMorphology",
                    "relation": "HAS_MORPHOLOGY",
                    "scenario": "mvtec",
                    "source": "dataset_labels",
                    "evidence": "structured source row",
                    "confidence": 0.9,
                    "weight": 0.1,
                    "review_status": "auto",
                    "feedback_count": 0,
                    "accepted_count": 0,
                    "rejected_count": 0,
                }
            ]
        return []


class FakeDriver:
    """Driver that records sessions and exposes one fake session."""

    def __init__(self) -> None:
        self.session_instance = FakeSession()
        self.closed = False

    def session(self, **_kwargs: object) -> FakeSession:
        return self.session_instance

    def close(self) -> None:
        self.closed = True


def test_candidates_are_scoped_to_dataset_and_shared() -> None:
    """Repository candidate lookup should pass dataset plus shared to Neo4j."""
    driver = FakeDriver()
    repository = _repository(driver)

    candidates = repository.candidates("scratch", scenario="mvtec")

    assert candidates[0].entity_id == "ScratchDefect"
    _query, params = driver.session_instance.runs[0]
    assert params["scenarios"] == ["shared", "mvtec"]


def test_has_edge_rejects_invalid_relation() -> None:
    """Runtime queries should keep dynamic relation types inside the KG contract."""
    repository = _repository(FakeDriver())

    with pytest.raises(ValueError, match="invalid Neo4j relation type"):
        repository.has_edge("ScratchDefect", "has morphology", "LinearMorphology", scenario="mvtec")


def test_outgoing_returns_kg_edges() -> None:
    """Repository should map Neo4j relation records back to KGEdge objects."""
    repository = _repository(FakeDriver())

    edges = repository.outgoing("ScratchDefect", "HAS_MORPHOLOGY", scenario="mvtec")

    assert edges[0].edge_id == "ScratchDefect|HAS_MORPHOLOGY|LinearMorphology|mvtec"
    assert edges[0].confidence == 0.9


def test_repository_close_closes_driver() -> None:
    """Repository close should delegate to the underlying driver."""
    driver = FakeDriver()
    repository = _repository(driver)

    repository.close()

    assert driver.closed is True


def test_to_knowledge_graph_returns_scenario_snapshot() -> None:
    """Repository should provide a graph snapshot for existing pipeline modules."""
    driver = FakeDriver()
    repository = _repository(driver)

    graph = repository.to_knowledge_graph(scenario="mvtec")

    assert "ScratchDefect" in graph.nodes
    assert graph.edges[0].edge_id == "ScratchDefect|HAS_MORPHOLOGY|LinearMorphology|mvtec"
    assert driver.session_instance.runs[-1][1]["scenarios"] == ["shared", "mvtec"]


def test_upsert_node_sends_runtime_node_payload() -> None:
    """Repository should create or update one Neo4j KGEntity."""
    driver = FakeDriver()
    repository = _repository(driver)

    node = repository.upsert_node(
        KGNode(
            id="ManualNode",
            name="Manual node",
            label="Concept",
            scenario="shared",
            aliases=("manual",),
            description="operator curated",
        )
    )

    query, params = driver.session_instance.runs[-1]
    assert "MERGE (node:KGEntity {id: $id})" in query
    assert params["id"] == "ManualNode"
    assert params["aliases"] == ["manual"]
    assert node.id == "ManualNode"


def test_upsert_edge_rejects_invalid_relation() -> None:
    """Runtime edge writes should validate dynamic Neo4j relation names."""
    repository = _repository(FakeDriver())

    with pytest.raises(ValueError, match="invalid Neo4j relation type"):
        repository.upsert_edge(
            KGEdge(
                head="ScratchDefect",
                relation="has_morphology",
                tail="LinearMorphology",
                scenario="mvtec",
                source="manual_api",
                evidence="operator edit",
                confidence=0.8,
                weight=0.2,
                review_status="reviewed",
                feedback_count=0,
                accepted_count=0,
                rejected_count=0,
            )
        )


def test_upsert_edge_and_update_confidence_send_weight() -> None:
    """Repository should persist edge confidence and derived weight."""
    driver = FakeDriver()
    repository = _repository(driver)
    edge = KGEdge(
        head="ScratchDefect",
        relation="HAS_MORPHOLOGY",
        tail="LinearMorphology",
        scenario="mvtec",
        source="manual_api",
        evidence="operator edit",
        confidence=0.8,
        weight=0.2,
        review_status="reviewed",
        feedback_count=0,
        accepted_count=0,
        rejected_count=0,
    )

    written = repository.upsert_edge(edge)
    updated = repository.update_edge_confidence(edge.edge_id, 0.65)

    assert written.confidence == 0.8
    assert updated.confidence == 0.65
    _query, params = driver.session_instance.runs[-1]
    assert params["weight"] == 0.35


def test_delete_node_and_edge_return_counts() -> None:
    """Repository delete helpers should expose affected row counts."""
    repository = _repository(FakeDriver())

    node_counts = repository.delete_node("ManualNode")
    edge_counts = repository.delete_edge("ScratchDefect|HAS_MORPHOLOGY|LinearMorphology|mvtec")

    assert node_counts == {
        "deleted_node_count": 1,
        "deleted_relationship_count": 2,
    }
    assert edge_counts == {"deleted_edge_count": 1}


def _repository(driver: FakeDriver) -> Neo4jKGRepository:
    return Neo4jKGRepository(
        config=Neo4jConfig(
            uri="bolt://localhost:7687",
            user="neo4j",
            password="password",
            database="neo4j",
        ),
        driver=driver,
    )


def _edge_record(parameters: Mapping[str, object]) -> dict[str, object]:
    return {
        "head": parameters["head"],
        "tail": parameters["tail"],
        "relation": parameters.get("relation", "HAS_MORPHOLOGY"),
        "scenario": parameters["scenario"],
        "source": parameters["source"],
        "evidence": parameters["evidence"],
        "confidence": parameters["confidence"],
        "weight": parameters["weight"],
        "review_status": parameters["review_status"],
        "feedback_count": parameters["feedback_count"],
        "accepted_count": parameters["accepted_count"],
        "rejected_count": parameters["rejected_count"],
    }
