# mypy: ignore-errors
"""Root-KGD baseline ranking on the RCA graph."""

# ruff: noqa

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Iterable

from kgtracevis.workflows.tep_root_kgd.anchor_memory import (
    anchor_memory_alignment_details,
    anchor_memory_payload,
    build_anchor_memory_profiles,
)
from kgtracevis.workflows.tep_root_kgd.assets import read_jsonl, write_jsonl
from kgtracevis.workflows.tep_root_kgd.anchor_discriminators import load_anchor_discriminators
from kgtracevis.workflows.tep_root_kgd.propagation import (
    build_propagation_graph,
    candidate_source_ids,
    default_relation_params,
    incident_neighbors,
    simulate_propagation,
    trace_path,
)
from kgtracevis.workflows.tep_root_kgd.rca_signal_utils import (
    contribution_weight as _contribution_weight,
    dense_cosine_similarity as cosine_similarity,
    weighted_contributions as _weighted_contributions,
)
from kgtracevis.workflows.tep_root_kgd.scenario_dynamic_features import (
    load_scenario_dynamic_features,
)
from kgtracevis.workflows.tep_root_kgd.rbc import build_rbc, load_tep_mapping, stable_id


ALLOWED_CANDIDATE_TYPES = {"Equipment", "Stream", "Variable", "Component", "FaultAnchor"}
DEFAULT_TOP_VARIABLE_COUNT = 8
DEFAULT_TOP_K = 3
ROOT_SCORE_COVERAGE_PENALTY = 0.12
ROOT_SCORE_ENTROPY_PENALTY = 0.03
CANDIDATE_TYPE_RANKING_BIAS = {
    "FaultAnchor": 0.06,
    "Equipment": 0.03,
    "Variable": 0.0,
    "Stream": -0.03,
    "Component": -0.03,
}
CANDIDATE_ROLE_RANKING_BIAS = {
    "root_cause_anchor": 0.10,
    "equipment_anchor": 0.03,
    "stream_anchor": 0.0,
    "composition_anchor": 0.02,
    "actuator": -0.03,
    "observation": -0.08,
    "support_only": -0.20,
}
ROOT_CAUSE_DISCRIMINATOR_WEIGHT = 0.28
ROOT_CAUSE_PROXY_PROMOTION_MARGIN = 0.09
ROOT_CAUSE_PROXY_PROMOTION_BONUS = 0.09
SEPARATOR_FAMILY_ID = "separator_cooling_family"
SEPARATOR_FAMILY_ANCHOR_IDS = (
    "faultanchor:separator_cooling_inlet_temperature",
    "faultanchor:separator_coolant_valve_stiction",
    "faultanchor:condenser_heat_transfer",
)
SEPARATOR_FAMILY_ACTIVATION_THRESHOLD = 0.60
SEPARATOR_FAMILY_MAX_COMPETITIVE_RANK = 3
SEPARATOR_FAMILY_MAX_SCORE_GAP = 0.12
SEPARATOR_FAMILY_SHARED_ALIGNMENT_WEIGHT = 0.30
SEPARATOR_FAMILY_UNIQUE_ALIGNMENT_WEIGHT = 0.20
CONDENSER_DYNAMIC_TARGET_ID = "faultanchor:condenser_heat_transfer"
CONDENSER_DYNAMIC_STD_FEATURE_ID = "xmeas_22__std"
CONDENSER_DYNAMIC_MEAN_FEATURE_ID = "xmeas_22__mean"
CONDENSER_DYNAMIC_SEPARATOR_TEMP_STD_FEATURE_ID = "xmeas_11__std"
CONDENSER_DYNAMIC_STD_THRESHOLD = 5.0
CONDENSER_DYNAMIC_MEAN_THRESHOLD = -0.5
CONDENSER_DYNAMIC_SEPARATOR_TEMP_STD_THRESHOLD = 4.0
CONDENSER_DYNAMIC_STD_SCALE = 7.0
CONDENSER_DYNAMIC_MEAN_SCALE = 4.5
CONDENSER_DYNAMIC_SEPARATOR_TEMP_STD_SCALE = 2.5
CONDENSER_DYNAMIC_STD_WEIGHT = 0.45
CONDENSER_DYNAMIC_MEAN_WEIGHT = 0.40
CONDENSER_DYNAMIC_SEPARATOR_TEMP_STD_WEIGHT = 0.15
CONDENSER_DYNAMIC_MAX_BONUS = 1.40
CONDENSER_DYNAMIC_MAX_COMPETITIVE_RANK = 3
CONDENSER_DYNAMIC_MAX_SCORE_GAP = 1.50
STREAM4_COLD_RESPONSE_TARGET_ID = "faultanchor:stream_4_feed_temperature"
STREAM4_COLD_RESPONSE_RIVAL_ID = "faultanchor:stripper_heat_transfer"
STREAM4_COLD_RESPONSE_STRIPPER_TEMP_MEAN_FEATURE_ID = "xmeas_18__mean"
STREAM4_COLD_RESPONSE_STEAM_FLOW_MEAN_FEATURE_ID = "xmeas_19__mean"
STREAM4_COLD_RESPONSE_STEAM_FLOW_STD_FEATURE_ID = "xmeas_19__std"
STREAM4_COLD_RESPONSE_STRIPPER_TEMP_MEAN_THRESHOLD = -1.0
STREAM4_COLD_RESPONSE_STEAM_FLOW_MEAN_THRESHOLD = 0.5
STREAM4_COLD_RESPONSE_STRIPPER_TEMP_MEAN_SCALE = 0.5
STREAM4_COLD_RESPONSE_STEAM_FLOW_MEAN_SCALE = 0.4
STREAM4_COLD_RESPONSE_STEAM_FLOW_STD_MIN = 1.0
STREAM4_COLD_RESPONSE_STEAM_FLOW_STD_MAX = 2.2
STREAM4_COLD_RESPONSE_STRIPPER_TEMP_WEIGHT = 0.45
STREAM4_COLD_RESPONSE_STEAM_FLOW_WEIGHT = 0.35
STREAM4_COLD_RESPONSE_STEAM_FLOW_STD_WEIGHT = 0.20
STREAM4_COLD_RESPONSE_MAX_BONUS = 0.80
STREAM4_COLD_RESPONSE_MAX_COMPETITIVE_RANK = 2
STREAM4_COLD_RESPONSE_MAX_SCORE_GAP = 0.75
STREAM4_PROXY_CHASE_TARGET_ID = "faultanchor:stream_4_feed_temperature"
STREAM4_PROXY_CHASE_RIVAL_IDS = frozenset(
    {
        "faultanchor:separator_coolant_valve_stiction",
        "faultanchor:multi_valve_stiction",
    }
)
STREAM4_PROXY_CHASE_MAX_COMPETITIVE_RANK = 4
STREAM4_PROXY_CHASE_MAX_SCORE_GAP = 0.12
STREAM4_PROXY_CHASE_MIN_UNIQUE_ALIGNMENT = 0.30
STREAM4_PROXY_CHASE_MIN_DISCRIMINATOR_ALIGNMENT = 0.25
STREAM4_PROXY_CHASE_MAX_RIVAL_DISCRIMINATOR_ALIGNMENT = 0.12
STREAM4_PROXY_CHASE_MAX_MEMORY_GAP = 0.25
STREAM4_PROXY_CHASE_MAX_BONUS = 0.14
STREAM4_PROXY_CHASE_WIN_MARGIN = 0.01
STREAM2_COMPETITION_TARGET_ID = "faultanchor:stream_2_feed_temperature"
STREAM2_COMPETITION_RIVAL_ID = "faultanchor:separator_coolant_valve_stiction"
STREAM2_COMPETITION_REACTOR_COOLING_MEAN_FEATURE_ID = "xmeas_21__mean"
STREAM2_COMPETITION_OFFGAS_B_MEAN_FEATURE_ID = "xmeas_30__mean"
STREAM2_COMPETITION_REACTOR_COOLING_ABS_THRESHOLD = 0.114
STREAM2_COMPETITION_REACTOR_COOLING_ABS_SCALE = 0.03
STREAM2_COMPETITION_OFFGAS_B_MEAN_THRESHOLD = 0.0612
STREAM2_COMPETITION_OFFGAS_B_MEAN_SCALE = 0.0012
STREAM2_COMPETITION_MAX_BONUS = 0.50
STREAM2_COMPETITION_MAX_COMPETITIVE_RANK = 3
STREAM2_COMPETITION_MAX_SCORE_GAP = 0.45
STREAM2_COMPETITION_EXTENDED_RIVAL_ID = "faultanchor:condenser_heat_transfer"
STREAM2_COMPETITION_EXTENDED_MIN_SIGNATURE = 0.95
STREAM2_COMPETITION_EXTENDED_MAX_COMPETITIVE_RANK = 5
STREAM2_COMPETITION_EXTENDED_MAX_SCORE_GAP = 0.35
STREAM2_COMPETITION_EXTENDED_MAX_TOP_PAIR_GAP = 0.12
STREAM2_COMPETITION_EXTENDED_FAMILY_ACTIVATION_THRESHOLD = 0.50
SEPARATOR_VALVE_TIEBREAK_TARGET_ID = "faultanchor:separator_coolant_valve_stiction"
SEPARATOR_VALVE_TIEBREAK_RIVAL_ID = "faultanchor:condenser_heat_transfer"
SEPARATOR_VALVE_TIEBREAK_FAMILY_ACTIVATION_THRESHOLD = 0.50
SEPARATOR_VALVE_TIEBREAK_MAX_SCORE_GAP = 0.12
SEPARATOR_VALVE_TIEBREAK_MAX_STREAM2_SIGNATURE = 0.20
SEPARATOR_VALVE_TIEBREAK_MIN_MEMORY_ADVANTAGE = 0.005
SEPARATOR_VALVE_TIEBREAK_WIN_MARGIN = 0.01
SEPARATOR_VALVE_TIEBREAK_MAX_BONUS = 0.14
STRIPPER_TIEBREAK_TARGET_ID = "faultanchor:stripper_heat_transfer"
STRIPPER_TIEBREAK_RIVAL_ID = "faultanchor:stream_4_feed_temperature"
STRIPPER_TIEBREAK_MAX_SCORE_GAP = 0.08
STRIPPER_TIEBREAK_MIN_MEMORY_ADVANTAGE = 0.04
STRIPPER_TIEBREAK_MIN_UNIQUE_ADVANTAGE = 0.10
STRIPPER_TIEBREAK_WIN_MARGIN = 0.01
STRIPPER_TIEBREAK_MAX_BONUS = 0.10
STREAM4_VARIANCE_TARGET_ID = "faultanchor:stream_4_feed_temperature"
STREAM4_VARIANCE_RIVAL_IDS = frozenset(
    {
        "faultanchor:stripper_heat_transfer",
        "faultanchor:separator_coolant_valve_stiction",
        "faultanchor:stream_2_feed_temperature",
    }
)
STREAM4_VARIANCE_STRIPPER_TEMP_STD_FEATURE_ID = "xmeas_18__std"
STREAM4_VARIANCE_STEAM_FLOW_STD_FEATURE_ID = "xmeas_19__std"
STREAM4_VARIANCE_STRIPPER_TEMP_STD_THRESHOLD = 1.20
STREAM4_VARIANCE_STRIPPER_TEMP_STD_SCALE = 0.35
STREAM4_VARIANCE_TEMP_STEAM_MARGIN_THRESHOLD = 0.40
STREAM4_VARIANCE_TEMP_STEAM_MARGIN_SCALE = 0.30
STREAM4_VARIANCE_MAX_COMPETITIVE_RANK = 4
STREAM4_VARIANCE_MAX_SCORE_GAP = 0.14
STREAM4_VARIANCE_MAX_BONUS = 0.14
STREAM4_VARIANCE_WIN_MARGIN = 0.01
STRIPPER_THERMAL_TARGET_ID = "faultanchor:stripper_heat_transfer"
STRIPPER_THERMAL_RIVAL_IDS = frozenset(
    {
        "faultanchor:stream_4_feed_temperature",
        "faultanchor:separator_coolant_valve_stiction",
    }
)
STRIPPER_THERMAL_STEAM_FLOW_STD_FEATURE_ID = "xmeas_19__std"
STRIPPER_THERMAL_STRIPPER_TEMP_STD_FEATURE_ID = "xmeas_18__std"
STRIPPER_THERMAL_STEAM_FLOW_STD_THRESHOLD = 1.20
STRIPPER_THERMAL_STEAM_FLOW_STD_SCALE = 0.30
STRIPPER_THERMAL_STEAM_TEMP_MARGIN_THRESHOLD = 0.10
STRIPPER_THERMAL_STEAM_TEMP_MARGIN_SCALE = 0.12
STRIPPER_THERMAL_MAX_COMPETITIVE_RANK = 5
STRIPPER_THERMAL_MAX_SCORE_GAP = 0.16
STRIPPER_THERMAL_MAX_BONUS = 0.15
STRIPPER_THERMAL_WIN_MARGIN = 0.01
CONDENSER_MODERATE_TARGET_ID = "faultanchor:condenser_heat_transfer"
CONDENSER_MODERATE_RIVAL_IDS = frozenset(
    {
        "faultanchor:separator_coolant_valve_stiction",
        "faultanchor:stream_2_feed_temperature",
        "faultanchor:multi_valve_stiction",
    }
)
CONDENSER_MODERATE_STD_FEATURE_ID = "xmeas_22__std"
CONDENSER_MODERATE_MEAN_FEATURE_ID = "xmeas_22__mean"
CONDENSER_MODERATE_SEPARATOR_TEMP_STD_FEATURE_ID = "xmeas_11__std"
CONDENSER_MODERATE_STD_THRESHOLD = 1.00
CONDENSER_MODERATE_STD_SCALE = 0.60
CONDENSER_MODERATE_MEAN_THRESHOLD = -0.12
CONDENSER_MODERATE_MEAN_SCALE = 0.28
CONDENSER_MODERATE_SEPARATOR_TEMP_STD_THRESHOLD = 0.80
CONDENSER_MODERATE_SEPARATOR_TEMP_STD_SCALE = 0.25
CONDENSER_MODERATE_MAX_COMPETITIVE_RANK = 5
CONDENSER_MODERATE_MAX_SCORE_GAP = 0.18
CONDENSER_MODERATE_MAX_BONUS = 0.16
CONDENSER_MODERATE_WIN_MARGIN = 0.01
SEPARATOR_WARM_TARGET_ID = "faultanchor:separator_coolant_valve_stiction"
SEPARATOR_WARM_RIVAL_ID = "faultanchor:stream_2_feed_temperature"
SEPARATOR_WARM_COOLANT_STD_FEATURE_ID = "xmeas_22__std"
SEPARATOR_WARM_SEPARATOR_TEMP_STD_FEATURE_ID = "xmeas_11__std"
SEPARATOR_WARM_COOLANT_MEAN_FEATURE_ID = "xmeas_22__mean"
SEPARATOR_WARM_STRIPPER_TEMP_MEAN_FEATURE_ID = "xmeas_18__mean"
SEPARATOR_WARM_STEAM_FLOW_MEAN_FEATURE_ID = "xmeas_19__mean"
SEPARATOR_WARM_STEAM_MV_MEAN_FEATURE_ID = "xmv_9__mean"
SEPARATOR_WARM_COOLANT_STD_THRESHOLD = 1.00
SEPARATOR_WARM_COOLANT_STD_SCALE = 0.12
SEPARATOR_WARM_SEPARATOR_TEMP_STD_THRESHOLD = 0.88
SEPARATOR_WARM_SEPARATOR_TEMP_STD_SCALE = 0.10
SEPARATOR_WARM_COOLANT_MEAN_THRESHOLD = -0.05
SEPARATOR_WARM_COOLANT_MEAN_SCALE = 0.10
SEPARATOR_WARM_POSITIVE_DRIFT_THRESHOLD = 0.0
SEPARATOR_WARM_POSITIVE_DRIFT_SCALE = 0.05
SEPARATOR_WARM_MAX_SCORE_GAP = 0.14
SEPARATOR_WARM_MAX_BONUS = 0.14
SEPARATOR_WARM_WIN_MARGIN = 0.01


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: (
                        value
                        if isinstance(value, (str, int, float, bool)) or value is None
                        else json.dumps(value, ensure_ascii=False, sort_keys=True)
                    )
                    for key, value in row.items()
                }
            )


