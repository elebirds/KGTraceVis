# mypy: ignore-errors
"""Historical anchor signatures learned from prior RCA scenarios."""

# ruff: noqa

from __future__ import annotations

from collections import defaultdict

from kgtracevis.workflows.tep_root_kgd.rca_signal_utils import (
    sparse_cosine_similarity,
    sparse_signature_coverage,
    weighted_contributions,
)


ANCHOR_CONTRIBUTION_ALIGNMENT_WEIGHT = 5.0
ANCHOR_DYNAMIC_ALIGNMENT_WEIGHT = 4.0
ANCHOR_UNIQUE_CONTRIBUTION_ALIGNMENT_WEIGHT = 0.0
ANCHOR_SIMILAR_SIBLING_COUNT = 4
UNIQUE_CONTRIBUTION_MARGIN_MIN = 0.01
TOP_VARIABLE_SIGNATURE_LIMIT = 6
TOP_DYNAMIC_SIGNATURE_LIMIT = 6
TOP_UNIQUE_CONTRIBUTION_LIMIT = 2


def _anchor_id_by_fault(graph: dict[str, object]) -> dict[int, str]:
    mapping: dict[int, str] = {}
    for node_id, node in graph["nodes"].items():
        if str(node.get("entity_type", "")) != "FaultAnchor":
            continue
        for fault_number in node.get("fault_numbers", []):
            mapping[int(fault_number)] = str(node_id)
    return mapping


def _variable_signature(
    graph: dict[str, object],
    centroid: dict[str, float],
) -> list[dict[str, object]]:
    rows = []
    for entity_id, value in sorted(centroid.items(), key=lambda item: (-float(item[1]), item[0])):
        if float(value) <= 1e-9:
            continue
        node = graph["nodes"].get(entity_id, {})
        rows.append(
            {
                "entity_id": entity_id,
                "name": node.get("name", entity_id),
                "weight": round(float(value), 8),
            }
        )
        if len(rows) >= TOP_VARIABLE_SIGNATURE_LIMIT:
            break
    return rows


def _unique_variable_signature(
    graph: dict[str, object],
    centroid: dict[str, float],
    margin_by_entity_id: dict[str, float],
) -> list[dict[str, object]]:
    rows = []
    for entity_id, value in sorted(centroid.items(), key=lambda item: (-float(item[1]), item[0])):
        if float(value) <= 1e-9:
            continue
        node = graph["nodes"].get(entity_id, {})
        rows.append(
            {
                "entity_id": entity_id,
                "name": node.get("name", entity_id),
                "weight": round(float(value), 8),
                "margin": round(float(margin_by_entity_id.get(entity_id, 0.0)), 8),
            }
        )
        if len(rows) >= TOP_UNIQUE_CONTRIBUTION_LIMIT:
            break
    return rows


def _dynamic_signature(centroid: dict[str, float]) -> list[dict[str, object]]:
    rows = []
    for feature_id, value in sorted(centroid.items(), key=lambda item: (-abs(float(item[1])), item[0])):
        if abs(float(value)) <= 1e-9:
            continue
        channel_id, _, statistic = feature_id.partition("__")
        rows.append(
            {
                "feature_id": feature_id,
                "channel_id": channel_id,
                "statistic": statistic,
                "value": round(float(value), 8),
                "magnitude": round(abs(float(value)), 8),
            }
        )
        if len(rows) >= TOP_DYNAMIC_SIGNATURE_LIMIT:
            break
    return rows


