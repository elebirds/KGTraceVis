"""Domain packs and RCA profile policies."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RcaProfile:
    """Scenario-specific policy for projection, RCA view, and review priority."""

    domain_id: str
    scenario: str
    ontology: str
    keep_labels: frozenset[str]
    relation_whitelist: frozenset[str]
    relation_rewrites: dict[str, str] = field(default_factory=dict)
    relation_families: dict[str, str] = field(default_factory=dict)
    propagation_families: frozenset[str] = frozenset()
    root_candidate_labels: frozenset[str] = frozenset()
    observable_labels: frozenset[str] = frozenset()
    task_view: str = "path_ranking_view"
    confidence_policy: str = "source_confidence"

    def rewrite_relation(self, relation: str) -> str:
        """Return the profile-normalized relation name."""
        normalized = relation.strip().upper()
        return self.relation_rewrites.get(normalized, normalized)

    def relation_family_for(self, relation: str, explicit: str = "") -> str:
        """Return relation family from explicit metadata or profile defaults."""
        if explicit.strip():
            return explicit.strip().upper()
        return self.relation_families.get(self.rewrite_relation(relation), "")

    def propagation_enabled_for(self, relation_family: str, explicit: bool | None = None) -> bool:
        """Return whether a relation family participates in propagation."""
        if explicit is not None:
            return explicit
        return relation_family in self.propagation_families


GENERIC_PROFILE = RcaProfile(
    domain_id="generic",
    scenario="shared",
    ontology="generic_rca_v1",
    keep_labels=frozenset(
        {
            "Equipment",
            "Component",
            "Variable",
            "Metric",
            "Signal",
            "Fault",
            "Event",
            "Alert",
            "Service",
            "Host",
            "Pod",
            "Product",
            "Wafer",
            "Defect",
            "Morphology",
            "ProcessUnit",
            "RootCause",
        }
    ),
    relation_whitelist=frozenset(
        {
            "OBSERVED_BY",
            "CAUSES",
            "AFFECTS",
            "DEPENDS_ON",
            "PART_OF",
            "ALIGNS_TO",
            "HAS_COMPONENT",
            "HAS_MORPHOLOGY",
            "HAS_LOCATION",
            "HAS_PLAUSIBLE_CAUSE",
            "SUGGESTS_ROOT_CAUSE",
        }
    ),
    relation_rewrites={
        "MEASURES": "OBSERVED_BY",
        "METRIC_OF": "OBSERVED_BY",
        "CONTAINS": "HAS_COMPONENT",
        "CALLS": "DEPENDS_ON",
    },
    relation_families={
        "OBSERVED_BY": "OBSERVATION",
        "CAUSES": "CAUSES",
        "AFFECTS": "AFFECTS",
        "DEPENDS_ON": "DEPENDS_ON",
        "PART_OF": "PART_OF",
        "ALIGNS_TO": "ALIGNS_TO",
        "HAS_COMPONENT": "PART_OF",
        "HAS_PLAUSIBLE_CAUSE": "CAUSES",
        "SUGGESTS_ROOT_CAUSE": "CAUSES",
    },
    propagation_families=frozenset({"CAUSES", "AFFECTS", "DEPENDS_ON", "OBSERVATION"}),
    root_candidate_labels=frozenset({"Fault", "RootCause", "Component", "Equipment"}),
    observable_labels=frozenset({"Variable", "Metric", "Signal", "Event", "Alert", "Defect"}),
)


TEP_PROFILE = RcaProfile(
    domain_id="tep",
    scenario="tep",
    ontology="tep_rca_v1",
    keep_labels=frozenset(
        {
            "Component",
            "ControlLoop",
            "Equipment",
            "Fault",
            "FaultAnchor",
            "FaultEvent",
            "Module",
            "ProcessUnit",
            "RootCause",
            "SemanticConcept",
            "SignalNode",
            "Stream",
            "Variable",
        }
    ),
    relation_whitelist=frozenset(
        {
            "ACTS_ON",
            "ALIGNS_TO",
            "ANALYZES",
            "BELONGS_TO",
            "CARRIES_COMPONENT",
            "CAUSES",
            "CONNECTS_TO",
            "DRIVES_DEMAND_FOR",
            "FLOWS_TO",
            "HAS_COMPONENT",
            "OBSERVED_BY",
            "PART_OF",
            "REALIZES",
            "SUGGESTS_ROOT_CAUSE",
            "SUPPLIES",
        }
    ),
    relation_rewrites={
        "CONTROLS": "ACTS_ON",
        "CONTROLS_FLOW_OF": "ACTS_ON",
        "MEASURES": "OBSERVED_BY",
        "MEASURES_FLOW_OF": "OBSERVED_BY",
        "MEASURES_COMPOSITION_OF": "OBSERVED_BY",
    },
    relation_families={
        "OBSERVED_BY": "OBSERVATION",
        "ACTS_ON": "CONTROL",
        "FLOWS_TO": "MATERIAL_FLOW",
        "SUPPLIES": "ENERGY_TRANSFER",
        "CONNECTS_TO": "PHASE_CHANGE",
        "CARRIES_COMPONENT": "COMPOSITION",
        "CAUSES": "FAULT_SOURCE",
        "SUGGESTS_ROOT_CAUSE": "FAULT_SOURCE",
        "ALIGNS_TO": "ALIGNMENT",
        "BELONGS_TO": "SEMANTIC_SUPPORT",
        "PART_OF": "SEMANTIC_SUPPORT",
        "REALIZES": "SEMANTIC_SUPPORT",
        "HAS_COMPONENT": "COMPOSITION",
    },
    propagation_families=frozenset(
        {
            "OBSERVATION",
            "CONTROL",
            "MATERIAL_FLOW",
            "ENERGY_TRANSFER",
            "PHASE_CHANGE",
            "COMPOSITION",
            "FAULT_SOURCE",
        }
    ),
    root_candidate_labels=frozenset({"Component", "Equipment", "Fault", "FaultAnchor"}),
    observable_labels=frozenset({"Variable", "SignalNode", "FaultAnchor"}),
    task_view="root_kgd_view",
)


def profile_for_scenario(scenario: str) -> RcaProfile:
    """Return the default profile for a scenario."""
    if scenario == "tep":
        return TEP_PROFILE
    return GENERIC_PROFILE