def _load_rbc_scenarios(project_root: Path) -> list[dict[str, object]]:
    path = project_root / "data" / "processed" / "rca" / "rbc_contributions.jsonl"
    if not path.exists():
        build_rbc(project_root)
    return read_jsonl(path)


def variable_order(project_root: Path) -> list[str]:
    return [str(row["kg_entity_id"]) for row in load_tep_mapping(project_root)]


def _downstream_contribution_signal(
    graph: dict[str, object],
    source_id: str,
    contributions: dict[str, float],
    *,
    max_depth: int = 3,
    top_k: int = 4,
) -> tuple[float, str]:
    frontier: list[tuple[str, int, float]] = [(source_id, 0, 1.0)]
    best_strength_by_node: dict[str, float] = {source_id: 1.0}
    variable_hits: dict[str, float] = {}

    while frontier:
        node_id, depth, strength = frontier.pop(0)
        if depth >= max_depth:
            continue
        for edge in graph["outgoing"].get(node_id, []):
            tail_id = str(edge["tail_id"])
            next_strength = float(strength) * float(edge.get("edge_weight", 1.0)) * 0.92
            if next_strength <= 1e-6:
                continue
            previous_strength = best_strength_by_node.get(tail_id, 0.0)
            if next_strength <= previous_strength and tail_id != source_id:
                continue
            best_strength_by_node[tail_id] = next_strength
            if str(graph["nodes"].get(tail_id, {}).get("entity_type", "")) == "Variable":
                weighted_value = float(contributions.get(tail_id, 0.0)) * next_strength
                if weighted_value > variable_hits.get(tail_id, 0.0):
                    variable_hits[tail_id] = weighted_value
            frontier.append((tail_id, depth + 1, next_strength))

    ranked_hits = sorted(variable_hits.items(), key=lambda item: (-item[1], item[0]))
    if not ranked_hits:
        return 0.0, ""
    signal = sum(value for _, value in ranked_hits[:top_k])
    return round(signal, 8), str(ranked_hits[0][0])


def enumerate_candidates(
    graph: dict[str, object],
    scenario: dict[str, object],
    *,
    top_variable_count: int = DEFAULT_TOP_VARIABLE_COUNT,
) -> list[dict[str, object]]:
    candidate_ids = candidate_source_ids(graph, ALLOWED_CANDIDATE_TYPES)
    raw_contributions = {
        str(entity_id): float(value)
        for entity_id, value in scenario["graph_contributions"].items()
    }
    weighted_contributions = _weighted_contributions(raw_contributions, graph)
    top_variables = [
        entity_id
        for entity_id, _ in sorted(
            weighted_contributions.items(),
            key=lambda item: (-item[1], item[0]),
        )[:top_variable_count]
    ]
    candidates: dict[str, dict[str, object]] = {}
    for variable_id in top_variables:
        if variable_id in candidate_ids and graph["nodes"][variable_id]["entity_type"] == "Variable":
            score = weighted_contributions.get(variable_id, 0.0)
            candidates[variable_id] = {
                "candidate_id": variable_id,
                "priority_level": 1,
                "adjacent_contribution": score,
                "direct_contribution": score,
                "support_contribution": score,
                "seed_variable_id": variable_id,
            }
        for neighbor_id, _ in incident_neighbors(graph, variable_id):
            if neighbor_id not in candidate_ids:
                continue
            previous = candidates.get(neighbor_id)
            score = weighted_contributions.get(variable_id, 0.0)
            if previous is None or score > float(previous["adjacent_contribution"]):
                candidates[neighbor_id] = {
                    "candidate_id": neighbor_id,
                    "priority_level": 1,
                    "adjacent_contribution": score,
                    "direct_contribution": weighted_contributions.get(neighbor_id, 0.0),
                    "support_contribution": 0.0,
                    "seed_variable_id": variable_id,
                }

    first_wave = [candidate_id for candidate_id, row in candidates.items() if row["priority_level"] == 1]
    for candidate_id in first_wave:
        for neighbor_id, _ in incident_neighbors(graph, candidate_id):
            if neighbor_id not in candidate_ids or neighbor_id in candidates:
                continue
            candidates[neighbor_id] = {
                "candidate_id": neighbor_id,
                "priority_level": 2,
                "adjacent_contribution": 0.7 * float(candidates[candidate_id]["adjacent_contribution"]),
                "direct_contribution": weighted_contributions.get(neighbor_id, 0.0),
                "support_contribution": 0.0,
                "seed_variable_id": candidates[candidate_id]["seed_variable_id"],
            }

    for candidate_id in sorted(candidate_ids):
        node = graph["nodes"][candidate_id]
        if str(node.get("candidate_role", "")) != "root_cause_anchor":
            continue
        support_contribution, support_variable_id = _downstream_contribution_signal(
            graph,
            candidate_id,
            weighted_contributions,
            max_depth=3,
        )
        previous = candidates.get(candidate_id)
        if previous is None:
            candidates[candidate_id] = {
                "candidate_id": candidate_id,
                "priority_level": 2 if support_contribution > 0 else 3,
                "adjacent_contribution": support_contribution,
                "direct_contribution": weighted_contributions.get(candidate_id, 0.0),
                "support_contribution": support_contribution,
                "seed_variable_id": support_variable_id,
            }
            continue
        previous["support_contribution"] = max(
            float(previous.get("support_contribution", 0.0)),
            support_contribution,
        )
        if support_contribution > float(previous["adjacent_contribution"]):
            previous["adjacent_contribution"] = support_contribution
            if support_variable_id:
                previous["seed_variable_id"] = support_variable_id

    for candidate_id, row in candidates.items():
        support_contribution, support_variable_id = _downstream_contribution_signal(
            graph,
            candidate_id,
            weighted_contributions,
            max_depth=3 if str(graph["nodes"][candidate_id].get("candidate_role", "")) == "root_cause_anchor" else 2,
        )
        row["direct_contribution"] = max(
            float(row.get("direct_contribution", 0.0)),
            weighted_contributions.get(candidate_id, 0.0),
        )
        row["support_contribution"] = max(
            float(row.get("support_contribution", 0.0)),
            support_contribution,
        )
        if not str(row.get("seed_variable_id", "")) and support_variable_id:
            row["seed_variable_id"] = support_variable_id

    if not candidates:
        for candidate_id in candidate_ids:
            candidates[candidate_id] = {
                "candidate_id": candidate_id,
                "priority_level": 3,
                "adjacent_contribution": 0.0,
                "direct_contribution": weighted_contributions.get(candidate_id, 0.0),
                "support_contribution": 0.0,
                "seed_variable_id": "",
            }

    ordered_candidates = []
    for candidate_id, row in candidates.items():
        node = graph["nodes"][candidate_id]
        ordered_candidates.append(
            {
                **row,
                "candidate_name": node.get("name", candidate_id),
                "candidate_type": node.get("entity_type", ""),
                "candidate_role": node.get("candidate_role", ""),
            }
        )
    return sorted(
        ordered_candidates,
        key=lambda row: (
            int(row["priority_level"]),
            -max(float(row.get("adjacent_contribution", 0.0)), float(row.get("support_contribution", 0.0))),
            -float(row.get("direct_contribution", 0.0)),
            str(row["candidate_type"]),
            str(row["candidate_name"]).lower(),
            str(row["candidate_id"]),
        ),
    )


def _candidate_seed_score(candidate: dict[str, object]) -> float:
    direct_contribution = float(candidate.get("direct_contribution", 0.0))
    adjacent_contribution = float(candidate.get("adjacent_contribution", 0.0))
    support_contribution = float(candidate.get("support_contribution", 0.0))
    seed_floor = 0.18 if str(candidate.get("candidate_role", "")) == "root_cause_anchor" else 0.12
    seed_score = max(seed_floor, direct_contribution, adjacent_contribution, 0.9 * support_contribution)
    return round(min(0.35, seed_score), 6)


def _top_variable_payload(
    scores: dict[str, float],
    contributions: dict[str, float],
    graph: dict[str, object],
    limit: int = 5,
) -> list[dict[str, object]]:
    rows = []
    for entity_id, score in sorted(scores.items(), key=lambda item: (-item[1], item[0])):
        if score <= 0:
            continue
        node = graph["nodes"].get(entity_id, {})
        rows.append(
            {
                "entity_id": entity_id,
                "name": node.get("name", entity_id),
                "propagated_score": round(score, 8),
                "rbc_contribution": round(contributions.get(entity_id, 0.0), 8),
            }
        )
        if len(rows) >= limit:
            break
    return rows