def _anchor_similarity_rows(
    anchor_id: str,
    profiles: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    profile = profiles[anchor_id]
    rows = []
    for sibling_id, sibling_profile in profiles.items():
        if sibling_id == anchor_id:
            continue
        contribution_similarity = sparse_cosine_similarity(
            {
                str(entity_id): float(value)
                for entity_id, value in dict(profile.get("contribution_centroid", {})).items()
            },
            {
                str(entity_id): float(value)
                for entity_id, value in dict(sibling_profile.get("contribution_centroid", {})).items()
            },
        )
        dynamic_similarity = sparse_cosine_similarity(
            {
                str(feature_id): float(value)
                for feature_id, value in dict(profile.get("dynamic_centroid", {})).items()
            },
            {
                str(feature_id): float(value)
                for feature_id, value in dict(sibling_profile.get("dynamic_centroid", {})).items()
            },
        )
        combined_similarity = (0.6 * contribution_similarity) + (0.4 * dynamic_similarity)
        rows.append(
            {
                "anchor_id": sibling_id,
                "anchor_name": str(sibling_profile.get("anchor_name", sibling_id)),
                "contribution_similarity": round(contribution_similarity, 8),
                "dynamic_similarity": round(dynamic_similarity, 8),
                "combined_similarity": round(combined_similarity, 8),
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            -float(row["combined_similarity"]),
            -float(row["contribution_similarity"]),
            -float(row["dynamic_similarity"]),
            str(row["anchor_id"]),
        ),
    )


def _unique_contribution_signature_payload(
    anchor_id: str,
    graph: dict[str, object],
    profiles: dict[str, dict[str, object]],
    sibling_anchor_ids: list[str],
) -> tuple[dict[str, float], dict[str, float]]:
    if not sibling_anchor_ids:
        return {}, {}
    anchor_row = graph["nodes"].get(anchor_id, {})
    direct_target_variable_ids = {
        str(target_id)
        for target_id in anchor_row.get("anchor_target_ids", [])
        if str(target_id).startswith("variable:")
    }
    contribution_centroid = {
        str(entity_id): float(value)
        for entity_id, value in dict(profiles[anchor_id].get("contribution_centroid", {})).items()
    }
    candidate_rows: list[tuple[int, float, float, str]] = []
    margin_by_entity_id: dict[str, float] = {}
    for entity_id, value in contribution_centroid.items():
        sibling_max = max(
            float(
                profiles[sibling_id].get("contribution_centroid", {}).get(entity_id, 0.0)
            )
            for sibling_id in sibling_anchor_ids
        )
        margin = float(value) - sibling_max
        if margin < UNIQUE_CONTRIBUTION_MARGIN_MIN:
            continue
        margin_by_entity_id[entity_id] = round(margin, 8)
        candidate_rows.append(
            (
                1 if entity_id in direct_target_variable_ids else 0,
                margin,
                float(value),
                entity_id,
            )
        )
    selected_rows = sorted(
        candidate_rows,
        key=lambda row: (
            -int(row[0]),
            -float(row[1]),
            -float(row[2]),
            str(row[3]),
        ),
    )[:TOP_UNIQUE_CONTRIBUTION_LIMIT]
    selected_centroid = {
        entity_id: round(contribution_centroid[entity_id], 8)
        for _, _, _, entity_id in selected_rows
    }
    selected_margins = {
        entity_id: float(margin_by_entity_id[entity_id])
        for entity_id in selected_centroid
    }
    return selected_centroid, selected_margins


def build_anchor_memory_profiles(
    graph: dict[str, object],
    scenarios: list[dict[str, object]],
    scenario_dynamic_features: dict[str, dict[str, object]] | None,
) -> dict[str, dict[str, object]]:
    anchor_id_by_fault = _anchor_id_by_fault(graph)
    if not anchor_id_by_fault:
        return {}

    contribution_totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    dynamic_totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    scenario_counts: dict[str, int] = defaultdict(int)

    for scenario in scenarios:
        anchor_id = anchor_id_by_fault.get(int(scenario["fault_number"]))
        if not anchor_id:
            continue
        scenario_id = str(scenario["scenario_id"])
        contribution_vector = weighted_contributions(
            {
                str(entity_id): float(value)
                for entity_id, value in dict(scenario["graph_contributions"]).items()
            },
            graph,
        )
        dynamic_row = (scenario_dynamic_features or {}).get(scenario_id, {})
        dynamic_vector = {
            str(feature_id): float(value)
            for feature_id, value in dict(dynamic_row.get("features", {})).items()
        }
        scenario_counts[anchor_id] += 1
        for entity_id, value in contribution_vector.items():
            contribution_totals[anchor_id][entity_id] += float(value)
        for feature_id, value in dynamic_vector.items():
            dynamic_totals[anchor_id][feature_id] += float(value)

    profiles: dict[str, dict[str, object]] = {}
    for anchor_id, scenario_count in sorted(scenario_counts.items()):
        contribution_centroid = {
            entity_id: round(float(value) / scenario_count, 8)
            for entity_id, value in contribution_totals[anchor_id].items()
            if abs(float(value)) > 1e-9
        }
        dynamic_centroid = {
            feature_id: round(float(value) / scenario_count, 8)
            for feature_id, value in dynamic_totals[anchor_id].items()
            if abs(float(value)) > 1e-9
        }
        node = graph["nodes"].get(anchor_id, {})
        profiles[anchor_id] = {
            "anchor_id": anchor_id,
            "anchor_name": str(node.get("name", anchor_id)),
            "scenario_count": scenario_count,
            "fault_numbers": [int(value) for value in node.get("fault_numbers", [])],
            "alignment_weights": {
                "contribution": ANCHOR_CONTRIBUTION_ALIGNMENT_WEIGHT,
                "dynamic": ANCHOR_DYNAMIC_ALIGNMENT_WEIGHT,
            },
            "unique_alignment_weights": {
                "contribution": ANCHOR_UNIQUE_CONTRIBUTION_ALIGNMENT_WEIGHT,
            },
            "contribution_centroid": contribution_centroid,
            "dynamic_centroid": dynamic_centroid,
            "contribution_signature": _variable_signature(graph, contribution_centroid),
            "dynamic_signature": _dynamic_signature(dynamic_centroid),
        }

    for anchor_id in sorted(profiles):
        similarity_rows = _anchor_similarity_rows(anchor_id, profiles)
        sibling_anchor_ids = [
            str(row["anchor_id"])
            for row in similarity_rows[:ANCHOR_SIMILAR_SIBLING_COUNT]
        ]
        unique_contribution_centroid, unique_margin_by_entity_id = _unique_contribution_signature_payload(
            anchor_id,
            graph,
            profiles,
            sibling_anchor_ids,
        )
        profiles[anchor_id]["memory_sibling_anchor_ids"] = sibling_anchor_ids
        profiles[anchor_id]["memory_sibling_similarities"] = similarity_rows[:ANCHOR_SIMILAR_SIBLING_COUNT]
        profiles[anchor_id]["unique_contribution_centroid"] = unique_contribution_centroid
        profiles[anchor_id]["unique_contribution_signature"] = _unique_variable_signature(
            graph,
            unique_contribution_centroid,
            unique_margin_by_entity_id,
        )
    return profiles


def anchor_memory_alignment_details(
    candidate_id: str,
    candidate_role: str,
    weighted_contribution_vector: dict[str, float],
    dynamic_feature_vector: dict[str, float],
    anchor_memory_profiles: dict[str, dict[str, object]] | None,
) -> dict[str, object]:
    if str(candidate_role) != "root_cause_anchor" or not anchor_memory_profiles:
        return {
            "contribution_alignment": 0.0,
            "dynamic_alignment": 0.0,
            "unique_contribution_alignment": 0.0,
            "unique_signature_bonus": 0.0,
            "bonus": 0.0,
            "scenario_count": 0,
        }
    profile = anchor_memory_profiles.get(candidate_id)
    if not profile:
        return {
            "contribution_alignment": 0.0,
            "dynamic_alignment": 0.0,
            "unique_contribution_alignment": 0.0,
            "unique_signature_bonus": 0.0,
            "bonus": 0.0,
            "scenario_count": 0,
        }
    contribution_alignment = sparse_cosine_similarity(
        weighted_contribution_vector,
        {
            str(entity_id): float(value)
            for entity_id, value in dict(profile.get("contribution_centroid", {})).items()
        },
    )
    dynamic_alignment = sparse_cosine_similarity(
        dynamic_feature_vector,
        {
            str(feature_id): float(value)
            for feature_id, value in dict(profile.get("dynamic_centroid", {})).items()
        },
    )
    alignment_weights = dict(profile.get("alignment_weights", {}))
    unique_alignment_weights = dict(profile.get("unique_alignment_weights", {}))
    unique_contribution_alignment = sparse_signature_coverage(
        weighted_contribution_vector,
        {
            str(entity_id): float(value)
            for entity_id, value in dict(profile.get("unique_contribution_centroid", {})).items()
        },
    )
    unique_signature_bonus = (
        float(
            unique_alignment_weights.get(
                "contribution",
                ANCHOR_UNIQUE_CONTRIBUTION_ALIGNMENT_WEIGHT,
            )
        )
        * unique_contribution_alignment
    )
    bonus = (
        float(alignment_weights.get("contribution", ANCHOR_CONTRIBUTION_ALIGNMENT_WEIGHT))
        * contribution_alignment
        + float(alignment_weights.get("dynamic", ANCHOR_DYNAMIC_ALIGNMENT_WEIGHT)) * dynamic_alignment
        + unique_signature_bonus
    )
    return {
        "contribution_alignment": round(contribution_alignment, 8),
        "dynamic_alignment": round(dynamic_alignment, 8),
        "unique_contribution_alignment": round(unique_contribution_alignment, 8),
        "unique_signature_bonus": round(unique_signature_bonus, 8),
        "bonus": round(bonus, 8),
        "scenario_count": int(profile.get("scenario_count", 0)),
    }


def anchor_memory_alignment(
    candidate_id: str,
    candidate_role: str,
    weighted_contribution_vector: dict[str, float],
    dynamic_feature_vector: dict[str, float],
    anchor_memory_profiles: dict[str, dict[str, object]] | None,
) -> tuple[float, float, float, int]:
    details = anchor_memory_alignment_details(
        candidate_id,
        candidate_role,
        weighted_contribution_vector,
        dynamic_feature_vector,
        anchor_memory_profiles,
    )
    return (
        float(details["contribution_alignment"]),
        float(details["dynamic_alignment"]),
        float(details["bonus"]),
        int(details["scenario_count"]),
    )


def anchor_memory_payload(anchor_memory_profiles: dict[str, dict[str, object]]) -> dict[str, object]:
    return {
        "anchor_count": len(anchor_memory_profiles),
        "anchors": [anchor_memory_profiles[key] for key in sorted(anchor_memory_profiles)],
    }
