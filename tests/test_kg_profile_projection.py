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
    SemanticProjectionRule,
    build_rca_reasoning_view,
    load_rca_profile,
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
                "relation_families": {"observed_by": "observation"},
                "relation_family_policies": {
                    "observation": {
                        "propagation_enabled": True,
                        "propagation_direction": "reverse",
                        "propagation_priority": 0.6,
                        "attenuation": 0.8,
                        "edge_weight_multiplier": 0.5,
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
    assert manifest["profile_source"] == str(profile_path)
    assert manifest["semantic_projection_rules"]["METRIC_OF"] == {
        "swap_endpoints": True,
        "target_relation": "OBSERVED_BY",
    }


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
    assert rca_view.manifest["relation_family_policies"]["OBSERVATION"] == {
        "attenuation": 0.8,
        "edge_weight_multiplier": 0.5,
        "propagation_direction": "reverse",
        "propagation_enabled": True,
        "propagation_priority": 0.65,
    }


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