def _pattern_entropy(scores: dict[str, float]) -> tuple[int, float]:
    positive_scores = [float(value) for value in scores.values() if float(value) > 1e-9]
    if not positive_scores:
        return 0, 0.0
    total = sum(positive_scores)
    entropy = 0.0
    for value in positive_scores:
        probability = value / total
        entropy -= probability * math.log(max(probability, 1e-12))
    return len(positive_scores), entropy


def ranking_score(
    *,
    root_score: float,
    covered_contribution_mass: float,
    pattern_entropy: float,
    candidate_type: str,
    candidate_role: str,
    discriminator_alignment: float = 0.0,
    ranking_adjustment: float = 0.0,
) -> float:
    coverage_penalty = ROOT_SCORE_COVERAGE_PENALTY
    entropy_penalty = ROOT_SCORE_ENTROPY_PENALTY
    role = str(candidate_role)
    if role == "root_cause_anchor":
        coverage_penalty *= 0.75
        entropy_penalty *= 0.50
    elif role == "actuator":
        coverage_penalty *= 1.10
        entropy_penalty *= 1.15
    return (
        float(root_score)
        - (coverage_penalty * float(covered_contribution_mass))
        - (entropy_penalty * float(pattern_entropy))
        + CANDIDATE_TYPE_RANKING_BIAS.get(str(candidate_type), 0.0)
        + CANDIDATE_ROLE_RANKING_BIAS.get(role, 0.0)
        + (ROOT_CAUSE_DISCRIMINATOR_WEIGHT * float(discriminator_alignment))
        + float(ranking_adjustment)
    )


def _anchor_discriminator_alignment(
    candidate_id: str,
    candidate_role: str,
    weighted_contributions: dict[str, float],
    anchor_discriminators: dict[str, dict[str, object]] | None,
) -> float:
    if str(candidate_role) != "root_cause_anchor" or not anchor_discriminators:
        return 0.0
    discriminator_row = anchor_discriminators.get(candidate_id)
    if not discriminator_row:
        return 0.0
    variable_ids = [
        str(variable_id)
        for variable_id in discriminator_row.get("diagnostic_variable_ids", [])
    ]
    if not variable_ids:
        return 0.0
    denominator = sum(
        value
        for _, value in sorted(
            weighted_contributions.items(),
            key=lambda item: (-item[1], item[0]),
        )[:8]
        if float(value) > 0
    )
    if denominator <= 0:
        return 0.0
    matched_mass = sum(float(weighted_contributions.get(entity_id, 0.0)) for entity_id in variable_ids)
    return round(min(1.0, matched_mass / denominator), 8)


def _ranking_sort_key(row: dict[str, object]) -> tuple[float, float, int, str, str]:
    return (
        -float(row.get("ranking_score", 0.0)),
        -float(row.get("root_score", 0.0)),
        int(row.get("priority_level", 999)),
        str(row.get("candidate_type", "")),
        str(row.get("candidate_id", "")),
    )


def _bounded_excess_ratio(value: float, threshold: float, scale: float) -> float:
    if scale <= 0:
        return 0.0
    return round(
        min(1.0, max(0.0, (float(value) - float(threshold)) / float(scale))),
        8,
    )


def _bounded_abs_excess_ratio(value: float, threshold: float, scale: float) -> float:
    if scale <= 0:
        return 0.0
    return round(
        min(1.0, max(0.0, (abs(float(value)) - float(threshold)) / float(scale))),
        8,
    )


def _bounded_negative_ratio(value: float, threshold: float, scale: float) -> float:
    if scale <= 0:
        return 0.0
    return round(
        min(1.0, max(0.0, (float(threshold) - float(value)) / float(scale))),
        8,
    )


def _bounded_band_ratio(value: float, lower_bound: float, upper_bound: float) -> float:
    lower = float(lower_bound)
    upper = float(upper_bound)
    current = float(value)
    if lower >= upper or current < lower or current > upper:
        return 0.0
    midpoint = (lower + upper) / 2.0
    radius = max(1e-6, (upper - lower) / 2.0)
    return round(max(0.0, 1.0 - (abs(current - midpoint) / radius)), 8)


def _separator_family_context(
    weighted_contributions: dict[str, float],
    anchor_discriminators: dict[str, dict[str, object]] | None,
) -> dict[str, object] | None:
    if not anchor_discriminators:
        return None

    diagnostic_variables_by_anchor: dict[str, set[str]] = {}
    family_union_ids: set[str] = set()
    for anchor_id in SEPARATOR_FAMILY_ANCHOR_IDS:
        discriminator_row = anchor_discriminators.get(anchor_id)
        if discriminator_row is None:
            return None
        variable_ids = {
            str(variable_id)
            for variable_id in discriminator_row.get("diagnostic_variable_ids", [])
            if str(variable_id)
        }
        if not variable_ids:
            return None
        diagnostic_variables_by_anchor[anchor_id] = variable_ids
        family_union_ids.update(variable_ids)

    denominator = sum(
        value
        for value in sorted(
            (float(value) for value in weighted_contributions.values() if float(value) > 0),
            reverse=True,
        )[:8]
    )
    if denominator <= 0:
        return None

    family_activation = sum(
        float(weighted_contributions.get(variable_id, 0.0))
        for variable_id in family_union_ids
    ) / denominator

    diagnostic_mass_by_anchor: dict[str, float] = {}
    unique_mass_by_anchor: dict[str, float] = {}
    for anchor_id, variable_ids in diagnostic_variables_by_anchor.items():
        diagnostic_mass_by_anchor[anchor_id] = sum(
            float(weighted_contributions.get(variable_id, 0.0))
            for variable_id in variable_ids
        ) / denominator
        sibling_union_ids = set().union(
            *(
                diagnostic_variables_by_anchor[sibling_id]
                for sibling_id in SEPARATOR_FAMILY_ANCHOR_IDS
                if sibling_id != anchor_id
            )
        )
        unique_mass_by_anchor[anchor_id] = sum(
            float(weighted_contributions.get(variable_id, 0.0))
            for variable_id in (variable_ids - sibling_union_ids)
        ) / denominator

    return {
        "family_activation": round(family_activation, 8),
        "diagnostic_mass_by_anchor": {
            anchor_id: round(value, 8)
            for anchor_id, value in diagnostic_mass_by_anchor.items()
        },
        "unique_mass_by_anchor": {
            anchor_id: round(value, 8)
            for anchor_id, value in unique_mass_by_anchor.items()
        },
    }


def _apply_anchor_preference_adjustments(
    rankings: list[dict[str, object]],
    graph: dict[str, object],
) -> None:
    ranking_by_candidate = {
        str(row["candidate_id"]): row
        for row in rankings
    }
    for row in rankings:
        candidate_role = str(row.get("candidate_role", ""))
        candidate_id = str(row["candidate_id"])
        base_adjustment = float(row.get("ranking_adjustment", 0.0))
        if candidate_role != "root_cause_anchor":
            continue
        proxy_bonus = 0.0
        for target_id in graph["nodes"].get(candidate_id, {}).get("anchor_target_ids", []):
            proxy_row = ranking_by_candidate.get(str(target_id))
            if proxy_row is None:
                continue
            if str(proxy_row.get("candidate_role", "")) == "root_cause_anchor":
                continue
            score_gap = float(proxy_row["base_ranking_score"]) - float(row["base_ranking_score"])
            if score_gap <= ROOT_CAUSE_PROXY_PROMOTION_MARGIN:
                proxy_bonus = max(proxy_bonus, ROOT_CAUSE_PROXY_PROMOTION_BONUS - max(0.0, score_gap))
        if proxy_bonus <= 0:
            continue
        row["ranking_adjustment"] = round(base_adjustment + proxy_bonus, 8)
        row["ranking_score"] = round(float(row["base_ranking_score"]) + float(row["ranking_adjustment"]), 8)


def _apply_separator_family_adjustments(
    rankings: list[dict[str, object]],
    weighted_contributions: dict[str, float],
    anchor_discriminators: dict[str, dict[str, object]] | None,
) -> None:
    context = _separator_family_context(weighted_contributions, anchor_discriminators)
    if context is None:
        return

    ordered_rows = sorted(rankings, key=_ranking_sort_key)
    family_rows = [
        row
        for row in ordered_rows
        if str(row.get("candidate_id", "")) in SEPARATOR_FAMILY_ANCHOR_IDS
    ]
    if not family_rows:
        return

    top_family_row = family_rows[0]
    competitive_rank = ordered_rows.index(top_family_row) + 1
    competition_gap = max(
        0.0,
        float(ordered_rows[0].get("ranking_score", 0.0)) - float(top_family_row.get("ranking_score", 0.0)),
    )
    family_activation = float(context["family_activation"])
    triggered = (
        family_activation >= SEPARATOR_FAMILY_ACTIVATION_THRESHOLD
        and competitive_rank <= SEPARATOR_FAMILY_MAX_COMPETITIVE_RANK
        and competition_gap <= SEPARATOR_FAMILY_MAX_SCORE_GAP
    )

    diagnostic_mass_by_anchor = dict(context["diagnostic_mass_by_anchor"])
    unique_mass_by_anchor = dict(context["unique_mass_by_anchor"])
    for row in rankings:
        candidate_id = str(row.get("candidate_id", ""))
        if candidate_id not in diagnostic_mass_by_anchor:
            continue
        row["family_id"] = SEPARATOR_FAMILY_ID
        row["family_activation"] = round(family_activation, 8)
        row["family_competitive_rank"] = competitive_rank
        row["family_competition_gap"] = round(competition_gap, 8)
        row["family_diagnostic_mass"] = round(float(diagnostic_mass_by_anchor[candidate_id]), 8)
        row["family_unique_mass"] = round(float(unique_mass_by_anchor[candidate_id]), 8)
        row["family_evidence_bonus"] = 0.0
        if not triggered:
            continue
        family_bonus = (
            SEPARATOR_FAMILY_SHARED_ALIGNMENT_WEIGHT
            * family_activation
            * float(diagnostic_mass_by_anchor[candidate_id])
            + SEPARATOR_FAMILY_UNIQUE_ALIGNMENT_WEIGHT * float(unique_mass_by_anchor[candidate_id])
        )
        if family_bonus <= 0:
            continue
        row["ranking_adjustment"] = round(float(row.get("ranking_adjustment", 0.0)) + family_bonus, 8)
        row["family_evidence_bonus"] = round(family_bonus, 8)
        row["ranking_score"] = round(float(row["base_ranking_score"]) + float(row["ranking_adjustment"]), 8)


def _condenser_dynamic_signature(
    dynamic_feature_vector: dict[str, float],
) -> float:
    coolant_outlet_std = float(dynamic_feature_vector.get(CONDENSER_DYNAMIC_STD_FEATURE_ID, 0.0))
    coolant_outlet_mean = float(dynamic_feature_vector.get(CONDENSER_DYNAMIC_MEAN_FEATURE_ID, 0.0))
    separator_temp_std = float(
        dynamic_feature_vector.get(CONDENSER_DYNAMIC_SEPARATOR_TEMP_STD_FEATURE_ID, 0.0)
    )
    std_signal = _bounded_excess_ratio(
        coolant_outlet_std,
        CONDENSER_DYNAMIC_STD_THRESHOLD,
        CONDENSER_DYNAMIC_STD_SCALE,
    )
    mean_signal = _bounded_negative_ratio(
        coolant_outlet_mean,
        CONDENSER_DYNAMIC_MEAN_THRESHOLD,
        CONDENSER_DYNAMIC_MEAN_SCALE,
    )
    separator_temp_signal = _bounded_excess_ratio(
        separator_temp_std,
        CONDENSER_DYNAMIC_SEPARATOR_TEMP_STD_THRESHOLD,
        CONDENSER_DYNAMIC_SEPARATOR_TEMP_STD_SCALE,
    )
    if std_signal <= 0 or mean_signal <= 0:
        return 0.0
    signature = (
        CONDENSER_DYNAMIC_STD_WEIGHT * std_signal
        + CONDENSER_DYNAMIC_MEAN_WEIGHT * mean_signal
        + CONDENSER_DYNAMIC_SEPARATOR_TEMP_STD_WEIGHT * separator_temp_signal
    )
    return round(min(1.0, signature), 8)


