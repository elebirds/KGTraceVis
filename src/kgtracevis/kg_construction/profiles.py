"""Domain packs and RCA profile policies."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SemanticProjectionRule:
    """Profile rule for projecting one source relation into the semantic layer."""

    target_relation: str
    swap_endpoints: bool = False

    def normalized_target(self) -> str:
        """Return the target relation using KG relation naming."""
        return self.target_relation.strip().upper()


@dataclass(frozen=True)
class SemanticDerivedRelationRule:
    """Profile rule for deriving a semantic edge from a two-hop edge pattern."""

    rule_id: str
    left_relation: str
    right_relation: str
    target_relation: str
    relation_family: str = ""
    confidence_policy: str = "min"

    def normalized_left(self) -> str:
        """Return the normalized first-hop relation."""
        return self.left_relation.strip().upper()

    def normalized_right(self) -> str:
        """Return the normalized second-hop relation."""
        return self.right_relation.strip().upper()

    def normalized_target(self) -> str:
        """Return the normalized derived relation."""
        return self.target_relation.strip().upper()


@dataclass(frozen=True)
class RelationFamilyPolicy:
    """RCA defaults for one semantic relation family."""

    propagation_enabled: bool = False
    propagation_direction: str = "forward"
    propagation_priority: float = 0.0
    attenuation: float = 1.0
    edge_weight_multiplier: float = 1.0
    confidence_score_weight: float = 0.5
    priority_score_weight: float = 0.25
    attenuation_score_weight: float = 0.15
    source_trust_score_weight: float = 0.1
    auto_source_trust: float = 0.7
    reviewed_source_trust: float = 1.0
    rejected_source_trust: float = 0.0

    def edge_weight_for(self, base_weight: float) -> float:
        """Return the family-adjusted RCA edge weight."""
        return max(0.0, min(1.0, base_weight * self.edge_weight_multiplier))

    def source_trust_for(self, review_status: str) -> float:
        """Return the source trust score for a construction review status."""
        normalized = review_status.strip().lower()
        if normalized == "reviewed":
            return self.reviewed_source_trust
        if normalized == "rejected":
            return self.rejected_source_trust
        return self.auto_source_trust


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
    semantic_derived_relation_rules: tuple[SemanticDerivedRelationRule, ...] = ()
    relation_families: dict[str, str] = field(default_factory=dict)
    propagation_families: frozenset[str] = frozenset()
    relation_family_policies: dict[str, RelationFamilyPolicy] = field(default_factory=dict)
    root_candidate_labels: frozenset[str] = frozenset()
    observable_labels: frozenset[str] = frozenset()
    task_view: str = "path_ranking_view"
    confidence_policy: str = "source_confidence"
    profile_source: str = "builtin"

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
            "FaultType",
            "AnomalyType",
            "Event",
            "Alert",
            "Service",
            "Host",
            "Pod",
            "Product",
            "Wafer",
            "Defect",
            "DefectType",
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
    observable_labels=frozenset(
        {
            "Variable",
            "Metric",
            "Signal",
            "FaultType",
            "AnomalyType",
            "Event",
            "Alert",
            "Defect",
            "DefectType",
        }
    ),
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


def load_rca_profile(path: str | Path) -> RcaProfile:
    """Load an RCA profile Domain Pack from a JSON file."""
    profile_path = Path(path).expanduser().resolve()
    if profile_path.suffix.lower() != ".json":
        raise ValueError(f"RCA profile packs currently support JSON only: {profile_path}")
    payload = json.loads(profile_path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"RCA profile pack must be a JSON object: {profile_path}")
    return profile_from_mapping(payload, source_path=profile_path)


def profile_from_mapping(
    payload: Mapping[str, Any],
    *,
    source_path: str | Path | None = None,
) -> RcaProfile:
    """Build an `RcaProfile` from a JSON-friendly Domain Pack mapping."""
    domain_id = _required_text(payload, "domain_id")
    scenario = _required_text(payload, "scenario")
    ontology = _required_text(payload, "ontology")
    family_policies = _relation_family_policies(
        payload.get("relation_family_policies", {})
    )
    propagation_families = _string_set(
        payload.get("propagation_families", ()),
        field_name="propagation_families",
        uppercase=True,
    )
    if not propagation_families:
        propagation_families = frozenset(
            family
            for family, policy in family_policies.items()
            if policy.propagation_enabled
        )
    profile_source = str(source_path) if source_path is not None else "mapping"
    return RcaProfile(
        domain_id=domain_id,
        scenario=scenario,
        ontology=ontology,
        keep_labels=_string_set(payload.get("keep_labels", ()), field_name="keep_labels"),
        relation_whitelist=_string_set(
            payload.get("relation_whitelist", ()),
            field_name="relation_whitelist",
            uppercase=True,
        ),
        relation_rewrites=_string_map(
            payload.get("relation_rewrites", {}),
            field_name="relation_rewrites",
            uppercase_keys=True,
            uppercase_values=True,
        ),
        semantic_projection_rules=_semantic_projection_rules(
            payload.get("semantic_projection_rules", {})
        ),
        semantic_derived_relation_rules=_semantic_derived_relation_rules(
            payload.get("semantic_derived_relation_rules", ())
        ),
        relation_families=_string_map(
            payload.get("relation_families", {}),
            field_name="relation_families",
            uppercase_keys=True,
            uppercase_values=True,
        ),
        propagation_families=propagation_families,
        relation_family_policies=family_policies,
        root_candidate_labels=_string_set(
            payload.get("root_candidate_labels", ()),
            field_name="root_candidate_labels",
        ),
        observable_labels=_string_set(
            payload.get("observable_labels", ()),
            field_name="observable_labels",
        ),
        task_view=str(payload.get("task_view") or "path_ranking_view"),
        confidence_policy=str(payload.get("confidence_policy") or "source_confidence"),
        profile_source=profile_source,
    )


def profile_to_manifest(profile: RcaProfile) -> dict[str, object]:
    """Return a JSON-friendly manifest for the active RCA profile."""
    return {
        "artifact_type": "rca_profile_manifest_v1",
        "domain_id": profile.domain_id,
        "scenario": profile.scenario,
        "ontology": profile.ontology,
        "profile_source": profile.profile_source,
        "task_view": profile.task_view,
        "confidence_policy": profile.confidence_policy,
        "keep_labels": sorted(profile.keep_labels),
        "relation_whitelist": sorted(profile.relation_whitelist),
        "relation_rewrites": dict(sorted(profile.relation_rewrites.items())),
        "semantic_projection_rules": {
            relation: {
                "target_relation": rule.normalized_target(),
                "swap_endpoints": rule.swap_endpoints,
            }
            for relation, rule in sorted(profile.semantic_projection_rules.items())
        },
        "semantic_derived_relation_rules": [
            {
                "rule_id": rule.rule_id,
                "left_relation": rule.normalized_left(),
                "right_relation": rule.normalized_right(),
                "target_relation": rule.normalized_target(),
                "relation_family": rule.relation_family.strip().upper(),
                "confidence_policy": rule.confidence_policy,
            }
            for rule in profile.semantic_derived_relation_rules
        ],
        "relation_families": dict(sorted(profile.relation_families.items())),
        "propagation_families": sorted(profile.propagation_families),
        "relation_family_policies": {
            family: {
                "propagation_enabled": policy.propagation_enabled,
                "propagation_direction": policy.propagation_direction,
                "propagation_priority": policy.propagation_priority,
                "attenuation": policy.attenuation,
                "edge_weight_multiplier": policy.edge_weight_multiplier,
                "confidence_score_weight": policy.confidence_score_weight,
                "priority_score_weight": policy.priority_score_weight,
                "attenuation_score_weight": policy.attenuation_score_weight,
                "source_trust_score_weight": policy.source_trust_score_weight,
                "auto_source_trust": policy.auto_source_trust,
                "reviewed_source_trust": policy.reviewed_source_trust,
                "rejected_source_trust": policy.rejected_source_trust,
            }
            for family, policy in sorted(profile.relation_family_policies.items())
        },
        "root_candidate_labels": sorted(profile.root_candidate_labels),
        "observable_labels": sorted(profile.observable_labels),
    }


def _required_text(payload: Mapping[str, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"RCA profile pack requires non-empty {field_name}")
    return value.strip()


def _string_set(
    value: Any,
    *,
    field_name: str,
    uppercase: bool = False,
) -> frozenset[str]:
    if value is None:
        return frozenset()
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise ValueError(f"RCA profile {field_name} must be an array of strings")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"RCA profile {field_name} entries must be non-empty strings")
        text = item.strip()
        items.append(text.upper() if uppercase else text)
    return frozenset(items)


def _string_map(
    value: Any,
    *,
    field_name: str,
    uppercase_keys: bool = False,
    uppercase_values: bool = False,
) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"RCA profile {field_name} must be an object")
    result: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError(f"RCA profile {field_name} keys must be non-empty strings")
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"RCA profile {field_name} values must be non-empty strings")
        normalized_key = key.strip().upper() if uppercase_keys else key.strip()
        normalized_value = item.strip().upper() if uppercase_values else item.strip()
        result[normalized_key] = normalized_value
    return result


def _semantic_projection_rules(value: Any) -> dict[str, SemanticProjectionRule]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("RCA profile semantic_projection_rules must be an object")
    rules: dict[str, SemanticProjectionRule] = {}
    for relation, item in value.items():
        if not isinstance(relation, str) or not relation.strip():
            raise ValueError("RCA profile semantic_projection_rules keys must be strings")
        relation_key = relation.strip().upper()
        if isinstance(item, str):
            rules[relation_key] = SemanticProjectionRule(target_relation=item.strip().upper())
            continue
        if not isinstance(item, Mapping):
            raise ValueError(
                "RCA profile semantic_projection_rules values must be strings or objects"
            )
        target = item.get("target_relation")
        if not isinstance(target, str) or not target.strip():
            raise ValueError(
                "RCA profile semantic_projection_rules objects require target_relation"
            )
        rules[relation_key] = SemanticProjectionRule(
            target_relation=target.strip().upper(),
            swap_endpoints=_bool_value(
                item,
                "swap_endpoints",
                default=False,
                context="semantic_projection_rules",
            ),
        )
    return rules


def _semantic_derived_relation_rules(value: Any) -> tuple[SemanticDerivedRelationRule, ...]:
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise ValueError("RCA profile semantic_derived_relation_rules must be an array")
    rules: list[SemanticDerivedRelationRule] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise ValueError("RCA profile derived relation rules must be objects")
        rule_id = str(item.get("rule_id") or f"derived_rule_{index + 1}").strip()
        left_relation = _required_rule_text(item, "left_relation", rule_id=rule_id)
        right_relation = _required_rule_text(item, "right_relation", rule_id=rule_id)
        target_relation = _required_rule_text(item, "target_relation", rule_id=rule_id)
        confidence_policy = str(item.get("confidence_policy") or "min").strip().lower()
        if confidence_policy not in {"min", "average", "product"}:
            raise ValueError(
                "RCA profile derived relation confidence_policy must be "
                "min, average, or product"
            )
        rules.append(
            SemanticDerivedRelationRule(
                rule_id=rule_id,
                left_relation=left_relation.upper(),
                right_relation=right_relation.upper(),
                target_relation=target_relation.upper(),
                relation_family=str(item.get("relation_family") or "").strip().upper(),
                confidence_policy=confidence_policy,
            )
        )
    return tuple(rules)


def _required_rule_text(
    payload: Mapping[str, Any],
    field_name: str,
    *,
    rule_id: str,
) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"RCA profile derived relation rule {rule_id} requires {field_name}")
    return value.strip()


def _relation_family_policies(value: Any) -> dict[str, RelationFamilyPolicy]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("RCA profile relation_family_policies must be an object")
    policies: dict[str, RelationFamilyPolicy] = {}
    for family, item in value.items():
        if not isinstance(family, str) or not family.strip():
            raise ValueError("RCA profile relation_family_policies keys must be strings")
        if not isinstance(item, Mapping):
            raise ValueError("RCA profile relation_family_policies values must be objects")
        policies[family.strip().upper()] = RelationFamilyPolicy(
            propagation_enabled=_bool_value(
                item,
                "propagation_enabled",
                default=False,
                context="relation_family_policies",
            ),
            propagation_direction=str(item.get("propagation_direction") or "forward").lower(),
            propagation_priority=_float_policy_value(
                item,
                "propagation_priority",
                default=0.0,
            ),
            attenuation=_float_policy_value(item, "attenuation", default=1.0),
            edge_weight_multiplier=_float_policy_value(
                item,
                "edge_weight_multiplier",
                default=1.0,
            ),
            confidence_score_weight=_float_policy_value(
                item,
                "confidence_score_weight",
                default=0.5,
            ),
            priority_score_weight=_float_policy_value(
                item,
                "priority_score_weight",
                default=0.25,
            ),
            attenuation_score_weight=_float_policy_value(
                item,
                "attenuation_score_weight",
                default=0.15,
            ),
            source_trust_score_weight=_float_policy_value(
                item,
                "source_trust_score_weight",
                default=0.1,
            ),
            auto_source_trust=_float_policy_value(
                item,
                "auto_source_trust",
                default=0.7,
            ),
            reviewed_source_trust=_float_policy_value(
                item,
                "reviewed_source_trust",
                default=1.0,
            ),
            rejected_source_trust=_float_policy_value(
                item,
                "rejected_source_trust",
                default=0.0,
            ),
        )
    return policies


def _bool_value(
    payload: Mapping[str, Any],
    field_name: str,
    *,
    default: bool,
    context: str,
) -> bool:
    value = payload.get(field_name, default)
    if not isinstance(value, bool):
        raise ValueError(f"RCA profile {context} {field_name} must be boolean")
    return value


def _float_policy_value(
    payload: Mapping[str, Any],
    field_name: str,
    *,
    default: float,
) -> float:
    value = payload.get(field_name, default)
    if isinstance(value, bool):
        raise ValueError(f"RCA profile policy {field_name} must be numeric")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"RCA profile policy {field_name} must be numeric") from exc
