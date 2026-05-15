"""Domain packs and RCA profile policies."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SemanticProjectionRule:
    """Profile rule for projecting one source relation into the semantic layer."""

    target_relation: str
    swap_endpoints: bool = False

    def normalized_target(self) -> str:
        """Return the target relation using KG relation naming."""
        return self.target_relation.strip().upper()


@dataclass(frozen=True)
class RelationFamilyPolicy:
    """RCA defaults for one semantic relation family."""

    propagation_enabled: bool = False
    propagation_direction: str = "forward"
    propagation_priority: float = 0.0
    attenuation: float = 1.0
    edge_weight_multiplier: float = 1.0

    def edge_weight_for(self, base_weight: float) -> float:
        """Return the family-adjusted RCA edge weight."""
        return max(0.0, min(1.0, base_weight * self.edge_weight_multiplier))


@dataclass(frozen=True)
class RcaProfile:
    """Scenario-specific policy for projection, RCA view, and review priority."""

    domain_id: str
    scenario: str
    ontology: str
    keep_labels: frozenset[str]
    relation_whitelist: frozenset[str]
    relation_rewrites: dict[str, str] = field(default_factory=dict)
    semantic_projection_rules: dict[str, SemanticProjectionRule] = field(default_factory=dict)
    relation_families: dict[str, str] = field(default_factory=dict)
    propagation_families: frozenset[str] = frozenset()
    relation_family_policies: dict[str, RelationFamilyPolicy] = field(default_factory=dict)
    root_candidate_labels: frozenset[str] = frozenset()
    observable_labels: frozenset[str] = frozenset()
    task_view: str = "path_ranking_view"
    confidence_policy: str = "source_confidence"

    def rewrite_relation(self, relation: str) -> str:
        """Return the profile-normalized relation name."""
        normalized = relation.strip().upper()
        if normalized in self.semantic_projection_rules:
            return self.semantic_projection_rules[normalized].normalized_target()
        return self.relation_rewrites.get(normalized, normalized)

    def projection_rule_for(self, relation: str) -> SemanticProjectionRule:
        """Return the semantic projection rule for a source relation."""
        normalized = relation.strip().upper()
        return self.semantic_projection_rules.get(
            normalized,
            SemanticProjectionRule(target_relation=self.rewrite_relation(normalized)),
        )

    def relation_family_for(self, relation: str, explicit: str = "") -> str:
        """Return relation family from explicit metadata or profile defaults."""
        if explicit.strip():
            return explicit.strip().upper()
        return self.relation_families.get(self.rewrite_relation(relation), "")

    def propagation_enabled_for(self, relation_family: str, explicit: bool | None = None) -> bool:
        """Return whether a relation family participates in propagation."""
        if explicit is not None:
            return explicit
        return self.relation_family_policy_for(relation_family).propagation_enabled

    def relation_family_policy_for(self, relation_family: str) -> RelationFamilyPolicy:
        """Return RCA policy defaults for a relation family."""
        family = relation_family.strip().upper()
        if family in self.relation_family_policies:
            return self.relation_family_policies[family]
        enabled = family in self.propagation_families
        return RelationFamilyPolicy(
            propagation_enabled=enabled,
            propagation_priority=1.0 if enabled else 0.0,
        )

    def propagation_direction_for(self, relation_family: str, explicit: str = "") -> str:
        """Return propagation direction from explicit metadata or profile policy."""
        if explicit.strip():
            return explicit.strip().lower()
        return self.relation_family_policy_for(relation_family).propagation_direction

    def propagation_priority_for(
        self,
        relation_family: str,
        explicit: float | None = None,
    ) -> float:
        """Return propagation priority from explicit metadata or profile policy."""
        if explicit is not None:
            return explicit
        return self.relation_family_policy_for(relation_family).propagation_priority

    def attenuation_for(self, relation_family: str, explicit: float | None = None) -> float:
        """Return propagation attenuation from explicit metadata or profile policy."""
        if explicit is not None:
            return explicit
        return self.relation_family_policy_for(relation_family).attenuation

    def edge_weight_for(
        self,
        relation_family: str,
        *,
        base_weight: float,
        explicit: float | None = None,
    ) -> float:
        """Return RCA edge weight from explicit metadata or profile policy."""
        if explicit is not None:
            return explicit
        return self.relation_family_policy_for(relation_family).edge_weight_for(base_weight)


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
    relation_family_policies={
        "OBSERVATION": RelationFamilyPolicy(
            propagation_enabled=True,
            propagation_direction="reverse",
            propagation_priority=0.7,
            attenuation=0.85,
            edge_weight_multiplier=0.8,
        ),
        "CAUSES": RelationFamilyPolicy(
            propagation_enabled=True,
            propagation_direction="forward",
            propagation_priority=1.0,
            attenuation=1.0,
        ),
        "AFFECTS": RelationFamilyPolicy(
            propagation_enabled=True,
            propagation_direction="forward",
            propagation_priority=0.85,
            attenuation=0.9,
        ),
        "DEPENDS_ON": RelationFamilyPolicy(
            propagation_enabled=True,
            propagation_direction="reverse",
            propagation_priority=0.6,
            attenuation=0.8,
            edge_weight_multiplier=0.9,
        ),
        "PART_OF": RelationFamilyPolicy(propagation_enabled=False),
        "ALIGNS_TO": RelationFamilyPolicy(propagation_enabled=False),
    },
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
    relation_family_policies={
        "OBSERVATION": RelationFamilyPolicy(
            propagation_enabled=True,
            propagation_direction="reverse",
            propagation_priority=0.75,
            attenuation=0.85,
            edge_weight_multiplier=0.8,
        ),
        "CONTROL": RelationFamilyPolicy(
            propagation_enabled=True,
            propagation_direction="forward",
            propagation_priority=0.9,
            attenuation=0.9,
        ),
        "MATERIAL_FLOW": RelationFamilyPolicy(
            propagation_enabled=True,
            propagation_direction="forward",
            propagation_priority=0.8,
            attenuation=0.85,
        ),
        "ENERGY_TRANSFER": RelationFamilyPolicy(
            propagation_enabled=True,
            propagation_direction="forward",
            propagation_priority=0.75,
            attenuation=0.85,
        ),
        "PHASE_CHANGE": RelationFamilyPolicy(
            propagation_enabled=True,
            propagation_direction="forward",
            propagation_priority=0.7,
            attenuation=0.8,
        ),
        "COMPOSITION": RelationFamilyPolicy(
            propagation_enabled=True,
            propagation_direction="forward",
            propagation_priority=0.65,
            attenuation=0.8,
        ),
        "FAULT_SOURCE": RelationFamilyPolicy(
            propagation_enabled=True,
            propagation_direction="reverse",
            propagation_priority=1.0,
            attenuation=1.0,
            edge_weight_multiplier=0.7,
        ),
        "ALIGNMENT": RelationFamilyPolicy(propagation_enabled=False),
        "SEMANTIC_SUPPORT": RelationFamilyPolicy(propagation_enabled=False),
    },
    root_candidate_labels=frozenset({"Component", "Equipment", "Fault", "FaultAnchor"}),
    observable_labels=frozenset({"Variable", "SignalNode", "FaultAnchor"}),
    task_view="root_kgd_view",
)


def profile_for_scenario(scenario: str) -> RcaProfile:
    """Return the default profile for a scenario."""
    if scenario == "tep":
        return TEP_PROFILE
    return GENERIC_PROFILE