def _apply_condenser_dynamic_adjustments(
    rankings: list[dict[str, object]],
    dynamic_feature_vector: dict[str, float],
) -> None:
    ordered_rows = sorted(rankings, key=_ranking_sort_key)
    condenser_row = next(
        (
            row
            for row in ordered_rows
            if str(row.get("candidate_id", "")) == CONDENSER_DYNAMIC_TARGET_ID
        ),
        None,
    )
    if condenser_row is None:
        return

    condenser_rank = ordered_rows.index(condenser_row) + 1
    competition_gap = max(
        0.0,
        float(ordered_rows[0].get("ranking_score", 0.0)) - float(condenser_row.get("ranking_score", 0.0)),
    )
    family_activation = float(condenser_row.get("family_activation", 0.0))
    signature = _condenser_dynamic_signature(dynamic_feature_vector)

    condenser_row["condenser_dynamic_signature"] = round(signature, 8)
    condenser_row["condenser_dynamic_bonus"] = 0.0
    condenser_row["condenser_dynamic_competitive_rank"] = condenser_rank
    condenser_row["condenser_dynamic_competition_gap"] = round(competition_gap, 8)

    if (
        signature <= 0
        or family_activation < SEPARATOR_FAMILY_ACTIVATION_THRESHOLD
        or condenser_rank > CONDENSER_DYNAMIC_MAX_COMPETITIVE_RANK
        or competition_gap > CONDENSER_DYNAMIC_MAX_SCORE_GAP
    ):
        return

    bonus = CONDENSER_DYNAMIC_MAX_BONUS * signature * family_activation
    if bonus <= 0:
        return
    condenser_row["ranking_adjustment"] = round(float(condenser_row.get("ranking_adjustment", 0.0)) + bonus, 8)
    condenser_row["condenser_dynamic_bonus"] = round(bonus, 8)
    condenser_row["ranking_score"] = round(
        float(condenser_row["base_ranking_score"]) + float(condenser_row["ranking_adjustment"]),
        8,
    )


def _stream4_cold_response_signature(
    dynamic_feature_vector: dict[str, float],
) -> float:
    stripper_temp_mean = float(
        dynamic_feature_vector.get(STREAM4_COLD_RESPONSE_STRIPPER_TEMP_MEAN_FEATURE_ID, 0.0)
    )
    steam_flow_mean = float(
        dynamic_feature_vector.get(STREAM4_COLD_RESPONSE_STEAM_FLOW_MEAN_FEATURE_ID, 0.0)
    )
    steam_flow_std = float(
        dynamic_feature_vector.get(STREAM4_COLD_RESPONSE_STEAM_FLOW_STD_FEATURE_ID, 0.0)
    )
    stripper_temp_signal = _bounded_negative_ratio(
        stripper_temp_mean,
        STREAM4_COLD_RESPONSE_STRIPPER_TEMP_MEAN_THRESHOLD,
        STREAM4_COLD_RESPONSE_STRIPPER_TEMP_MEAN_SCALE,
    )
    steam_flow_signal = _bounded_excess_ratio(
        steam_flow_mean,
        STREAM4_COLD_RESPONSE_STEAM_FLOW_MEAN_THRESHOLD,
        STREAM4_COLD_RESPONSE_STEAM_FLOW_MEAN_SCALE,
    )
    steam_flow_std_signal = _bounded_band_ratio(
        steam_flow_std,
        STREAM4_COLD_RESPONSE_STEAM_FLOW_STD_MIN,
        STREAM4_COLD_RESPONSE_STEAM_FLOW_STD_MAX,
    )
    if stripper_temp_signal <= 0 or steam_flow_signal <= 0 or steam_flow_std_signal <= 0:
        return 0.0
    signature = (
        STREAM4_COLD_RESPONSE_STRIPPER_TEMP_WEIGHT * stripper_temp_signal
        + STREAM4_COLD_RESPONSE_STEAM_FLOW_WEIGHT * steam_flow_signal
        + STREAM4_COLD_RESPONSE_STEAM_FLOW_STD_WEIGHT * steam_flow_std_signal
    )
    return round(min(1.0, signature), 8)


def _apply_stream4_cold_response_adjustments(
    rankings: list[dict[str, object]],
    dynamic_feature_vector: dict[str, float],
) -> None:
    ordered_rows = sorted(rankings, key=_ranking_sort_key)
    ranking_by_candidate = {
        str(row.get("candidate_id", "")): row
        for row in ordered_rows
    }
    stream4_row = ranking_by_candidate.get(STREAM4_COLD_RESPONSE_TARGET_ID)
    rival_row = ranking_by_candidate.get(STREAM4_COLD_RESPONSE_RIVAL_ID)
    if stream4_row is None or rival_row is None or not ordered_rows:
        return

    stream4_rank = ordered_rows.index(stream4_row) + 1
    competition_gap = max(
        0.0,
        float(ordered_rows[0].get("ranking_score", 0.0)) - float(stream4_row.get("ranking_score", 0.0)),
    )
    signature = _stream4_cold_response_signature(dynamic_feature_vector)

    stream4_row["stream4_cold_response_signature"] = round(signature, 8)
    stream4_row["stream4_cold_response_bonus"] = 0.0
    stream4_row["stream4_cold_response_competitive_rank"] = stream4_rank
    stream4_row["stream4_cold_response_competition_gap"] = round(competition_gap, 8)

    if (
        signature <= 0
        or stream4_rank > STREAM4_COLD_RESPONSE_MAX_COMPETITIVE_RANK
        or str(ordered_rows[0].get("candidate_id", "")) != STREAM4_COLD_RESPONSE_RIVAL_ID
        or competition_gap > STREAM4_COLD_RESPONSE_MAX_SCORE_GAP
    ):
        return

    bonus = STREAM4_COLD_RESPONSE_MAX_BONUS * signature
    if bonus <= 0:
        return
    stream4_row["ranking_adjustment"] = round(float(stream4_row.get("ranking_adjustment", 0.0)) + bonus, 8)
    stream4_row["stream4_cold_response_bonus"] = round(bonus, 8)
    stream4_row["ranking_score"] = round(
        float(stream4_row["base_ranking_score"]) + float(stream4_row["ranking_adjustment"]),
        8,
    )


def _apply_stream4_proxy_chase_adjustments(
    rankings: list[dict[str, object]],
) -> None:
    ordered_rows = sorted(rankings, key=_ranking_sort_key)
    if not ordered_rows:
        return

    ranking_by_candidate = {
        str(row.get("candidate_id", "")): row
        for row in ordered_rows
    }
    stream4_row = ranking_by_candidate.get(STREAM4_PROXY_CHASE_TARGET_ID)
    if stream4_row is None:
        return

    stream4_rank = ordered_rows.index(stream4_row) + 1
    top_row = ordered_rows[0]
    competition_gap = max(
        0.0,
        float(top_row.get("ranking_score", 0.0)) - float(stream4_row.get("ranking_score", 0.0)),
    )
    memory_gap = max(
        0.0,
        float(top_row.get("anchor_memory_bonus", 0.0)) - float(stream4_row.get("anchor_memory_bonus", 0.0)),
    )
    unique_alignment = float(stream4_row.get("anchor_unique_contribution_alignment", 0.0))
    discriminator_alignment = float(stream4_row.get("discriminator_alignment", 0.0))
    rival_discriminator_alignment = float(top_row.get("discriminator_alignment", 0.0))

    stream4_row["stream4_proxy_chase_bonus"] = 0.0
    stream4_row["stream4_proxy_chase_competition_gap"] = round(competition_gap, 8)
    stream4_row["stream4_proxy_chase_memory_gap"] = round(memory_gap, 8)
    stream4_row["stream4_proxy_chase_unique_alignment"] = round(unique_alignment, 8)

    if (
        stream4_rank > STREAM4_PROXY_CHASE_MAX_COMPETITIVE_RANK
        or str(top_row.get("candidate_id", "")) not in STREAM4_PROXY_CHASE_RIVAL_IDS
        or competition_gap > STREAM4_PROXY_CHASE_MAX_SCORE_GAP
        or float(stream4_row.get("stream4_cold_response_signature", 0.0)) > 0.0
        or unique_alignment < STREAM4_PROXY_CHASE_MIN_UNIQUE_ALIGNMENT
        or discriminator_alignment < STREAM4_PROXY_CHASE_MIN_DISCRIMINATOR_ALIGNMENT
        or rival_discriminator_alignment > STREAM4_PROXY_CHASE_MAX_RIVAL_DISCRIMINATOR_ALIGNMENT
        or memory_gap > STREAM4_PROXY_CHASE_MAX_MEMORY_GAP
    ):
        return

    bonus = min(
        STREAM4_PROXY_CHASE_MAX_BONUS,
        competition_gap + STREAM4_PROXY_CHASE_WIN_MARGIN,
    )
    if bonus <= 0:
        return
    stream4_row["ranking_adjustment"] = round(float(stream4_row.get("ranking_adjustment", 0.0)) + bonus, 8)
    stream4_row["stream4_proxy_chase_bonus"] = round(bonus, 8)
    stream4_row["ranking_score"] = round(
        float(stream4_row["base_ranking_score"]) + float(stream4_row["ranking_adjustment"]),
        8,
    )


def _stream2_competition_signature(
    dynamic_feature_vector: dict[str, float],
) -> tuple[float, float, float]:
    reactor_cooling_mean = float(
        dynamic_feature_vector.get(STREAM2_COMPETITION_REACTOR_COOLING_MEAN_FEATURE_ID, 0.0)
    )
    offgas_b_mean = float(
        dynamic_feature_vector.get(STREAM2_COMPETITION_OFFGAS_B_MEAN_FEATURE_ID, 0.0)
    )
    reactor_cooling_signal = _bounded_abs_excess_ratio(
        reactor_cooling_mean,
        STREAM2_COMPETITION_REACTOR_COOLING_ABS_THRESHOLD,
        STREAM2_COMPETITION_REACTOR_COOLING_ABS_SCALE,
    )
    offgas_b_signal = _bounded_excess_ratio(
        offgas_b_mean,
        STREAM2_COMPETITION_OFFGAS_B_MEAN_THRESHOLD,
        STREAM2_COMPETITION_OFFGAS_B_MEAN_SCALE,
    )
    signature = max(reactor_cooling_signal, offgas_b_signal)
    return (
        round(signature, 8),
        round(reactor_cooling_signal, 8),
        round(offgas_b_signal, 8),
    )


