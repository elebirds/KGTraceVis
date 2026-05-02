"""Tests for entity linking."""

from __future__ import annotations

from kgtracevis.kg.entity_linker import link_evidence_entities, selected_entities_by_field
from kgtracevis.kg.graph import KnowledgeGraph
from kgtracevis.schema.validators import load_evidence_json


def test_link_mvtec_example_entities() -> None:
    """The MVTec example should link its core visual fields."""
    evidence = load_evidence_json("data/examples/ds_mvtec_example.json")
    graph = KnowledgeGraph.from_csv()

    links = link_evidence_entities(evidence, graph)
    selected = {link["field"]: link["selected_entity_id"] for link in links}

    assert selected["anomaly_type"] == "ScratchDefect"
    assert selected["morphology"] == "LinearMorphology"
    assert selected["location"] == "SurfaceLocation"

    anomaly_link = next(link for link in links if link["field"] == "anomaly_type")
    assert anomaly_link["obs_id"] == "obs_mvtec_0001_anomaly_type_scratch"
    assert anomaly_link["facet"] == "anomaly_type"


def test_linker_prefers_observation_when_legacy_field_conflicts() -> None:
    """Canonical observations should take precedence over legacy fields."""
    evidence = load_evidence_json("data/examples/ds_mvtec_example.json").model_copy(
        update={"morphology": "surface"}
    )
    graph = KnowledgeGraph.from_csv()

    links = link_evidence_entities(evidence, graph)
    morphology_links = [link for link in links if link["field"] == "morphology"]

    assert [link["mention"] for link in morphology_links] == ["linear"]
    assert morphology_links[0]["obs_id"] == "obs_mvtec_0001_morphology_linear"
    assert selected_entities_by_field(links)["morphology"] == "LinearMorphology"


def test_linker_keeps_legacy_fallback_when_observations_are_absent() -> None:
    """Legacy payloads remain runnable while observations are adopted."""
    evidence = load_evidence_json("data/examples/ds_mvtec_example.json").model_copy(
        update={"observations": []}
    )
    graph = KnowledgeGraph.from_csv()

    links = link_evidence_entities(evidence, graph)
    morphology_link = next(link for link in links if link["field"] == "morphology")

    assert morphology_link["mention"] == "linear"
    assert "obs_id" not in morphology_link
    assert selected_entities_by_field(links)["morphology"] == "LinearMorphology"
