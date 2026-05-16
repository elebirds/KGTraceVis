"""Tests for profile-driven semantic projection and RCA scoring policy."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kgtracevis.kg_construction import (
    DraftEntity,
    DraftKG,
    DraftRelation,
    RcaProfile,
    RelationFamilyPolicy,
    SemanticDerivedRelationRule,
    SemanticProjectionRule,
    build_rca_reasoning_view,
    load_rca_profile,
    profile_for_scenario,
    profile_to_manifest,
    project_semantic_layer,
)


def test_load_rca_profile_pack_from_json(tmp_path: Path) -> None:
    """JSON Domain Packs should hydrate the same runtime profile policy object."""
    profile_path = tmp_path / "unit_profile.json"
    profile_path.write_text(
        json.dumps(
            {
                "domain_id": "unit",
                "scenario": "shared",
                "ontology": "unit_rca_v1",
                "keep_labels": ["Equipment", "Variable"],
                "relation_whitelist": ["OBSERVED_BY"],
                "semantic_projection_rules": {
                    "metric_of": {
                        "target_relation": "observed_by",
                        "swap_endpoints": True,
                    }
                },
                "semantic_derived_relation_rules": [
                    {
                        "rule_id": "unit_bridge",
                        "left_relation": "HAS_COMPONENT",
                        "right_relation": "OBSERVED_BY",
                        "target_relation": "OBSERVED_BY",
                        "relation_family": "OBSERVATION",
                        "confidence_policy": "average",
                    }
                ],
                "relation_families": {"observed_by": "observation"},
                "relation_label_constraints": {
                    "observed_by": {
                        "head_labels": ["Equipment"],
                        "tail_labels": ["Variable"],
                    }
                },
                "relation_family_policies": {
                    "observation": {
                        "propagation_enabled": True,
                        "propagation_direction": "reverse",
                        "propagation_priority": 0.6,
                        "attenuation": 0.8,
                        "edge_weight_multiplier": 0.5,
                        "confidence_score_weight": 1.0,
                        "priority_score_weight": 0.0,
                        "attenuation_score_weight": 0.0,
                        "source_trust_score_weight": 0.0,
                    }
                },
                "root_candidate_labels": ["Equipment"],
                "observable_labels": ["Variable"],
            }
        ),
        encoding="utf-8",
    )

    profile = load_rca_profile(profile_path)
    manifest = profile_to_manifest(profile)

    assert profile.profile_source == str(profile_path)
    assert profile.projection_rule_for("METRIC_OF").swap_endpoints is True
    assert profile.rewrite_relation("metric_of") == "OBSERVED_BY"
    assert profile.relation_family_for("observed_by") == "OBSERVATION"
    assert profile.propagation_priority_for("OBSERVATION") == pytest.approx(0.6)
    assert profile.edge_weight_for("OBSERVATION", base_weight=0.4) == pytest.approx(0.2)
    assert profile.relation_family_policy_for("OBSERVATION").confidence_score_weight == 1.0
    assert manifest["profile_source"] == str(profile_path)
    assert manifest["semantic_projection_rules"]["METRIC_OF"] == {
        "swap_endpoints": True,
        "target_relation": "OBSERVED_BY",
    }
    assert manifest["semantic_derived_relation_rules"] == [
        {
            "confidence_policy": "average",
            "left_relation": "HAS_COMPONENT",
            "relation_family": "OBSERVATION",
            "right_relation": "OBSERVED_BY",
            "rule_id": "unit_bridge",
            "target_relation": "OBSERVED_BY",
        }
    ]
    assert manifest["relation_label_constraints"] == {
        "OBSERVED_BY": {
            "head_labels": ["Equipment"],
            "tail_labels": ["Variable"],
        }
    }


def test_profile_projection_can_derive_source_backed_two_hop_edges() -> None:
    """Semantic profiles should derive auditable candidate edges from two-hop rules."""
    profile = RcaProfile(
        domain_id="unit",
        scenario="shared",
        ontology="unit_rca_v1",
        keep_labels=frozenset({"Equipment", "Component", "Variable"}),
        relation_whitelist=frozenset({"HAS_COMPONENT", "OBSERVED_BY"}),
        relation_families={
            "HAS_COMPONENT": "PART_OF",
            "OBSERVED_BY": "OBSERVATION",
        },
        semantic_derived_relation_rules=(
            SemanticDerivedRelationRule(
                rule_id="component_observation_bridge",
                left_relation="HAS_COMPONENT",
                right_relation="OBSERVED_BY",
                target_relation="OBSERVED_BY",
                relation_family="OBSERVATION",
                confidence_policy="min",
            ),
        ),
        relation_family_policies={
            "OBSERVATION": RelationFamilyPolicy(
                propagation_enabled=True,
                propagation_direction="reverse",
                propagation_priority=0.7,
                attenuation=0.85,
            )
        },
    )
    draft = DraftKG(
        entities=(
            DraftEntity(
                draft_id="entity-pump",
                source_id="unit_source",
                extractor_name="unit",
                extractor_version="v1",
                scenario="shared",
                entity_id_suggestion="PumpA",
                name="Pump A",
                label="Equipment",
                evidence="pump row",
            ),
            DraftEntity(
                draft_id="entity-seal",
                source_id="unit_source",
                extractor_name="unit",
                extractor_version="v1",
                scenario="shared",
                entity_id_suggestion="SealAssembly",
                name="Seal assembly",
                label="Component",
                evidence="seal row",
            ),
            DraftEntity(
                draft_id="entity-pressure",
                source_id="unit_source",
                extractor_name="unit",
                extractor_version="v1",
                scenario="shared",
                entity_id_suggestion="PressureSignal",
                name="Pressure signal",
                label="Variable",
                evidence="pressure row",
            ),
        ),
        relations=(
            DraftRelation(
                draft_id="relation-pump-seal",
                source_id="unit_source",
                extractor_name="unit",
                extractor_version="v1",
                scenario="shared",
                head="PumpA",
                relation="HAS_COMPONENT",
                tail="SealAssembly",
                evidence="pump has seal assembly",
                confidence=0.9,
            ),
            DraftRelation(
                draft_id="relation-seal-pressure",
                source_id="unit_source",
                extractor_name="unit",
                extractor_version="v1",
                scenario="shared",
                head="SealAssembly",
                relation="OBSERVED_BY",
                tail="PressureSignal",
                evidence="seal assembly is observed by pressure signal",
                confidence=0.7,
            ),
        ),
    )

    semantic = project_semantic_layer(draft, profile)
    derived = [
        edge
        for edge in semantic.edges
        if edge.source == "semantic_projection:component_observation_bridge"
    ]

    assert len(semantic.edges) == 3
    assert len(derived) == 1
    assert derived[0].head == "PumpA"
    assert derived[0].relation == "OBSERVED_BY"
    assert derived[0].tail == "PressureSignal"
    assert derived[0].confidence == pytest.approx(0.7)
    assert derived[0].review_status == "auto"
    assert derived[0].propagation_enabled is True
    assert "relation-pump-seal" not in derived[0].evidence
    assert "PumpA|HAS_COMPONENT|SealAssembly|shared" in derived[0].evidence
    assert semantic.manifest["derived_edge_count"] == 1
    assert semantic.manifest["derived_edge_ids"] == [
        "PumpA|OBSERVED_BY|PressureSignal|shared"
    ]


def test_profile_projection_rule_can_rewrite_and_swap_relation_endpoints() -> None:
    """Domain profiles should drive semantic shape and RCA edge defaults."""
    profile = RcaProfile(
        domain_id="unit",
        scenario="shared",
        ontology="unit_rca_v1",
        keep_labels=frozenset({"Equipment", "Variable"}),
        relation_whitelist=frozenset({"OBSERVED_BY"}),
        semantic_projection_rules={
            "METRIC_OF": SemanticProjectionRule(
                target_relation="OBSERVED_BY",
                swap_endpoints=True,
            )
        },
        relation_families={"OBSERVED_BY": "OBSERVATION"},
        relation_family_policies={
            "OBSERVATION": RelationFamilyPolicy(
                propagation_enabled=True,
                propagation_direction="reverse",
                propagation_priority=0.65,
                attenuation=0.8,
                edge_weight_multiplier=0.5,
            )
        },
        root_candidate_labels=frozenset({"Equipment"}),
        observable_labels=frozenset({"Variable"}),
    )
    draft = DraftKG(
        entities=(
            DraftEntity(
                draft_id="entity-pump",
                source_id="unit_source",
                extractor_name="unit",
                extractor_version="v1",
                scenario="shared",
                entity_id_suggestion="PumpA",
                name="Pump A",
                label="Equipment",
                evidence="pump row",
            ),
            DraftEntity(
                draft_id="entity-pressure",
                source_id="unit_source",
                extractor_name="unit",
                extractor_version="v1",
                scenario="shared",
                entity_id_suggestion="PressureSignal",
                name="Pressure signal",
                label="Variable",
                evidence="pressure row",
            ),
        ),
        relations=(
            DraftRelation(
                draft_id="relation-pressure-pump",
                source_id="unit_source",
                extractor_name="unit",
                extractor_version="v1",
                scenario="shared",
                head="PressureSignal",
                relation="METRIC_OF",
                tail="PumpA",
                evidence="pressure signal is a metric of Pump A",
                confidence=0.8,
            ),
        ),
    )

    semantic = project_semantic_layer(draft, profile)
    assert len(semantic.edges) == 1
    semantic_edge = semantic.edges[0]
    assert semantic_edge.head == "PumpA"
    assert semantic_edge.relation == "OBSERVED_BY"
    assert semantic_edge.tail == "PressureSignal"
    assert semantic_edge.relation_family == "OBSERVATION"
    assert semantic_edge.propagation_enabled is True
    assert semantic_edge.propagation_direction == "reverse"
    assert semantic_edge.propagation_priority == pytest.approx(0.65)
    assert semantic_edge.attenuation == pytest.approx(0.8)
    assert semantic_edge.edge_weight == pytest.approx(0.1)
    assert semantic_edge.rca_score == pytest.approx(0.0)

    rca_view = build_rca_reasoning_view(
        semantic.nodes,
        semantic.edges,
        profile=profile,
        kg_build_id="kgbuild_unit_projection",
    )
    rca_edge = rca_view.edges[0]
    assert rca_edge.root_candidate is True
    assert rca_edge.observable is True
    assert rca_edge.edge_weight == pytest.approx(0.1)
    assert rca_edge.source_trust == pytest.approx(0.7)
    assert rca_edge.rca_score == pytest.approx(0.7525)
    assert rca_edge.rca_score_confidence == pytest.approx(0.4)
    assert rca_edge.rca_score_priority == pytest.approx(0.1625)
    assert rca_edge.rca_score_attenuation == pytest.approx(0.12)
    assert rca_edge.rca_score_source_trust == pytest.approx(0.07)
    policy = rca_view.manifest["relation_family_policies"]["OBSERVATION"]
    assert policy["attenuation"] == pytest.approx(0.8)
    assert policy["edge_weight_multiplier"] == pytest.approx(0.5)
    assert policy["propagation_direction"] == "reverse"
    assert policy["propagation_enabled"] is True
    assert policy["propagation_priority"] == pytest.approx(0.65)
    assert policy["confidence_score_weight"] == pytest.approx(0.5)
    assert rca_view.manifest["score_summary"]["mean_rca_score"] == pytest.approx(0.7525)


def test_profile_rca_policy_does_not_override_explicit_candidate_metadata() -> None:
    """Extractor/import metadata should override profile defaults when present."""
    profile = RcaProfile(
        domain_id="unit",
        scenario="shared",
        ontology="unit_rca_v1",
        keep_labels=frozenset({"RootCause", "Alert"}),
        relation_whitelist=frozenset({"CAUSES"}),
        relation_families={"CAUSES": "CAUSES"},
        relation_family_policies={
            "CAUSES": RelationFamilyPolicy(
                propagation_enabled=True,
                propagation_direction="forward",
                propagation_priority=1.0,
                attenuation=1.0,
            )
        },
        root_candidate_labels=frozenset({"RootCause"}),
        observable_labels=frozenset({"Alert"}),
    )
    draft = DraftKG(
        entities=(
            DraftEntity(
                draft_id="entity-root",
                source_id="unit_source",
                extractor_name="unit",
                extractor_version="v1",
                scenario="shared",
                entity_id_suggestion="SealWear",
                name="Seal wear",
                label="RootCause",
                evidence="seal wear",
            ),
            DraftEntity(
                draft_id="entity-alert",
                source_id="unit_source",
                extractor_name="unit",
                extractor_version="v1",
                scenario="shared",
                entity_id_suggestion="CoolingAlert",
                name="Cooling alert",
                label="Alert",
                evidence="cooling alert",
            ),
        ),
        relations=(
            DraftRelation(
                draft_id="relation-root-alert",
                source_id="unit_source",
                extractor_name="unit",
                extractor_version="v1",
                scenario="shared",
                head="SealWear",
                relation="CAUSES",
                tail="CoolingAlert",
                evidence="seal wear causes cooling alert",
                confidence=0.8,
                metadata={
                    "propagation_enabled": "false",
                    "propagation_direction": "reverse",
                    "propagation_priority": "0.4",
                    "attenuation": "0.6",
                    "edge_weight": "0.3",
                },
            ),
        ),
    )

    semantic = project_semantic_layer(draft, profile)
    rca_edge = build_rca_reasoning_view(
        semantic.nodes,
        semantic.edges,
        profile=profile,
        kg_build_id="kgbuild_unit_explicit",
    ).edges[0]

    assert rca_edge.propagation_enabled is False
    assert rca_edge.propagation_direction == "reverse"
    assert rca_edge.propagation_priority == pytest.approx(0.0)
    assert rca_edge.attenuation == pytest.approx(0.6)
    assert rca_edge.edge_weight == pytest.approx(0.3)
    assert rca_edge.rca_score == pytest.approx(0.56)


def test_blank_candidate_metadata_does_not_override_profile_defaults() -> None:
    """Only explicit source metadata should override profile RCA policy."""
    profile = RcaProfile(
        domain_id="unit",
        scenario="shared",
        ontology="unit_rca_v1",
        keep_labels=frozenset({"RootCause", "Alert"}),
        relation_whitelist=frozenset({"CAUSES"}),
        relation_families={"CAUSES": "CAUSES"},
        relation_family_policies={
            "CAUSES": RelationFamilyPolicy(
                propagation_enabled=True,
                propagation_direction="reverse",
                propagation_priority=0.8,
                attenuation=0.7,
                edge_weight_multiplier=0.5,
            )
        },
        root_candidate_labels=frozenset({"RootCause"}),
        observable_labels=frozenset({"Alert"}),
    )
    draft = DraftKG(
        entities=(
            DraftEntity(
                draft_id="entity-root",
                source_id="unit_source",
                extractor_name="unit",
                extractor_version="v1",
                scenario="shared",
                entity_id_suggestion="SealWear",
                name="Seal wear",
                label="RootCause",
                evidence="seal wear",
            ),
            DraftEntity(
                draft_id="entity-alert",
                source_id="unit_source",
                extractor_name="unit",
                extractor_version="v1",
                scenario="shared",
                entity_id_suggestion="CoolingAlert",
                name="Cooling alert",
                label="Alert",
                evidence="cooling alert",
            ),
        ),
        relations=(
            DraftRelation(
                draft_id="relation-root-alert",
                source_id="unit_source",
                extractor_name="unit",
                extractor_version="v1",
                scenario="shared",
                head="SealWear",
                relation="CAUSES",
                tail="CoolingAlert",
                evidence="seal wear causes cooling alert",
                confidence=0.8,
                metadata={
                    "propagation_enabled": "",
                    "propagation_direction": "",
                    "propagation_priority": "",
                    "attenuation": "",
                    "edge_weight": "",
                },
            ),
        ),
    )

    semantic = project_semantic_layer(draft, profile)
    edge = semantic.edges[0]

    assert edge.propagation_enabled is True
    assert edge.propagation_direction == "reverse"
    assert edge.propagation_priority == pytest.approx(0.8)
    assert edge.attenuation == pytest.approx(0.7)
    assert edge.edge_weight == pytest.approx(0.1)


def test_projection_swap_skips_edges_when_swapped_endpoint_is_not_kept() -> None:
    """Swapped semantic edges should still satisfy the projected node contract."""
    profile = RcaProfile(
        domain_id="unit",
        scenario="shared",
        ontology="unit_rca_v1",
        keep_labels=frozenset({"Variable"}),
        relation_whitelist=frozenset({"OBSERVED_BY"}),
        semantic_projection_rules={
            "METRIC_OF": SemanticProjectionRule(
                target_relation="OBSERVED_BY",
                swap_endpoints=True,
            )
        },
        relation_families={"OBSERVED_BY": "OBSERVATION"},
    )
    draft = DraftKG(
        entities=(
            DraftEntity(
                draft_id="entity-pump",
                source_id="unit_source",
                extractor_name="unit",
                extractor_version="v1",
                scenario="shared",
                entity_id_suggestion="PumpA",
                name="Pump A",
                label="Equipment",
                evidence="pump row",
            ),
            DraftEntity(
                draft_id="entity-pressure",
                source_id="unit_source",
                extractor_name="unit",
                extractor_version="v1",
                scenario="shared",
                entity_id_suggestion="PressureSignal",
                name="Pressure signal",
                label="Variable",
                evidence="pressure row",
            ),
        ),
        relations=(
            DraftRelation(
                draft_id="relation-pressure-pump",
                source_id="unit_source",
                extractor_name="unit",
                extractor_version="v1",
                scenario="shared",
                head="PressureSignal",
                relation="METRIC_OF",
                tail="PumpA",
                evidence="pressure signal is a metric of Pump A",
                confidence=0.8,
            ),
        ),
    )

    semantic = project_semantic_layer(draft, profile)

    assert semantic.edges == ()
    assert semantic.manifest["skipped_relation_ids"] == ["relation-pressure-pump"]


def test_profile_projection_skips_relation_when_endpoint_labels_do_not_match() -> None:
    """Profile label constraints keep source IE mistakes out of semantic rows."""
    profile = RcaProfile(
        domain_id="unit",
        scenario="shared",
        ontology="unit_rca_v1",
        keep_labels=frozenset({"Defect", "Location"}),
        relation_whitelist=frozenset({"HAS_LOCATION"}),
        relation_families={"HAS_LOCATION": "SEMANTIC_SUPPORT"},
        relation_label_constraints={
            "HAS_LOCATION": (
                frozenset({"Defect"}),
                frozenset({"Location"}),
            )
        },
    )
    draft = DraftKG(
        entities=(
            DraftEntity(
                draft_id="entity-flow-mark",
                source_id="unit_source",
                extractor_name="unit",
                extractor_version="v1",
                scenario="shared",
                entity_id_suggestion="FlowMark",
                name="Flow mark",
                label="Defect",
                evidence="flow mark row",
            ),
            DraftEntity(
                draft_id="entity-crack",
                source_id="unit_source",
                extractor_name="unit",
                extractor_version="v1",
                scenario="shared",
                entity_id_suggestion="Crack",
                name="Crack",
                label="Defect",
                evidence="crack row",
            ),
            DraftEntity(
                draft_id="entity-gate",
                source_id="unit_source",
                extractor_name="unit",
                extractor_version="v1",
                scenario="shared",
                entity_id_suggestion="GateArea",
                name="Gate area",
                label="Location",
                evidence="gate row",
            ),
        ),
        relations=(
            DraftRelation(
                draft_id="relation-bad-location",
                source_id="unit_source",
                extractor_name="unit",
                extractor_version="v1",
                scenario="shared",
                head="FlowMark",
                relation="HAS_LOCATION",
                tail="Crack",
                evidence="flow mark appears near a crack",
                confidence=0.7,
            ),
            DraftRelation(
                draft_id="relation-good-location",
                source_id="unit_source",
                extractor_name="unit",
                extractor_version="v1",
                scenario="shared",
                head="FlowMark",
                relation="HAS_LOCATION",
                tail="GateArea",
                evidence="flow mark appears near the gate area",
                confidence=0.8,
            ),
        ),
    )

    semantic = project_semantic_layer(draft, profile)

    assert [edge.edge_id for edge in semantic.edges] == [
        "FlowMark|HAS_LOCATION|GateArea|shared"
    ]
    assert semantic.manifest["label_constraint_skipped_relation_ids"] == [
        "relation-bad-location"
    ]


def test_wafer_profile_keeps_spatial_edges_and_filters_bad_cause_shapes() -> None:
    """Wafer projection should preserve spatial traceability but filter bad RCA shapes."""
    profile = profile_for_scenario("wafer")
    draft = DraftKG(
        entities=(
            DraftEntity(
                draft_id="entity-scratch",
                source_id="wafer_source",
                extractor_name="unit",
                extractor_version="v1",
                scenario="wafer",
                entity_id_suggestion="ScratchPattern",
                name="Scratch pattern",
                label="DefectType",
                evidence="Scratch pattern",
            ),
            DraftEntity(
                draft_id="entity-linear",
                source_id="wafer_source",
                extractor_name="unit",
                extractor_version="v1",
                scenario="wafer",
                entity_id_suggestion="LinearSignature",
                name="Linear signature",
                label="Morphology",
                evidence="linear scratch",
            ),
            DraftEntity(
                draft_id="entity-center",
                source_id="wafer_source",
                extractor_name="unit",
                extractor_version="v1",
                scenario="wafer",
                entity_id_suggestion="CenterPattern",
                name="Center pattern",
                label="DefectType",
                evidence="center pattern",
            ),
            DraftEntity(
                draft_id="entity-machine",
                source_id="wafer_source",
                extractor_name="unit",
                extractor_version="v1",
                scenario="wafer",
                entity_id_suggestion="MachineHandlingProblem",
                name="Machine handling problem",
                label="Equipment",
                evidence="machine handling problem",
            ),
        ),
        relations=(
            DraftRelation(
                draft_id="relation-scratch-linear",
                source_id="wafer_source",
                extractor_name="unit",
                extractor_version="v1",
                scenario="wafer",
                head="ScratchPattern",
                relation="HAS_SPATIAL_SIGNATURE",
                tail="LinearSignature",
                evidence="scratch pattern is linear",
                confidence=0.7,
            ),
            DraftRelation(
                draft_id="relation-bad-cause",
                source_id="wafer_source",
                extractor_name="unit",
                extractor_version="v1",
                scenario="wafer",
                head="ScratchPattern",
                relation="CAUSES",
                tail="CenterPattern",
                evidence="bad candidate shape",
                confidence=0.7,
            ),
            DraftRelation(
                draft_id="relation-bad-suggested-cause",
                source_id="wafer_source",
                extractor_name="unit",
                extractor_version="v1",
                scenario="wafer",
                head="ScratchPattern",
                relation="SUGGESTS_ROOT_CAUSE",
                tail="CenterPattern",
                evidence="bad suggested RCA candidate shape",
                confidence=0.7,
            ),
            DraftRelation(
                draft_id="relation-good-plausible-cause",
                source_id="wafer_source",
                extractor_name="unit",
                extractor_version="v1",
                scenario="wafer",
                head="ScratchPattern",
                relation="HAS_PLAUSIBLE_CAUSE",
                tail="MachineHandlingProblem",
                evidence="scratch pattern is caused by machine handling problem",
                confidence=0.7,
            ),
        ),
    )

    semantic = project_semantic_layer(draft, profile)

    assert {edge.edge_id for edge in semantic.edges} == {
        "ScratchPattern|HAS_SPATIAL_SIGNATURE|LinearSignature|wafer",
        "ScratchPattern|HAS_PLAUSIBLE_CAUSE|MachineHandlingProblem|wafer",
    }
    assert semantic.manifest["label_constraint_skipped_relation_ids"] == [
        "relation-bad-cause",
        "relation-bad-suggested-cause",
    ]