def _apply_stream2_competition_adjustments(
    rankings: list[dict[str, object]],
    dynamic_feature_vector: dict[str, float],
) -> None:
    ordered_rows = sorted(rankings, key=_ranking_sort_key)
    ranking_by_candidate = {
        str(row.get("candidate_id", "")): row
        for row in ordered_rows
    }
    stream2_row = ranking_by_candidate.get(STREAM2_COMPETITION_TARGET_ID)
    rival_row = ranking_by_candidate.get(STREAM2_COMPETITION_RIVAL_ID)
    condenser_row = ranking_by_candidate.get(STREAM2_COMPETITION_EXTENDED_RIVAL_ID)
    if stream2_row is None or rival_row is None or not ordered_rows:
        return

    stream2_rank = ordered_rows.index(stream2_row) + 1
    competition_gap = max(
        0.0,
        float(ordered_rows[0].get("ranking_score", 0.0)) - float(stream2_row.get("ranking_score", 0.0)),
    )
    top_pair_gap = (
        max(
            0.0,
            float(ordered_rows[0].get("ranking_score", 0.0))
            - float(ordered_rows[1].get("ranking_score", 0.0)),
        )
        if len(ordered_rows) > 1
        else 0.0
    )
    family_activation = max(
        float(rival_row.get("family_activation", 0.0)),
        float(condenser_row.get("family_activation", 0.0)) if condenser_row is not None else 0.0,
    )
    signature, reactor_cooling_signal, offgas_b_signal = _stream2_competition_signature(
        dynamic_feature_vector
    )

    stream2_row["stream2_competition_signature"] = round(signature, 8)
    stream2_row["stream2_competition_bonus"] = 0.0
    stream2_row["stream2_competition_competitive_rank"] = stream2_rank
    stream2_row["stream2_competition_competition_gap"] = round(competition_gap, 8)
    stream2_row["stream2_competition_top_pair_gap"] = round(top_pair_gap, 8)
    stream2_row["stream2_competition_family_activation"] = round(family_activation, 8)
    stream2_row["stream2_competition_mode"] = ""
    stream2_row["stream2_competition_reactor_cooling_signal"] = round(reactor_cooling_signal, 8)
    stream2_row["stream2_competition_offgas_b_signal"] = round(offgas_b_signal, 8)

    standard_trigger = (
        signature > 0
        and stream2_rank <= STREAM2_COMPETITION_MAX_COMPETITIVE_RANK
        and str(ordered_rows[0].get("candidate_id", "")) == STREAM2_COMPETITION_RIVAL_ID
        and competition_gap <= STREAM2_COMPETITION_MAX_SCORE_GAP
    )
    extended_trigger = (
        signature >= STREAM2_COMPETITION_EXTENDED_MIN_SIGNATURE
        and stream2_rank <= STREAM2_COMPETITION_EXTENDED_MAX_COMPETITIVE_RANK
        and condenser_row is not None
        and str(ordered_rows[0].get("candidate_id", "")) == STREAM2_COMPETITION_EXTENDED_RIVAL_ID
        and len(ordered_rows) > 1
        and str(ordered_rows[1].get("candidate_id", "")) == STREAM2_COMPETITION_RIVAL_ID
        and competition_gap <= STREAM2_COMPETITION_EXTENDED_MAX_SCORE_GAP
        and top_pair_gap <= STREAM2_COMPETITION_EXTENDED_MAX_TOP_PAIR_GAP
        and family_activation >= STREAM2_COMPETITION_EXTENDED_FAMILY_ACTIVATION_THRESHOLD
        and float(condenser_row.get("condenser_dynamic_signature", 0.0)) <= 0.0
    )
    if not standard_trigger and not extended_trigger:
        return

    bonus = STREAM2_COMPETITION_MAX_BONUS * signature
    if bonus <= 0:
        return
    stream2_row["ranking_adjustment"] = round(float(stream2_row.get("ranking_adjustment", 0.0)) + bonus, 8)
    stream2_row["stream2_competition_bonus"] = round(bonus, 8)
    stream2_row["stream2_competition_mode"] = (
        "separator_rival"
        if standard_trigger
        else "condenser_separator_pair"
    )
    stream2_row["ranking_score"] = round(
        float(stream2_row["base_ranking_score"]) + float(stream2_row["ranking_adjustment"]),
        8,
    )


def _apply_separator_valve_tiebreak_adjustments(
    rankings: list[dict[str, object]],
) -> None:
    ordered_rows = sorted(rankings, key=_ranking_sort_key)
    if len(ordered_rows) < 2:
        return

    ranking_by_candidate = {
        str(row.get("candidate_id", "")): row
        for row in ordered_rows
    }
    separator_row = ranking_by_candidate.get(SEPARATOR_VALVE_TIEBREAK_TARGET_ID)
    condenser_row = ranking_by_candidate.get(SEPARATOR_VALVE_TIEBREAK_RIVAL_ID)
    stream2_row = ranking_by_candidate.get(STREAM2_COMPETITION_TARGET_ID)
    if separator_row is None or condenser_row is None:
        return

    competition_gap = max(
        0.0,
        float(condenser_row.get("ranking_score", 0.0)) - float(separator_row.get("ranking_score", 0.0)),
    )
    family_activation = max(
        float(separator_row.get("family_activation", 0.0)),
        float(condenser_row.get("family_activation", 0.0)),
    )
    stream2_signature = float(stream2_row.get("stream2_competition_signature", 0.0)) if stream2_row else 0.0
    memory_advantage = float(separator_row.get("anchor_memory_bonus", 0.0)) - float(
        condenser_row.get("anchor_memory_bonus", 0.0)
    )

    separator_row["separator_valve_tiebreak_bonus"] = 0.0
    separator_row["separator_valve_tiebreak_competition_gap"] = round(competition_gap, 8)
    separator_row["separator_valve_tiebreak_memory_advantage"] = round(memory_advantage, 8)

    if (
        str(ordered_rows[0].get("candidate_id", "")) != SEPARATOR_VALVE_TIEBREAK_RIVAL_ID
        or str(ordered_rows[1].get("candidate_id", "")) != SEPARATOR_VALVE_TIEBREAK_TARGET_ID
        or competition_gap > SEPARATOR_VALVE_TIEBREAK_MAX_SCORE_GAP
        or family_activation < SEPARATOR_VALVE_TIEBREAK_FAMILY_ACTIVATION_THRESHOLD
        or float(condenser_row.get("condenser_dynamic_signature", 0.0)) > 0.0
        or stream2_signature > SEPARATOR_VALVE_TIEBREAK_MAX_STREAM2_SIGNATURE
        or memory_advantage < SEPARATOR_VALVE_TIEBREAK_MIN_MEMORY_ADVANTAGE
    ):
        return

    bonus = min(
        SEPARATOR_VALVE_TIEBREAK_MAX_BONUS,
        competition_gap + SEPARATOR_VALVE_TIEBREAK_WIN_MARGIN,
    )
    if bonus <= 0:
        return
    separator_row["ranking_adjustment"] = round(float(separator_row.get("ranking_adjustment", 0.0)) + bonus, 8)
    separator_row["separator_valve_tiebreak_bonus"] = round(bonus, 8)
    separator_row["ranking_score"] = round(
        float(separator_row["base_ranking_score"]) + float(separator_row["ranking_adjustment"]),
        8,
    )


def _apply_stripper_tiebreak_adjustments(
    rankings: list[dict[str, object]],
) -> None:
    ordered_rows = sorted(rankings, key=_ranking_sort_key)
    if len(ordered_rows) < 2:
        return

    top_row = ordered_rows[0]
    runner_up = ordered_rows[1]
    if (
        str(top_row.get("candidate_id", "")) != STRIPPER_TIEBREAK_RIVAL_ID
        or str(runner_up.get("candidate_id", "")) != STRIPPER_TIEBREAK_TARGET_ID
    ):
        return

    competition_gap = max(
        0.0,
        float(top_row.get("ranking_score", 0.0)) - float(runner_up.get("ranking_score", 0.0)),
    )
    memory_advantage = float(runner_up.get("anchor_memory_bonus", 0.0)) - float(
        top_row.get("anchor_memory_bonus", 0.0)
    )
    unique_advantage = float(runner_up.get("anchor_unique_contribution_alignment", 0.0)) - float(
        top_row.get("anchor_unique_contribution_alignment", 0.0)
    )

    runner_up["stripper_tiebreak_bonus"] = 0.0
    runner_up["stripper_tiebreak_competition_gap"] = round(competition_gap, 8)
    runner_up["stripper_tiebreak_memory_advantage"] = round(memory_advantage, 8)
    runner_up["stripper_tiebreak_unique_advantage"] = round(unique_advantage, 8)

    if (
        competition_gap > STRIPPER_TIEBREAK_MAX_SCORE_GAP
        or float(top_row.get("stream4_cold_response_signature", 0.0)) > 0.0
        or float(top_row.get("stream4_variance_signature", 0.0)) > 0.0
        or memory_advantage < STRIPPER_TIEBREAK_MIN_MEMORY_ADVANTAGE
        or unique_advantage < STRIPPER_TIEBREAK_MIN_UNIQUE_ADVANTAGE
    ):
        return

    bonus = min(
        STRIPPER_TIEBREAK_MAX_BONUS,
        competition_gap + STRIPPER_TIEBREAK_WIN_MARGIN,
    )
    if bonus <= 0:
        return
    runner_up["ranking_adjustment"] = round(float(runner_up.get("ranking_adjustment", 0.0)) + bonus, 8)
    runner_up["stripper_tiebreak_bonus"] = round(bonus, 8)
    runner_up["ranking_score"] = round(
        float(runner_up["base_ranking_score"]) + float(runner_up["ranking_adjustment"]),
        8,
    )


def _stream4_variance_signature(
    dynamic_feature_vector: dict[str, float],
) -> tuple[float, float, float]:
    stripper_temp_std = float(
        dynamic_feature_vector.get(STREAM4_VARIANCE_STRIPPER_TEMP_STD_FEATURE_ID, 0.0)
    )
    steam_flow_std = float(
        dynamic_feature_vector.get(STREAM4_VARIANCE_STEAM_FLOW_STD_FEATURE_ID, 0.0)
    )
    stripper_temp_signal = _bounded_excess_ratio(
        stripper_temp_std,
        STREAM4_VARIANCE_STRIPPER_TEMP_STD_THRESHOLD,
        STREAM4_VARIANCE_STRIPPER_TEMP_STD_SCALE,
    )
    margin_signal = _bounded_excess_ratio(
        stripper_temp_std - steam_flow_std,
        STREAM4_VARIANCE_TEMP_STEAM_MARGIN_THRESHOLD,
        STREAM4_VARIANCE_TEMP_STEAM_MARGIN_SCALE,
    )
    if stripper_temp_signal <= 0.0 or margin_signal <= 0.0:
        return 0.0, round(stripper_temp_signal, 8), round(margin_signal, 8)
    signature = (
        0.55 * stripper_temp_signal
        + 0.45 * margin_signal
    )
    return (
        round(min(1.0, signature), 8),
        round(stripper_temp_signal, 8),
        round(margin_signal, 8),
    )


def _apply_stream4_variance_adjustments(
    rankings: list[dict[str, object]],
    dynamic_feature_vector: dict[str, float],
) -> None:
    ordered_rows = sorted(rankings, key=_ranking_sort_key)
    if not ordered_rows:
        return

    ranking_by_candidate = {
        str(row.get("candidate_id", "")): row
        for row in ordered_rows
    }
    stream4_row = ranking_by_candidate.get(STREAM4_VARIANCE_TARGET_ID)
    if stream4_row is None:
        return

    stream4_rank = ordered_rows.index(stream4_row) + 1
    top_row = ordered_rows[0]
    competition_gap = max(
        0.0,
        float(top_row.get("ranking_score", 0.0)) - float(stream4_row.get("ranking_score", 0.0)),
    )
    signature, stripper_temp_signal, margin_signal = _stream4_variance_signature(dynamic_feature_vector)

    stream4_row["stream4_variance_signature"] = round(signature, 8)
    stream4_row["stream4_variance_bonus"] = 0.0
    stream4_row["stream4_variance_competitive_rank"] = int(stream4_rank)
    stream4_row["stream4_variance_competition_gap"] = round(competition_gap, 8)
    stream4_row["stream4_variance_stripper_temp_signal"] = round(stripper_temp_signal, 8)
    stream4_row["stream4_variance_margin_signal"] = round(margin_signal, 8)

    if (
        signature <= 0.0
        or stream4_rank > STREAM4_VARIANCE_MAX_COMPETITIVE_RANK
        or str(top_row.get("candidate_id", "")) not in STREAM4_VARIANCE_RIVAL_IDS
        or competition_gap > STREAM4_VARIANCE_MAX_SCORE_GAP
        or float(stream4_row.get("stream4_cold_response_signature", 0.0)) > 0.0
    ):
        return

    bonus = min(
        STREAM4_VARIANCE_MAX_BONUS,
        competition_gap + STREAM4_VARIANCE_WIN_MARGIN,
    )
    if bonus <= 0.0:
        return
    stream4_row["ranking_adjustment"] = round(float(stream4_row.get("ranking_adjustment", 0.0)) + bonus, 8)
    stream4_row["stream4_variance_bonus"] = round(bonus, 8)
    stream4_row["ranking_score"] = round(
        float(stream4_row["base_ranking_score"]) + float(stream4_row["ranking_adjustment"]),
        8,
    )


