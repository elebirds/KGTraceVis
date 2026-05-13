"""Tests for entity linking."""

from __future__ import annotations

from kgtracevis.adapters.wm811k_adapter import evidence_from_wm811k_record
from kgtracevis.kg.entity_linker import link_evidence_entities, selected_entities_by_field
from kgtracevis.kg.graph import KGNode, KnowledgeGraph
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


def test_linker_prefers_field_compatible_candidate_labels() -> None:
    """Field-aware linking should not select a defect node for a location mention."""
    graph = KnowledgeGraph(
        nodes=[
            KGNode("WaferObject", "Wafer", "Object", "wafer", ("wafer",)),
            KGNode("LocDefect", "Loc defect", "AnomalyType", "wafer", ("loc", "local")),
            KGNode(
                "WaferLocalLocation",
                "Wafer local region",
                "Location",
                "wafer",
                ("local", "localized"),
            ),
            KGNode(
                "WaferClusteredMorphology",
                "Wafer clustered morphology",
                "Morphology",
                "wafer",
                ("clustered",),
            ),
        ],
        edges=[],
    )
    evidence = evidence_from_wm811k_record(
        {
            "dataset": "wafer",
            "adapter": "wm811k",
            "case_id": "wm811k_loc_001",
            "predicted_pattern": "Loc",
            "failure_pattern": "Loc",
            "classification_confidence": 0.67,
            "wafer_map": [[0, 0, 0], [0, 2, 0], [0, 0, 0]],
        }
    )

    links = link_evidence_entities(evidence, graph)
    selected = selected_entities_by_field(links)

    assert selected["anomaly_type"] == "LocDefect"
    assert selected["location"] == "WaferLocalLocation"
    assert selected["morphology"] == "WaferClusteredMorphology"


def test_default_graph_links_wm811k_loc_to_hardened_wafer_entities() -> None:
    """Default KG loading should include hardened wafer classes for web analysis."""
    evidence = evidence_from_wm811k_record(
        {
            "dataset": "wafer",
            "adapter": "wm811k",
            "case_id": "wm811k_loc_default",
            "predicted_pattern": "Loc",
            "failure_pattern": "Loc",
            "classification_confidence": 0.67,
            "wafer_map": [[0, 0, 0], [0, 2, 0], [0, 0, 0]],
        }
    )
    graph = KnowledgeGraph.from_default_paths()

    selected = selected_entities_by_field(link_evidence_entities(evidence, graph))

    assert selected["anomaly_type"] == "LocDefect"
    assert selected["location"] == "WaferLocalLocation"
    assert selected["morphology"] == "WaferClusteredMorphology"
