"""Tests for the reusable analysis pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from kgtracevis.core import KGTracePipeline
from kgtracevis.kg.graph import KnowledgeGraph
from kgtracevis.schema.evidence_schema import KGAnalysis
from kgtracevis.schema.validators import load_evidence_json

EDGE_CONTRACT_KEYS = {
    "edge_id",
    "source",
    "evidence",
    "confidence",
    "weight",
    "review_status",
    "feedback_count",
    "accepted_count",
    "rejected_count",
}


def test_pipeline_analyzes_all_examples() -> None:
    """The v0 pipeline should produce links, scores, and paths for examples."""
    pipeline = KGTracePipeline(graph=KnowledgeGraph.from_default_paths())

    for path in sorted(Path("data/examples").glob("*.json")):
        result = pipeline.analyze(load_evidence_json(path))

        assert result.linked_entities
        assert result.consistency_score is not None
        assert result.top_k_paths


def test_pipeline_uses_mvtec_reference_layer() -> None:
    """The default pipeline should use curated MVTec RCA reference edges."""
    pipeline = KGTracePipeline(graph=KnowledgeGraph.from_default_paths())
    result = pipeline.analyze(load_evidence_json("data/examples/ds_mvtec_example.json"))
    root_targets = {path["target_entity_id"] for path in result.top_k_paths}

    assert "MechanicalContact" in root_targets


def test_pipeline_result_serializes_feedback_compatible_contract() -> None:
    """Serialized results should keep all downstream review payloads intact."""
    feedback = {
        "entity_linking": [
            {
                "link_id": "link_mvtec_0001_anomaly_type_scratch",
                "accepted": True,
            }
        ]
    }
    evidence = load_evidence_json("data/examples/ds_mvtec_example.json").model_copy(
        update={"human_feedback": feedback}
    )

    result = KGTracePipeline(graph=KnowledgeGraph.from_default_paths()).analyze(evidence)
    payload = result.model_dump(mode="json")

    assert payload["case_id"] == "mvtec_0001"
    assert payload["linked_entities"]
    assert payload["consistency_score"] == 1.0
    assert payload["inconsistent_fields"] == []
    assert payload["correction_candidates"] == []
    assert payload["top_k_paths"]
    assert payload["ranked_root_causes"]
    assert payload["human_feedback"] == feedback
    kg_analysis = KGAnalysis.model_validate(
        {
            "top_k_paths": payload["top_k_paths"],
            "ranked_root_causes": payload["ranked_root_causes"],
        }
    )
    assert kg_analysis.ranked_root_causes[0]["candidate_id"] == "MechanicalContact"

    anomaly_link = _link_for_field(payload["linked_entities"], "anomaly_type")
    assert anomaly_link["link_id"] == "link_mvtec_0001_anomaly_type_scratch"
    assert anomaly_link["selected_entity_id"] == "ScratchDefect"
    assert anomaly_link["candidates"]


def test_pipeline_correction_candidate_contract_for_known_inconsistency() -> None:
    """Correction candidates should expose stable IDs and supporting KG edges."""
    evidence = load_evidence_json("data/examples/mvtec_noisy_morphology_demo.json")

    result = KGTracePipeline(graph=KnowledgeGraph.from_default_paths()).analyze(evidence)

    assert result.inconsistent_fields == ["anomaly_type", "morphology"]
    assert result.correction_candidates
    candidate = result.correction_candidates[0]
    assert candidate["candidate_id"] == "corr_mvtec_noisy_0001_morphology_linearmorphology"
    assert candidate["source_field"] == "anomaly_type"
    assert candidate["source_entity_id"] == "ScratchDefect"
    assert candidate["target_field"] == "morphology"
    assert candidate["original_value"] == "surface"
    assert candidate["suggested_entity_id"] == "LinearMorphology"
    assert candidate["suggested_value"] == "Linear morphology"
    assert candidate["supporting_edge_ids"] == [
        "ScratchDefect|HAS_MORPHOLOGY|LinearMorphology|mvtec"
    ]
    assert candidate["supporting_edges"]
    _assert_edge_contract(candidate["supporting_edges"][0])


def test_pipeline_path_contract_for_known_example() -> None:
    """Ranked paths should expose stable path IDs and reviewable source edges."""
    result = KGTracePipeline(graph=KnowledgeGraph.from_default_paths()).analyze(
        load_evidence_json("data/examples/ds_mvtec_example.json")
    )

    path = result.top_k_paths[0]
    assert path["path_id"] == "path_mvtec_0001_742df5e1c9"
    assert path["source_entity_id"] == "ScratchDefect"
    assert path["target_entity_id"] == "MechanicalContact"
    assert path["nodes"] == ["ScratchDefect", "MechanicalContact"]
    assert path["relations"] == ["HAS_PLAUSIBLE_CAUSE"]
    assert path["supporting_evidence"]
    assert path["source_edge_ids"] == [
        "ScratchDefect|HAS_PLAUSIBLE_CAUSE|MechanicalContact|mvtec"
    ]
    assert path["source_edges"]
    _assert_edge_contract(path["source_edges"][0])

    root_cause = result.ranked_root_causes[0]
    assert root_cause.candidate_id == "MechanicalContact"
    assert root_cause.scoring_method == "relation_weighted_path"
    assert root_cause.explanation_paths[0]["path_id"] == "path_mvtec_0001_742df5e1c9"
    assert root_cause.supporting_edges


def test_pipeline_does_not_mutate_input_evidence() -> None:
    """Analysis should leave raw and normalized input evidence untouched."""
    evidence = load_evidence_json("data/examples/ds_mvtec_example.json")
    before = evidence.model_dump(mode="json")

    KGTracePipeline(graph=KnowledgeGraph.from_default_paths()).analyze(evidence)

    assert evidence.model_dump(mode="json") == before


def test_pipeline_uses_neo4j_snapshot_repository_by_default() -> None:
    """Default runtime analysis should come from a dataset-scoped Neo4j snapshot."""
    repository = FakeSnapshotRepository(KnowledgeGraph.from_default_paths())
    evidence = load_evidence_json("data/examples/ds_mvtec_example.json")

    result = KGTracePipeline(neo4j_repository=repository).analyze(evidence)

    assert repository.scenarios == ["mvtec"]
    assert result.top_k_paths


def test_pipeline_keeps_legacy_root_cause_provider_signature_working() -> None:
    """Adding graph context should not break older provider implementations."""
    provider = LegacyRootCauseProvider()
    evidence = load_evidence_json("data/examples/ds_mvtec_example.json")

    result = KGTracePipeline(
        graph=KnowledgeGraph.from_default_paths(),
        root_cause_provider=provider,
    ).analyze(evidence)

    assert provider.case_ids == ["mvtec_0001"]
    assert result.ranked_root_causes[0].candidate_id == "MechanicalContact"


class FakeSnapshotRepository:
    """Tiny fake repository for pipeline backend selection tests."""

    def __init__(self, graph: KnowledgeGraph | None) -> None:
        assert graph is not None
        self.graph = graph
        self.scenarios: list[str | None] = []

    def to_knowledge_graph(self, *, scenario: str | None = None) -> KnowledgeGraph:
        self.scenarios.append(scenario)
        return self.graph


class LegacyRootCauseProvider:
    """Provider fixture with the pre-graph extension method shape."""

    def __init__(self) -> None:
        self.case_ids: list[str] = []

    def rank_root_causes(
        self,
        evidence: Any,
        *,
        top_k: int = 5,
        top_k_paths: list[dict[str, Any]] | None = None,
    ) -> list[Any]:
        del top_k
        del top_k_paths
        self.case_ids.append(evidence.case_id)
        return []


def _link_for_field(links: list[dict[str, Any]], field: str) -> dict[str, Any]:
    return next(link for link in links if link["field"] == field)


def _assert_edge_contract(edge: dict[str, Any]) -> None:
    assert EDGE_CONTRACT_KEYS <= edge.keys()
    assert edge["edge_id"]
    assert edge["source"]
    assert edge["evidence"]
    assert 0 <= edge["confidence"] <= 1
    assert 0 <= edge["weight"] <= 1
    assert edge["review_status"] in {"auto", "reviewed", "rejected"}
    assert isinstance(edge["feedback_count"], int)
    assert isinstance(edge["accepted_count"], int)
    assert isinstance(edge["rejected_count"], int)
    assert edge["feedback_count"] >= 0
    assert edge["accepted_count"] >= 0
    assert edge["rejected_count"] >= 0