def _stripper_thermal_signature(
    dynamic_feature_vector: dict[str, float],
) -> tuple[float, float, float]:
    steam_flow_std = float(
        dynamic_feature_vector.get(STRIPPER_THERMAL_STEAM_FLOW_STD_FEATURE_ID, 0.0)
    )
    stripper_temp_std = float(
        dynamic_feature_vector.get(STRIPPER_THERMAL_STRIPPER_TEMP_STD_FEATURE_ID, 0.0)
    )
    steam_flow_signal = _bounded_excess_ratio(
        steam_flow_std,
        STRIPPER_THERMAL_STEAM_FLOW_STD_THRESHOLD,
        STRIPPER_THERMAL_STEAM_FLOW_STD_SCALE,
    )
    margin_signal = _bounded_excess_ratio(
        steam_flow_std - stripper_temp_std,
        STRIPPER_THERMAL_STEAM_TEMP_MARGIN_THRESHOLD,
        STRIPPER_THERMAL_STEAM_TEMP_MARGIN_SCALE,
    )
    if steam_flow_signal <= 0.0 or margin_signal <= 0.0:
        return 0.0, round(steam_flow_signal, 8), round(margin_signal, 8)
    signature = (
        0.60 * steam_flow_signal
        + 0.40 * margin_signal
    )
    return (
        round(min(1.0, signature), 8),
        round(steam_flow_signal, 8),
        round(margin_signal, 8),
    )


def _apply_stripper_thermal_adjustments(
    rankings: list[dict[str, object]],
    dynamic_feature_vector: dict[str, float],
) -> None:
    ordered_rows = sorted(rankings, key=_ranking_sort_key)
    if not ordered_rows:
        return

    ranking_by_candidate = {
        str(row.get("candidate_id", "")): row
        for row in ordered_rows
    }
    stripper_row = ranking_by_candidate.get(STRIPPER_THERMAL_TARGET_ID)
    if stripper_row is None:
        return

    stripper_rank = ordered_rows.index(stripper_row) + 1
    top_row = ordered_rows[0]
    competition_gap = max(
        0.0,
        float(top_row.get("ranking_score", 0.0)) - float(stripper_row.get("ranking_score", 0.0)),
    )
    signature, steam_flow_signal, margin_signal = _stripper_thermal_signature(dynamic_feature_vector)

    stripper_row["stripper_thermal_signature"] = round(signature, 8)
    stripper_row["stripper_thermal_bonus"] = 0.0
    stripper_row["stripper_thermal_competitive_rank"] = int(stripper_rank)
    stripper_row["stripper_thermal_competition_gap"] = round(competition_gap, 8)
    stripper_row["stripper_thermal_steam_flow_signal"] = round(steam_flow_signal, 8)
    stripper_row["stripper_thermal_margin_signal"] = round(margin_signal, 8)

    if (
        signature <= 0.0
        or stripper_rank > STRIPPER_THERMAL_MAX_COMPETITIVE_RANK
        or str(top_row.get("candidate_id", "")) not in STRIPPER_THERMAL_RIVAL_IDS
        or competition_gap > STRIPPER_THERMAL_MAX_SCORE_GAP
        or float(top_row.get("stream4_cold_response_signature", 0.0)) > 0.0
        or float(top_row.get("stream4_variance_signature", 0.0)) > 0.0
    ):
        return

    bonus = min(
        STRIPPER_THERMAL_MAX_BONUS,
        competition_gap + STRIPPER_THERMAL_WIN_MARGIN,
    )
    if bonus <= 0.0:
        return
    stripper_row["ranking_adjustment"] = round(float(stripper_row.get("ranking_adjustment", 0.0)) + bonus, 8)
    stripper_row["stripper_thermal_bonus"] = round(bonus, 8)
    stripper_row["ranking_score"] = round(
        float(stripper_row["base_ranking_score"]) + float(stripper_row["ranking_adjustment"]),
        8,
    )


def _condenser_moderate_signature(
    dynamic_feature_vector: dict[str, float],
) -> tuple[float, float, float, float]:
    coolant_outlet_std = float(dynamic_feature_vector.get(CONDENSER_MODERATE_STD_FEATURE_ID, 0.0))
    coolant_outlet_mean = float(dynamic_feature_vector.get(CONDENSER_MODERATE_MEAN_FEATURE_ID, 0.0))
    separator_temp_std = float(
        dynamic_feature_vector.get(CONDENSER_MODERATE_SEPARATOR_TEMP_STD_FEATURE_ID, 0.0)
    )
    std_signal = _bounded_excess_ratio(
        coolant_outlet_std,
        CONDENSER_MODERATE_STD_THRESHOLD,
        CONDENSER_MODERATE_STD_SCALE,
    )
    mean_signal = _bounded_negative_ratio(
        coolant_outlet_mean,
        CONDENSER_MODERATE_MEAN_THRESHOLD,
        CONDENSER_MODERATE_MEAN_SCALE,
    )
    separator_temp_signal = _bounded_excess_ratio(
        separator_temp_std,
        CONDENSER_MODERATE_SEPARATOR_TEMP_STD_THRESHOLD,
        CONDENSER_MODERATE_SEPARATOR_TEMP_STD_SCALE,
    )
    if std_signal <= 0.0 or mean_signal <= 0.0:
        return (
            0.0,
            round(std_signal, 8),
            round(mean_signal, 8),
            round(separator_temp_signal, 8),
        )
    signature = (
        0.50 * std_signal
        + 0.35 * mean_signal
        + 0.15 * separator_temp_signal
    )
    return (
        round(min(1.0, signature), 8),
        round(std_signal, 8),
        round(mean_signal, 8),
        round(separator_temp_signal, 8),
    )


def _apply_condenser_moderate_adjustments(
    rankings: list[dict[str, object]],
    dynamic_feature_vector: dict[str, float],
) -> None:
    ordered_rows = sorted(rankings, key=_ranking_sort_key)
    if not ordered_rows:
        return

    ranking_by_candidate = {
        str(row.get("candidate_id", "")): row
        for row in ordered_rows
    }
    condenser_row = ranking_by_candidate.get(CONDENSER_MODERATE_TARGET_ID)
    if condenser_row is None:
        return

    condenser_rank = ordered_rows.index(condenser_row) + 1
    top_row = ordered_rows[0]
    competition_gap = max(
        0.0,
        float(top_row.get("ranking_score", 0.0)) - float(condenser_row.get("ranking_score", 0.0)),
    )
    signature, std_signal, mean_signal, separator_temp_signal = _condenser_moderate_signature(
        dynamic_feature_vector
    )

    condenser_row["condenser_moderate_signature"] = round(signature, 8)
    condenser_row["condenser_moderate_bonus"] = 0.0
    condenser_row["condenser_moderate_competitive_rank"] = int(condenser_rank)
    condenser_row["condenser_moderate_competition_gap"] = round(competition_gap, 8)
    condenser_row["condenser_moderate_std_signal"] = round(std_signal, 8)
    condenser_row["condenser_moderate_mean_signal"] = round(mean_signal, 8)
    condenser_row["condenser_moderate_separator_temp_signal"] = round(separator_temp_signal, 8)

    if (
        signature <= 0.0
        or condenser_rank > CONDENSER_MODERATE_MAX_COMPETITIVE_RANK
        or str(top_row.get("candidate_id", "")) not in CONDENSER_MODERATE_RIVAL_IDS
        or competition_gap > CONDENSER_MODERATE_MAX_SCORE_GAP
        or float(condenser_row.get("condenser_dynamic_signature", 0.0)) > 0.0
    ):
        return

    bonus = min(
        CONDENSER_MODERATE_MAX_BONUS,
        competition_gap + CONDENSER_MODERATE_WIN_MARGIN,
    )
    if bonus <= 0.0:
        return
    condenser_row["ranking_adjustment"] = round(float(condenser_row.get("ranking_adjustment", 0.0)) + bonus, 8)
    condenser_row["condenser_moderate_bonus"] = round(bonus, 8)
    condenser_row["ranking_score"] = round(
        float(condenser_row["base_ranking_score"]) + float(condenser_row["ranking_adjustment"]),
        8,
    )


def _separator_warm_signature(
    dynamic_feature_vector: dict[str, float],
) -> tuple[float, float, float, float, float]:
    coolant_std = float(dynamic_feature_vector.get(SEPARATOR_WARM_COOLANT_STD_FEATURE_ID, 0.0))
    separator_temp_std = float(
        dynamic_feature_vector.get(SEPARATOR_WARM_SEPARATOR_TEMP_STD_FEATURE_ID, 0.0)
    )
    coolant_mean = float(dynamic_feature_vector.get(SEPARATOR_WARM_COOLANT_MEAN_FEATURE_ID, 0.0))
    positive_drift = max(
        float(dynamic_feature_vector.get(SEPARATOR_WARM_STRIPPER_TEMP_MEAN_FEATURE_ID, 0.0)),
        float(dynamic_feature_vector.get(SEPARATOR_WARM_STEAM_FLOW_MEAN_FEATURE_ID, 0.0)),
        float(dynamic_feature_vector.get(SEPARATOR_WARM_STEAM_MV_MEAN_FEATURE_ID, 0.0)),
    )
    coolant_std_signal = _bounded_excess_ratio(
        coolant_std,
        SEPARATOR_WARM_COOLANT_STD_THRESHOLD,
        SEPARATOR_WARM_COOLANT_STD_SCALE,
    )
    separator_temp_std_signal = _bounded_excess_ratio(
        separator_temp_std,
        SEPARATOR_WARM_SEPARATOR_TEMP_STD_THRESHOLD,
        SEPARATOR_WARM_SEPARATOR_TEMP_STD_SCALE,
    )
    coolant_mean_signal = _bounded_excess_ratio(
        coolant_mean,
        SEPARATOR_WARM_COOLANT_MEAN_THRESHOLD,
        SEPARATOR_WARM_COOLANT_MEAN_SCALE,
    )
    positive_drift_signal = _bounded_excess_ratio(
        positive_drift,
        SEPARATOR_WARM_POSITIVE_DRIFT_THRESHOLD,
        SEPARATOR_WARM_POSITIVE_DRIFT_SCALE,
    )
    if (
        coolant_std_signal <= 0.0
        or separator_temp_std_signal <= 0.0
        or coolant_mean_signal <= 0.0
        or positive_drift_signal <= 0.0
    ):
        return (
            0.0,
            round(coolant_std_signal, 8),
            round(separator_temp_std_signal, 8),
            round(coolant_mean_signal, 8),
            round(positive_drift_signal, 8),
        )
    signature = (
        0.35 * coolant_std_signal
        + 0.25 * separator_temp_std_signal
        + 0.20 * coolant_mean_signal
        + 0.20 * positive_drift_signal
    )
    return (
        round(min(1.0, signature), 8),
        round(coolant_std_signal, 8),
        round(separator_temp_std_signal, 8),
        round(coolant_mean_signal, 8),
        round(positive_drift_signal, 8),
    )


def _apply_separator_warm_adjustments(
    rankings: list[dict[str, object]],
    dynamic_feature_vector: dict[str, float],
) -> None:
    ordered_rows = sorted(rankings, key=_ranking_sort_key)
    if len(ordered_rows) < 2:
        return

    top_row = ordered_rows[0]
    runner_up = ordered_rows[1]
    if (
        str(top_row.get("candidate_id", "")) != SEPARATOR_WARM_RIVAL_ID
        or str(runner_up.get("candidate_id", "")) != SEPARATOR_WARM_TARGET_ID
    ):
        return

    competition_gap = max(
        0.0,
        float(top_row.get("ranking_score", 0.0)) - float(runner_up.get("ranking_score", 0.0)),
    )
    signature, coolant_std_signal, separator_temp_std_signal, coolant_mean_signal, positive_drift_signal = (
        _separator_warm_signature(dynamic_feature_vector)
    )

    runner_up["separator_warm_signature"] = round(signature, 8)
    runner_up["separator_warm_bonus"] = 0.0
    runner_up["separator_warm_competition_gap"] = round(competition_gap, 8)
    runner_up["separator_warm_coolant_std_signal"] = round(coolant_std_signal, 8)
    runner_up["separator_warm_separator_temp_std_signal"] = round(separator_temp_std_signal, 8)
    runner_up["separator_warm_coolant_mean_signal"] = round(coolant_mean_signal, 8)
    runner_up["separator_warm_positive_drift_signal"] = round(positive_drift_signal, 8)

    if (
        signature <= 0.0
        or competition_gap > SEPARATOR_WARM_MAX_SCORE_GAP
        or float(top_row.get("stream2_competition_signature", 0.0)) > 0.0
        or float(runner_up.get("condenser_dynamic_signature", 0.0)) > 0.0
        or float(runner_up.get("condenser_moderate_signature", 0.0)) > 0.0
    ):
        return

    bonus = min(
        SEPARATOR_WARM_MAX_BONUS,
        competition_gap + SEPARATOR_WARM_WIN_MARGIN,
    )
    if bonus <= 0.0:
        return
    runner_up["ranking_adjustment"] = round(float(runner_up.get("ranking_adjustment", 0.0)) + bonus, 8)
    runner_up["separator_warm_bonus"] = round(bonus, 8)
    runner_up["ranking_score"] = round(
        float(runner_up["base_ranking_score"]) + float(runner_up["ranking_adjustment"]),
        8,
    )


def _support_payload(
    candidate_id: str,
    top_variables: list[dict[str, object]],
    simulation: dict[str, object],
    graph: dict[str, object],
) -> tuple[list[list[str]], set[str], dict[str, int]]:
    edges_by_id = graph["edges"]
    support_paths: list[list[str]] = []
    support_evidence_ids: set[str] = set()
    support_path_count: dict[str, int] = {}
    for row in top_variables[:3]:
        path_edge_ids = trace_path(
            candidate_id,
            str(row["entity_id"]),
            simulation["best_parent_edge"],
            edges_by_id,
        )
        if not path_edge_ids:
            continue
        node_path = [candidate_id]
        for edge_id in path_edge_ids:
            edge = edges_by_id[edge_id]
            node_path.append(str(edge["tail_id"]))
            support_path_count[edge_id] = support_path_count.get(edge_id, 0) + 1
            support_evidence_ids.update(str(item) for item in edge.get("provenance_ids", []))
        support_paths.append(node_path)
    return support_paths, support_evidence_ids, support_path_count


def rank_scenario(
    graph: dict[str, object],
    scenario: dict[str, object],
    ordered_variables: list[str],
    *,
    anchor_discriminators: dict[str, dict[str, object]] | None = None,
    scenario_dynamic_features: dict[str, dict[str, object]] | None = None,
    anchor_memory_profiles: dict[str, dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    contributions = {
        str(entity_id): float(value)
        for entity_id, value in scenario["graph_contributions"].items()
    }
    weighted_contributions = _weighted_contributions(contributions, graph)
    contribution_vector = [weighted_contributions.get(entity_id, 0.0) for entity_id in ordered_variables]
    scenario_dynamic_row = (scenario_dynamic_features or {}).get(str(scenario["scenario_id"]), {})
    dynamic_feature_vector = {
        str(feature_id): float(value)
        for feature_id, value in dict(scenario_dynamic_row.get("features", {})).items()
    }
    candidates = enumerate_candidates(graph, scenario)
    rankings = []

    for candidate in candidates:
        simulation = simulate_propagation(
            graph,
            str(candidate["candidate_id"]),
            seed_score=_candidate_seed_score(candidate),
        )
        variable_scores = {
            entity_id: float(simulation["node_scores"].get(entity_id, 0.0))
            for entity_id in ordered_variables
        }
        weighted_variable_scores = {
            entity_id: float(variable_scores[entity_id]) * _contribution_weight(entity_id, graph)
            for entity_id in ordered_variables
        }
        score_vector = [weighted_variable_scores[entity_id] for entity_id in ordered_variables]
        root_score = cosine_similarity(score_vector, contribution_vector)
        active_variable_count, pattern_entropy = _pattern_entropy(weighted_variable_scores)
        max_variable_score = max(score_vector) if score_vector else 0.0
        coverage_threshold = max(1e-6, 0.10 * max_variable_score)
        covered_mass = sum(
            weighted_contributions.get(entity_id, 0.0)
            for entity_id, score in weighted_variable_scores.items()
            if score >= coverage_threshold
        )
        discriminator_alignment = _anchor_discriminator_alignment(
            str(candidate["candidate_id"]),
            str(candidate.get("candidate_role", "")),
            weighted_contributions,
            anchor_discriminators,
        )
        structural_ranking_score = ranking_score(
            root_score=root_score,
            covered_contribution_mass=covered_mass,
            pattern_entropy=pattern_entropy,
            candidate_type=str(candidate["candidate_type"]),
            candidate_role=str(candidate.get("candidate_role", "")),
            discriminator_alignment=discriminator_alignment,
        )
        anchor_memory_metrics = anchor_memory_alignment_details(
            str(candidate["candidate_id"]),
            str(candidate.get("candidate_role", "")),
            weighted_contributions,
            dynamic_feature_vector,
            anchor_memory_profiles,
        )
        anchor_contribution_alignment = float(anchor_memory_metrics["contribution_alignment"])
        anchor_dynamic_alignment = float(anchor_memory_metrics["dynamic_alignment"])
        anchor_unique_contribution_alignment = float(
            anchor_memory_metrics["unique_contribution_alignment"]
        )
        anchor_unique_signature_bonus = float(anchor_memory_metrics["unique_signature_bonus"])
        anchor_memory_bonus = float(anchor_memory_metrics["bonus"])
        anchor_memory_scenario_count = int(anchor_memory_metrics["scenario_count"])
        candidate_ranking_score = structural_ranking_score + anchor_memory_bonus
        top_affected_variables = _top_variable_payload(variable_scores, contributions, graph)
        top_support_paths, support_evidence_ids, support_path_count = _support_payload(
            str(candidate["candidate_id"]),
            top_affected_variables,
            simulation,
            graph,
        )
        rankings.append(
            {
                "scenario_id": scenario["scenario_id"],
                "fault_number": scenario["fault_number"],
                "simulation_run": scenario["simulation_run"],
                "candidate_id": candidate["candidate_id"],
                "candidate_name": candidate["candidate_name"],
                "candidate_type": candidate["candidate_type"],
                "candidate_role": candidate.get("candidate_role", ""),
                "priority_level": candidate["priority_level"],
                "seed_variable_id": candidate["seed_variable_id"],
                "seed_score": _candidate_seed_score(candidate),
                "root_score": round(root_score, 8),
                "ranking_score": round(candidate_ranking_score, 8),
                "base_ranking_score": round(candidate_ranking_score, 8),
                "structural_ranking_score": round(structural_ranking_score, 8),
                "discriminator_alignment": round(discriminator_alignment, 8),
                "anchor_contribution_alignment": round(anchor_contribution_alignment, 8),
                "anchor_dynamic_alignment": round(anchor_dynamic_alignment, 8),
                "anchor_unique_contribution_alignment": round(anchor_unique_contribution_alignment, 8),
                "anchor_unique_signature_bonus": round(anchor_unique_signature_bonus, 8),
                "anchor_memory_bonus": round(anchor_memory_bonus, 8),
                "anchor_memory_scenario_count": int(anchor_memory_scenario_count),
                "ranking_adjustment": 0.0,
                "covered_contribution_mass": round(covered_mass, 8),
                "active_variable_count": active_variable_count,
                "pattern_entropy": round(pattern_entropy, 8),
                "family_id": "",
                "family_activation": 0.0,
                "family_competitive_rank": 0,
                "family_competition_gap": 0.0,
                "family_diagnostic_mass": 0.0,
                "family_unique_mass": 0.0,
                "family_evidence_bonus": 0.0,
                "condenser_dynamic_signature": 0.0,
                "condenser_dynamic_bonus": 0.0,
                "condenser_dynamic_competitive_rank": 0,
                "condenser_dynamic_competition_gap": 0.0,
                "stream4_cold_response_signature": 0.0,
                "stream4_cold_response_bonus": 0.0,
                "stream4_cold_response_competitive_rank": 0,
                "stream4_cold_response_competition_gap": 0.0,
                "stream4_proxy_chase_bonus": 0.0,
                "stream4_proxy_chase_competition_gap": 0.0,
                "stream4_proxy_chase_memory_gap": 0.0,
                "stream4_proxy_chase_unique_alignment": 0.0,
                "stream4_variance_signature": 0.0,
                "stream4_variance_bonus": 0.0,
                "stream4_variance_competitive_rank": 0,
                "stream4_variance_competition_gap": 0.0,
                "stream4_variance_stripper_temp_signal": 0.0,
                "stream4_variance_margin_signal": 0.0,
                "stream2_competition_signature": 0.0,
                "stream2_competition_bonus": 0.0,
                "stream2_competition_competitive_rank": 0,
                "stream2_competition_competition_gap": 0.0,
                "stream2_competition_top_pair_gap": 0.0,
                "stream2_competition_family_activation": 0.0,
                "stream2_competition_mode": "",
                "stream2_competition_reactor_cooling_signal": 0.0,
                "stream2_competition_offgas_b_signal": 0.0,
                "separator_valve_tiebreak_bonus": 0.0,
                "separator_valve_tiebreak_competition_gap": 0.0,
                "separator_valve_tiebreak_memory_advantage": 0.0,
                "stripper_tiebreak_bonus": 0.0,
                "stripper_tiebreak_competition_gap": 0.0,
                "stripper_tiebreak_memory_advantage": 0.0,
                "stripper_tiebreak_unique_advantage": 0.0,
                "stripper_thermal_signature": 0.0,
                "stripper_thermal_bonus": 0.0,
                "stripper_thermal_competitive_rank": 0,
                "stripper_thermal_competition_gap": 0.0,
                "stripper_thermal_steam_flow_signal": 0.0,
                "stripper_thermal_margin_signal": 0.0,
                "condenser_moderate_signature": 0.0,
                "condenser_moderate_bonus": 0.0,
                "condenser_moderate_competitive_rank": 0,
                "condenser_moderate_competition_gap": 0.0,
                "condenser_moderate_std_signal": 0.0,
                "condenser_moderate_mean_signal": 0.0,
                "condenser_moderate_separator_temp_signal": 0.0,
                "separator_warm_signature": 0.0,
                "separator_warm_bonus": 0.0,
                "separator_warm_competition_gap": 0.0,
                "separator_warm_coolant_std_signal": 0.0,
                "separator_warm_separator_temp_std_signal": 0.0,
                "separator_warm_coolant_mean_signal": 0.0,
                "separator_warm_positive_drift_signal": 0.0,
                "top_support_paths": top_support_paths,
                "top_affected_variables": top_affected_variables,
                "support_evidence_ids": sorted(support_evidence_ids),
                "_edge_flow": simulation["edge_flow"],
                "_node_scores": simulation["node_scores"],
                "_support_path_count": support_path_count,
            }
        )

    _apply_anchor_preference_adjustments(rankings, graph)
    _apply_separator_family_adjustments(rankings, weighted_contributions, anchor_discriminators)
    _apply_condenser_dynamic_adjustments(rankings, dynamic_feature_vector)
    _apply_stream4_cold_response_adjustments(rankings, dynamic_feature_vector)
    _apply_stream4_proxy_chase_adjustments(rankings)
    _apply_stream2_competition_adjustments(rankings, dynamic_feature_vector)
    _apply_separator_valve_tiebreak_adjustments(rankings)
    _apply_stripper_tiebreak_adjustments(rankings)
    _apply_condenser_moderate_adjustments(rankings, dynamic_feature_vector)
    _apply_separator_warm_adjustments(rankings, dynamic_feature_vector)
    rankings.sort(
        key=lambda row: (
            *_ranking_sort_key(row),
            -float(row["covered_contribution_mass"]),
        )
    )
    for rank, row in enumerate(rankings, start=1):
        row["rank"] = rank
        row["ranking_id"] = stable_id(
            "root_kgd_rank",
            [row["scenario_id"], row["candidate_id"], rank],
        )
    return rankings


def build_topk_subgraphs(
    graph: dict[str, object],
    rankings: list[dict[str, object]],
    scenarios: dict[str, dict[str, object]],
    *,
    top_k: int = DEFAULT_TOP_K,
) -> list[dict[str, object]]:
    by_scenario: dict[str, list[dict[str, object]]] = {}
    for row in rankings:
        by_scenario.setdefault(str(row["scenario_id"]), []).append(row)

    payloads = []
    for scenario_id, rows in sorted(by_scenario.items()):
        scenario = scenarios[scenario_id]
        contributions = {
            str(entity_id): float(value)
            for entity_id, value in scenario["graph_contributions"].items()
        }
        candidate_payloads = []
        for row in rows[:top_k]:
            node_ids = {str(row["candidate_id"])}
            edge_ids: set[str] = set()
            for path in row["top_support_paths"]:
                node_ids.update(path)
            for edge_id in row["_edge_flow"]:
                if float(row["_edge_flow"][edge_id]) > 0:
                    edge_ids.add(edge_id)
            edge_ids = {
                edge_id
                for edge_id in edge_ids
                if row["_support_path_count"].get(edge_id, 0) > 0
            }
            for affected in row["top_affected_variables"]:
                node_ids.add(str(affected["entity_id"]))

            nodes = []
            for node_id in sorted(node_ids):
                node = graph["nodes"][node_id]
                propagated_score = float(row["_node_scores"].get(node_id, 0.0))
                rbc_contribution = contributions.get(node_id, 0.0)
                nodes.append(
                    {
                        "node_id": node_id,
                        "name": node.get("name", node_id),
                        "node_type": node.get("entity_type", ""),
                        "root_score_contribution": round(
                            min(rbc_contribution, propagated_score)
                            if node.get("entity_type") == "Variable"
                            else propagated_score * float(row["root_score"]),
                            8,
                        ),
                        "rbc_contribution": round(rbc_contribution, 8),
                        "propagated_score": round(propagated_score, 8),
                        "evidence_count": len(node.get("provenance_ids", [])),
                    }
                )
            edges = []
            for edge_id in sorted(edge_ids):
                edge = graph["edges"][edge_id]
                edges.append(
                    {
                        "edge_id": edge_id,
                        "head_id": edge["head_id"],
                        "tail_id": edge["tail_id"],
                        "relation_family": edge["relation_family"],
                        "raw_relation_support": list(edge.get("raw_relations", [])),
                        "edge_weight": round(float(edge["edge_weight"]), 8),
                        "propagation_enabled": bool(edge.get("propagation_enabled", False)),
                        "support_path_count": int(row["_support_path_count"].get(edge_id, 0)),
                    }
                )
            candidate_payloads.append(
                {
                    "candidate_id": row["candidate_id"],
                    "candidate_name": row["candidate_name"],
                    "candidate_type": row["candidate_type"],
                    "candidate_role": row.get("candidate_role", ""),
                    "rank": row["rank"],
                    "ranking_score": row["ranking_score"],
                    "structural_ranking_score": row.get("structural_ranking_score", row["ranking_score"]),
                    "root_score": row["root_score"],
                    "discriminator_alignment": row.get("discriminator_alignment", 0.0),
                    "anchor_contribution_alignment": row.get("anchor_contribution_alignment", 0.0),
                    "anchor_dynamic_alignment": row.get("anchor_dynamic_alignment", 0.0),
                    "anchor_unique_contribution_alignment": row.get("anchor_unique_contribution_alignment", 0.0),
                    "anchor_unique_signature_bonus": row.get("anchor_unique_signature_bonus", 0.0),
                    "anchor_memory_bonus": row.get("anchor_memory_bonus", 0.0),
                    "anchor_memory_scenario_count": row.get("anchor_memory_scenario_count", 0),
                    "ranking_adjustment": row.get("ranking_adjustment", 0.0),
                    "covered_contribution_mass": row["covered_contribution_mass"],
                    "family_id": row.get("family_id", ""),
                    "family_activation": row.get("family_activation", 0.0),
                    "family_competitive_rank": row.get("family_competitive_rank", 0),
                    "family_competition_gap": row.get("family_competition_gap", 0.0),
                    "family_diagnostic_mass": row.get("family_diagnostic_mass", 0.0),
                    "family_unique_mass": row.get("family_unique_mass", 0.0),
                    "family_evidence_bonus": row.get("family_evidence_bonus", 0.0),
                    "condenser_dynamic_signature": row.get("condenser_dynamic_signature", 0.0),
                    "condenser_dynamic_bonus": row.get("condenser_dynamic_bonus", 0.0),
                    "condenser_dynamic_competitive_rank": row.get("condenser_dynamic_competitive_rank", 0),
                    "condenser_dynamic_competition_gap": row.get("condenser_dynamic_competition_gap", 0.0),
                    "stream4_cold_response_signature": row.get("stream4_cold_response_signature", 0.0),
                    "stream4_cold_response_bonus": row.get("stream4_cold_response_bonus", 0.0),
                    "stream4_cold_response_competitive_rank": row.get("stream4_cold_response_competitive_rank", 0),
                    "stream4_cold_response_competition_gap": row.get("stream4_cold_response_competition_gap", 0.0),
                    "stream4_proxy_chase_bonus": row.get("stream4_proxy_chase_bonus", 0.0),
                    "stream4_proxy_chase_competition_gap": row.get("stream4_proxy_chase_competition_gap", 0.0),
                    "stream4_proxy_chase_memory_gap": row.get("stream4_proxy_chase_memory_gap", 0.0),
                    "stream4_proxy_chase_unique_alignment": row.get(
                        "stream4_proxy_chase_unique_alignment",
                        0.0,
                    ),
                    "stream4_variance_signature": row.get("stream4_variance_signature", 0.0),
                    "stream4_variance_bonus": row.get("stream4_variance_bonus", 0.0),
                    "stream4_variance_competitive_rank": row.get("stream4_variance_competitive_rank", 0),
                    "stream4_variance_competition_gap": row.get("stream4_variance_competition_gap", 0.0),
                    "stream4_variance_stripper_temp_signal": row.get(
                        "stream4_variance_stripper_temp_signal",
                        0.0,
                    ),
                    "stream4_variance_margin_signal": row.get("stream4_variance_margin_signal", 0.0),
                    "stream2_competition_signature": row.get("stream2_competition_signature", 0.0),
                    "stream2_competition_bonus": row.get("stream2_competition_bonus", 0.0),
                    "stream2_competition_competitive_rank": row.get("stream2_competition_competitive_rank", 0),
                    "stream2_competition_competition_gap": row.get("stream2_competition_competition_gap", 0.0),
                    "stream2_competition_top_pair_gap": row.get("stream2_competition_top_pair_gap", 0.0),
                    "stream2_competition_family_activation": row.get(
                        "stream2_competition_family_activation",
                        0.0,
                    ),
                    "stream2_competition_mode": row.get("stream2_competition_mode", ""),
                    "stream2_competition_reactor_cooling_signal": row.get(
                        "stream2_competition_reactor_cooling_signal",
                        0.0,
                    ),
                    "stream2_competition_offgas_b_signal": row.get(
                        "stream2_competition_offgas_b_signal",
                        0.0,
                    ),
                    "separator_valve_tiebreak_bonus": row.get("separator_valve_tiebreak_bonus", 0.0),
                    "separator_valve_tiebreak_competition_gap": row.get(
                        "separator_valve_tiebreak_competition_gap",
                        0.0,
                    ),
                    "separator_valve_tiebreak_memory_advantage": row.get(
                        "separator_valve_tiebreak_memory_advantage",
                        0.0,
                    ),
                    "stripper_tiebreak_bonus": row.get("stripper_tiebreak_bonus", 0.0),
                    "stripper_tiebreak_competition_gap": row.get("stripper_tiebreak_competition_gap", 0.0),
                    "stripper_tiebreak_memory_advantage": row.get(
                        "stripper_tiebreak_memory_advantage",
                        0.0,
                    ),
                    "stripper_tiebreak_unique_advantage": row.get(
                        "stripper_tiebreak_unique_advantage",
                        0.0,
                    ),
                    "stripper_thermal_signature": row.get("stripper_thermal_signature", 0.0),
                    "stripper_thermal_bonus": row.get("stripper_thermal_bonus", 0.0),
                    "stripper_thermal_competitive_rank": row.get("stripper_thermal_competitive_rank", 0),
                    "stripper_thermal_competition_gap": row.get("stripper_thermal_competition_gap", 0.0),
                    "stripper_thermal_steam_flow_signal": row.get("stripper_thermal_steam_flow_signal", 0.0),
                    "stripper_thermal_margin_signal": row.get("stripper_thermal_margin_signal", 0.0),
                    "condenser_moderate_signature": row.get("condenser_moderate_signature", 0.0),
                    "condenser_moderate_bonus": row.get("condenser_moderate_bonus", 0.0),
                    "condenser_moderate_competitive_rank": row.get("condenser_moderate_competitive_rank", 0),
                    "condenser_moderate_competition_gap": row.get("condenser_moderate_competition_gap", 0.0),
                    "condenser_moderate_std_signal": row.get("condenser_moderate_std_signal", 0.0),
                    "condenser_moderate_mean_signal": row.get("condenser_moderate_mean_signal", 0.0),
                    "condenser_moderate_separator_temp_signal": row.get(
                        "condenser_moderate_separator_temp_signal",
                        0.0,
                    ),
                    "separator_warm_signature": row.get("separator_warm_signature", 0.0),
                    "separator_warm_bonus": row.get("separator_warm_bonus", 0.0),
                    "separator_warm_competition_gap": row.get("separator_warm_competition_gap", 0.0),
                    "separator_warm_coolant_std_signal": row.get("separator_warm_coolant_std_signal", 0.0),
                    "separator_warm_separator_temp_std_signal": row.get(
                        "separator_warm_separator_temp_std_signal",
                        0.0,
                    ),
                    "separator_warm_coolant_mean_signal": row.get("separator_warm_coolant_mean_signal", 0.0),
                    "separator_warm_positive_drift_signal": row.get(
                        "separator_warm_positive_drift_signal",
                        0.0,
                    ),
                    "support_evidence_ids": row["support_evidence_ids"],
                    "nodes": nodes,
                    "edges": edges,
                }
            )

        payloads.append(
            {
                "scenario_id": scenario_id,
                "fault_number": scenario["fault_number"],
                "simulation_run": scenario["simulation_run"],
                "top_candidates": candidate_payloads,
            }
        )
    return payloads


def build_root_kgd(
    project_root: Path,
    *,
    edge_weights: dict[str, float] | None = None,
    relation_params: dict[str, dict[str, float]] | None = None,
    top_k: int = DEFAULT_TOP_K,
) -> dict[str, object]:
    scenarios = _load_rbc_scenarios(project_root)
    ordered_variables = variable_order(project_root)
    anchor_discriminators = load_anchor_discriminators(project_root)
    scenario_dynamic_features = load_scenario_dynamic_features(project_root)
    graph = build_propagation_graph(
        project_root,
        edge_weights=edge_weights,
        relation_params=relation_params or default_relation_params(),
    )
    anchor_memory_profiles = build_anchor_memory_profiles(graph, scenarios, scenario_dynamic_features)
    all_rankings = []
    scenario_lookup = {str(row["scenario_id"]): row for row in scenarios}
    for scenario in scenarios:
        all_rankings.extend(
            rank_scenario(
                graph,
                scenario,
                ordered_variables,
                anchor_discriminators=anchor_discriminators,
                scenario_dynamic_features=scenario_dynamic_features,
                anchor_memory_profiles=anchor_memory_profiles,
            )
        )

    baseline_rows = [
        {
            key: value
            for key, value in row.items()
            if not key.startswith("_")
        }
        for row in all_rankings
    ]
    topk_subgraphs = build_topk_subgraphs(graph, all_rankings, scenario_lookup, top_k=top_k)
    output_dir = project_root / "outputs" / "rca"
    output_dir.mkdir(parents=True, exist_ok=True)

    _write_csv(output_dir / "baseline_root_scores.csv", baseline_rows)
    (output_dir / "baseline_topk_subgraphs.json").write_text(
        json.dumps(topk_subgraphs, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    (output_dir / "anchor_memory_profiles.json").write_text(
        json.dumps(anchor_memory_payload(anchor_memory_profiles), indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    report = {
        "ok": bool(all_rankings),
        "scenario_count": len(scenarios),
        "ranking_count": len(all_rankings),
        "candidate_count_mean": round(len(all_rankings) / max(1, len(scenarios)), 6),
        "mean_top1_ranking_score": round(
            sum(float(row["ranking_score"]) for row in all_rankings if int(row["rank"]) == 1)
            / max(1, len(scenarios)),
            8,
        ),
        "mean_top1_root_score": round(
            sum(float(row["root_score"]) for row in all_rankings if int(row["rank"]) == 1)
            / max(1, len(scenarios)),
            8,
        ),
        "relation_params": relation_params or default_relation_params(),
        "anchor_discriminator_count": len(anchor_discriminators),
        "scenario_dynamic_feature_count": len(scenario_dynamic_features),
        "anchor_memory_profile_count": len(anchor_memory_profiles),
    }
    (output_dir / "root_kgd_baseline_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return report
