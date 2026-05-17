"""Dashboard enrichment helpers for run details."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from kgtracevis.core.result import AnalysisResult
from kgtracevis.schema.evidence_schema import Evidence
from kgtracevis.schema.validators import load_evidence_json
from kgtracevis.service.run_models import RunDetail
from kgtracevis.service.visual_evidence import normalize_visual_evidence_items


def evidence_with_analysis(evidence: Evidence, analysis: AnalysisResult) -> dict[str, Any]:
    """Return an Evidence payload with runtime KG analysis attached."""
    payload = evidence.model_dump(mode="json")
    payload["kg_analysis"] = {
        "linked_entities": analysis.linked_entities,
        "consistency_score": analysis.consistency_score,
        "inconsistent_fields": analysis.inconsistent_fields,
        "correction_candidates": analysis.correction_candidates,
        "top_k_paths": analysis.top_k_paths,
        "ranked_root_causes": [
            item.model_dump(mode="json") for item in analysis.ranked_root_causes
        ],
    }
    return payload


def dashboard_fields_from_analysis(
    evidence: Evidence,
    analysis: AnalysisResult,
) -> dict[str, Any]:
    """Build dashboard fields for a single analyzed Evidence object."""
    linked_entities = [dict(item) for item in analysis.linked_entities]
    top_k_paths = [dict(item) for item in analysis.top_k_paths]
    ranked_root_causes = [
        item.model_dump(mode="json") for item in analysis.ranked_root_causes
    ]
    linked_entities, top_k_paths, ranked_root_causes, _changed = normalize_case_reasoning_payload(
        evidence.model_dump(mode="json"),
        linked_entities=linked_entities,
        top_k_paths=top_k_paths,
        ranked_root_causes=ranked_root_causes,
    )
    source_edges = unique_source_edges(top_k_paths)
    correction_candidates = list(analysis.correction_candidates)
    return {
        "evidence_summary": compact_evidence_summary(evidence),
        "linked_entities": linked_entities,
        "correction_candidates": correction_candidates,
        "top_k_paths": top_k_paths,
        "ranked_root_causes": ranked_root_causes,
        "path_graph": path_graph_from_paths(top_k_paths),
        "source_edge_provenance": source_edges,
        "review_targets": review_targets(
            linked_entities=linked_entities,
            correction_candidates=correction_candidates,
            top_k_paths=top_k_paths,
            ranked_root_causes=ranked_root_causes,
            source_edges=source_edges,
        ),
    }


def enrich_run_detail(detail: RunDetail) -> RunDetail:
    """Backfill derived dashboard fields for older persisted run manifests."""
    changed = False
    path_graph = detail.path_graph
    if not path_graph and detail.top_k_paths:
        path_graph = path_graph_from_paths(detail.top_k_paths)
        changed = True
    targets = detail.review_targets
    if any("target_key" not in target for target in targets):
        targets = [
            {
                **target,
                "target_key": review_target_key(
                    str(target.get("target_type", "target")),
                    target.get("target_id", ""),
                ),
            }
            for target in targets
        ]
        changed = True
    visual_evidence = normalize_visual_evidence_items(detail.visual_evidence)
    if visual_evidence != detail.visual_evidence:
        changed = True
    case_visuals = _visual_evidence_by_case(visual_evidence)
    raw_cases = [dict(case) for case in detail.cases] or _default_case_rows(
        detail,
        case_visuals=case_visuals,
    )
    if not detail.cases and raw_cases:
        changed = True

    cases = []
    for raw_case in raw_cases:
        row, case_changed = _enrich_case_row(raw_case, case_visuals=case_visuals)
        changed = changed or case_changed
        cases.append(row)
    if not changed:
        return detail
    return detail.model_copy(
        update={
            "path_graph": path_graph,
            "review_targets": targets,
            "visual_evidence": visual_evidence,
            "cases": cases,
        }
    )


def enriched_case_rows(
    cases: list[dict[str, Any]],
    *,
    visual_evidence: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Attach graph and review fields to adapter-pipeline case rows."""
    case_visuals = _visual_evidence_by_case(visual_evidence or [])
    enriched: list[dict[str, Any]] = []
    for case in cases:
        row, _changed = _enrich_case_row(dict(case), case_visuals=case_visuals)
        enriched.append(row)
    return enriched


def dashboard_fields_from_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Build aggregate dashboard fields from adapter-pipeline case rows."""
    linked_entities: list[dict[str, Any]] = []
    correction_candidates: list[dict[str, Any]] = []
    top_k_paths: list[dict[str, Any]] = []
    ranked_root_causes: list[dict[str, Any]] = []
    source_edges_by_id: dict[str, dict[str, Any]] = {}
    evidence_summary: dict[str, Any] | None = None

    for case in cases:
        if evidence_summary is None and isinstance(case.get("generated_evidence"), dict):
            evidence_summary = dict(case["generated_evidence"])
        linked_entities.extend(list_of_dicts(case.get("linked_entities")))
        correction_candidates.extend(list_of_dicts(case.get("correction_candidates")))
        top_k_paths.extend(list_of_dicts(case.get("top_k_paths")))
        ranked_root_causes.extend(list_of_dicts(case.get("ranked_root_causes")))
        for edge in list_of_dicts(case.get("source_edge_provenance")):
            edge_id = str(edge.get("edge_id", ""))
            if edge_id:
                source_edges_by_id.setdefault(edge_id, edge)

    source_edges = [source_edges_by_id[edge_id] for edge_id in sorted(source_edges_by_id)]
    return {
        "evidence_summary": evidence_summary,
        "linked_entities": linked_entities,
        "correction_candidates": correction_candidates,
        "top_k_paths": top_k_paths,
        "ranked_root_causes": ranked_root_causes,
        "path_graph": path_graph_from_paths(top_k_paths),
        "source_edge_provenance": source_edges,
        "review_targets": review_targets(
            linked_entities=linked_entities,
            correction_candidates=correction_candidates,
            top_k_paths=top_k_paths,
            ranked_root_causes=ranked_root_causes,
            source_edges=source_edges,
        ),
    }


def resolve_case_generated_evidence(row: Mapping[str, Any]) -> dict[str, Any]:
    """Return the richest available evidence payload for one case row."""
    generated_evidence_full = row.get("generated_evidence_full")
    full_payload = (
        dict(generated_evidence_full)
        if isinstance(generated_evidence_full, Mapping)
        else {}
    )
    if full_payload:
        return full_payload

    evidence_path = row.get("generated_evidence_path") or row.get("evidence_path")
    if isinstance(evidence_path, str) and evidence_path.strip():
        try:
            evidence = load_evidence_json(Path(evidence_path))
            return evidence.model_dump(mode="json")
        except (OSError, ValueError):
            pass

    generated_evidence = row.get("generated_evidence")
    generated = (
        dict(generated_evidence)
        if isinstance(generated_evidence, Mapping)
        else {}
    )
    if generated:
        return generated

    return {}


def normalize_case_reasoning_payload(
    evidence: Mapping[str, Any] | None,
    *,
    linked_entities: list[dict[str, Any]],
    top_k_paths: list[dict[str, Any]],
    ranked_root_causes: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], bool]:
    updated_links = [dict(item) for item in linked_entities]
    updated_paths = [dict(item) for item in top_k_paths]
    updated_candidates = [dict(item) for item in ranked_root_causes]
    changed = False

    observation_values = (
        evidence.get("observations") if isinstance(evidence, Mapping) else None
    )
    observations = [
        dict(item)
        for item in _list_value(observation_values)
        if isinstance(item, Mapping)
    ]
    observation_lookup = {
        (
            _normalize_facet(observation.get("facet")),
            _normalize_text(observation.get("name")),
        ): str(observation.get("obs_id"))
        for observation in observations
        if observation.get("obs_id") is not None
    }

    for link in updated_links:
        if not link.get("facet") and link.get("field"):
            link["facet"] = link.get("field")
            changed = True
        if not link.get("obs_id"):
            key = (
                _normalize_facet(link.get("facet") or link.get("field")),
                _normalize_text(link.get("mention")),
            )
            obs_id = observation_lookup.get(key)
            if obs_id:
                link["obs_id"] = obs_id
                changed = True
        if not link.get("selected_entity_name"):
            selected_entity_id = link.get("selected_entity_id")
            candidates = list_of_dicts(link.get("candidates"))
            selected_name = next(
                (
                    candidate.get("name")
                    for candidate in candidates
                    if candidate.get("entity_id") == selected_entity_id and candidate.get("name")
                ),
                selected_entity_id,
            )
            if selected_name:
                link["selected_entity_name"] = selected_name
                changed = True
        if link.get("ambiguity_margin") is None:
            candidates = list_of_dicts(link.get("candidates"))
            if len(candidates) >= 2:
                first = _to_float(candidates[0].get("score"))
                second = _to_float(candidates[1].get("score"))
                if first is not None and second is not None:
                    link["ambiguity_margin"] = round(first - second, 4)
                    changed = True

    entity_to_obs_ids: dict[str, list[str]] = {}
    for link in updated_links:
        entity_id = link.get("selected_entity_id")
        obs_id = link.get("obs_id")
        if not entity_id or not obs_id:
            continue
        bucket = entity_to_obs_ids.setdefault(str(entity_id), [])
        if str(obs_id) not in bucket:
            bucket.append(str(obs_id))

    path_by_id = {
        str(path.get("path_id")): path
        for path in updated_paths
        if path.get("path_id")
    }
    for path in updated_paths:
        support_obs_ids = _read_obs_id_list(path.get("support_obs_ids"))
        if not support_obs_ids:
            support_obs_ids = _read_obs_id_list(path.get("supporting_evidence"))
        if not support_obs_ids:
            for node_id in _read_string_array(path.get("nodes")):
                support_obs_ids.extend(entity_to_obs_ids.get(node_id, []))
            support_obs_ids = _unique_strings(support_obs_ids)
        if support_obs_ids and support_obs_ids != _read_string_array(path.get("support_obs_ids")):
            path["support_obs_ids"] = support_obs_ids
            changed = True

    for candidate in updated_candidates:
        support_evidence_ids = _read_obs_id_list(candidate.get("support_evidence_ids"))
        if not support_evidence_ids:
            support_evidence_ids = _read_obs_id_list(candidate.get("supporting_evidence"))
        if not support_evidence_ids:
            support_evidence_ids = _candidate_support_obs_ids(
                candidate,
                top_k_paths=updated_paths,
                path_by_id=path_by_id,
            )
        existing_support_ids = _read_string_array(candidate.get("support_evidence_ids"))
        if support_evidence_ids and support_evidence_ids != existing_support_ids:
            candidate["support_evidence_ids"] = support_evidence_ids
            changed = True

    return updated_links, updated_paths, updated_candidates, changed


def _candidate_support_obs_ids(
    candidate: Mapping[str, Any],
    *,
    top_k_paths: list[dict[str, Any]],
    path_by_id: Mapping[str, dict[str, Any]],
) -> list[str]:
    ranking_id = str(candidate.get("ranking_id") or "")
    candidate_id = str(candidate.get("candidate_id") or "")
    path_ids = {
        str(path.get("path_id"))
        for path in list_of_dicts(candidate.get("explanation_paths"))
        if path.get("path_id")
    }
    if ranking_id.startswith("ranking:"):
        path_ids.add(ranking_id.removeprefix("ranking:"))

    support_obs_ids: list[str] = []
    for path_id in sorted(path_ids):
        support_obs_ids.extend(
            _read_obs_id_list(path_by_id.get(path_id, {}).get("support_obs_ids"))
        )

    for path in top_k_paths:
        path_id = str(path.get("path_id") or "")
        matches_candidate = candidate_id and (
            str(path.get("target_entity_id") or "") == candidate_id
            or candidate_id in _read_string_array(path.get("nodes"))
        )
        if path_ids:
            if path_id in path_ids:
                support_obs_ids.extend(_read_obs_id_list(path.get("support_obs_ids")))
            continue
        if matches_candidate:
            support_obs_ids.extend(_read_obs_id_list(path.get("support_obs_ids")))

    return _unique_strings(support_obs_ids)


def _read_obs_id_list(value: Any) -> list[str]:
    ids: list[str] = []
    for item in _list_value(value):
        if isinstance(item, str) and item.startswith("obs"):
            ids.append(item)
        elif isinstance(item, Mapping):
            evidence_id = item.get("evidence_id")
            if isinstance(evidence_id, str) and evidence_id.startswith("obs"):
                ids.append(evidence_id)
    return _unique_strings(ids)


def _read_string_array(value: Any) -> list[str]:
    return [str(item) for item in _list_value(value) if item is not None]


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalize_facet(value: Any) -> str:
    return _normalize_text(value)


def _unique_strings(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def compact_evidence_summary(evidence: Evidence) -> dict[str, Any]:
    """Return compact Evidence fields for dashboard summaries."""
    return {
        "case_id": evidence.case_id,
        "dataset": evidence.dataset,
        "source": evidence.source,
        "object": evidence.object,
        "anomaly_type": evidence.anomaly_type,
        "location": evidence.location,
        "morphology": evidence.morphology,
        "severity": evidence.severity,
        "confidence": evidence.confidence,
        "observation_count": len(evidence.observations),
    }


def unique_source_edges(top_k_paths: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return unique source edges used by ranked paths."""
    edges_by_id: dict[str, dict[str, Any]] = {}
    for path in top_k_paths:
        for edge in list_of_dicts(path.get("source_edges")):
            edge_id = str(edge.get("edge_id", ""))
            if edge_id:
                edges_by_id.setdefault(edge_id, edge)
    return [edges_by_id[edge_id] for edge_id in sorted(edges_by_id)]


def path_graph_from_paths(top_k_paths: list[dict[str, Any]]) -> dict[str, Any]:
    """Build graph-ready path nodes and edges from ranked paths."""
    paths: list[dict[str, Any]] = []
    edge_ids: set[str] = set()
    node_ids: set[str] = set()
    for index, path in enumerate(top_k_paths):
        path_id = str(path.get("path_id") or f"path_{index}")
        nodes = [str(node) for node in path.get("nodes", []) if node is not None]
        node_names = [str(name) for name in path.get("node_names", []) if name is not None]
        relations = [
            str(relation)
            for relation in path.get("relations", [])
            if relation is not None
        ]
        source_edges = list_of_dicts(path.get("source_edges"))
        graph_nodes = []
        for node_index, node_id in enumerate(nodes):
            node_ids.add(node_id)
            graph_nodes.append(
                {
                    "node_id": node_id,
                    "label": node_names[node_index] if node_index < len(node_names) else node_id,
                    "role": _path_node_role(node_index, len(nodes)),
                }
            )
        graph_edges = []
        for edge_index, relation in enumerate(relations):
            edge = source_edges[edge_index] if edge_index < len(source_edges) else {}
            edge_id = str(
                edge.get("edge_id")
                or _fallback_edge_id(nodes, edge_index, relation, path_id)
            )
            edge_ids.add(edge_id)
            graph_edges.append(
                {
                    "edge_id": edge_id,
                    "target_key": review_target_key("edge", edge_id),
                    "source_node_id": nodes[edge_index] if edge_index < len(nodes) else "",
                    "target_node_id": nodes[edge_index + 1] if edge_index + 1 < len(nodes) else "",
                    "relation": relation,
                    "source": edge.get("source"),
                    "evidence": edge.get("evidence"),
                    "confidence": edge.get("confidence"),
                    "review_status": edge.get("review_status"),
                }
            )
        paths.append(
            {
                "path_id": path_id,
                "target_key": review_target_key("path", path_id),
                "source_entity_id": path.get("source_entity_id"),
                "target_entity_id": path.get("target_entity_id"),
                "score": path.get("score"),
                "confidence": path.get("confidence"),
                "supporting_evidence": path.get("support_obs_ids")
                or path.get("supporting_evidence", []),
                "nodes": graph_nodes,
                "edges": graph_edges,
            }
        )
    return {
        "paths": paths,
        "path_count": len(paths),
        "node_count": len(node_ids),
        "edge_count": len(edge_ids),
    }


def review_targets(
    *,
    linked_entities: list[dict[str, Any]],
    correction_candidates: list[dict[str, Any]],
    top_k_paths: list[dict[str, Any]],
    source_edges: list[dict[str, Any]],
    ranked_root_causes: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build review target references for path, edge, link, and correction feedback."""
    targets: list[dict[str, Any]] = []
    for path in top_k_paths:
        path_id = path.get("path_id")
        if path_id:
            targets.append(
                {
                    "target_type": "path",
                    "target_id": str(path_id),
                    "target_key": review_target_key("path", path_id),
                    "label": str(path.get("target_entity_id") or path_id),
                }
            )
    for root_cause in ranked_root_causes or []:
        ranking_id = root_cause.get("ranking_id") or root_cause.get("candidate_id")
        if ranking_id:
            targets.append(
                {
                    "target_type": "root_cause_candidate",
                    "target_id": str(ranking_id),
                    "target_key": review_target_key("root_cause_candidate", ranking_id),
                    "label": str(
                        root_cause.get("candidate_name")
                        or root_cause.get("candidate_id")
                        or ranking_id
                    ),
                }
            )
    for edge in source_edges:
        edge_id = edge.get("edge_id")
        if edge_id:
            targets.append(
                {
                    "target_type": "edge",
                    "target_id": str(edge_id),
                    "target_key": review_target_key("edge", edge_id),
                    "label": str(edge.get("relation") or edge_id),
                }
            )
    for link in linked_entities:
        link_id = link.get("link_id") or link.get("field")
        if link_id:
            targets.append(
                {
                    "target_type": "entity_link",
                    "target_id": str(link_id),
                    "target_key": review_target_key("entity_link", link_id),
                    "label": str(link.get("selected_entity_id") or link_id),
                }
            )
    for candidate in correction_candidates:
        candidate_id = candidate.get("candidate_id")
        if candidate_id:
            targets.append(
                {
                    "target_type": "correction",
                    "target_id": str(candidate_id),
                    "target_key": review_target_key("correction", candidate_id),
                    "label": str(candidate.get("suggested_value") or candidate_id),
                }
            )
    return targets


def review_target_key(target_type: str, target_id: object) -> str:
    """Return the stable review target key."""
    return f"{target_type}:{target_id}"


def list_of_dicts(value: Any) -> list[dict[str, Any]]:
    """Return dict items from a list-like value."""
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _enrich_case_row(
    row: dict[str, Any],
    *,
    case_visuals: Mapping[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any], bool]:
    """Attach stable case-level dashboard fields expected by RootLens clients."""
    changed = False
    evidence = resolve_case_generated_evidence(row)
    if evidence and row.get("generated_evidence") != evidence:
        row["generated_evidence"] = evidence
        changed = True
    case_id = str(
        row.get("case_id")
        or evidence.get("case_id")
        or "unknown"
    )
    if row.get("case_id") != case_id:
        row["case_id"] = case_id
        changed = True

    dataset = row.get("dataset") or evidence.get("dataset")
    if dataset is not None and row.get("dataset") != dataset:
        row["dataset"] = dataset
        changed = True

    source = row.get("source") or evidence.get("source")
    if source is not None and row.get("source") != source:
        row["source"] = source
        changed = True

    display_label = (
        row.get("case_label")
        or evidence.get("case_label")
        or row.get("label")
        or case_id
    )
    if row.get("case_label") != display_label:
        row["case_label"] = display_label
        changed = True
    if row.get("label") != display_label:
        row["label"] = display_label
        changed = True

    top_k_paths = list_of_dicts(row.get("top_k_paths"))
    ranked_root_causes = list_of_dicts(row.get("ranked_root_causes"))
    linked_entities = list_of_dicts(row.get("linked_entities"))
    correction_candidates = list_of_dicts(row.get("correction_candidates"))
    source_edges = list_of_dicts(row.get("source_edge_provenance"))

    linked_entities, top_k_paths, ranked_root_causes, normalized_changed = (
        normalize_case_reasoning_payload(
            evidence,
            linked_entities=linked_entities,
            top_k_paths=top_k_paths,
            ranked_root_causes=ranked_root_causes,
        )
    )
    if normalized_changed:
        row["linked_entities"] = linked_entities
        row["top_k_paths"] = top_k_paths
        row["ranked_root_causes"] = ranked_root_causes
        changed = True

    if not row.get("path_graph") or normalized_changed:
        row["path_graph"] = path_graph_from_paths(top_k_paths)
        changed = True
    if not row.get("review_targets"):
        row["review_targets"] = review_targets(
            linked_entities=linked_entities,
            correction_candidates=correction_candidates,
            top_k_paths=top_k_paths,
            ranked_root_causes=ranked_root_causes,
            source_edges=source_edges,
        )
        changed = True

    visual_items = list_of_dicts(row.get("visual_evidence"))
    if not visual_items:
        if case_id in case_visuals:
            row["visual_evidence"] = [dict(item) for item in case_visuals[case_id]]
            changed = True
    elif case_id in case_visuals:
        expected = case_visuals[case_id]
        if visual_items != expected:
            row["visual_evidence"] = [dict(item) for item in expected]
            changed = True

    return row, changed


def _default_case_rows(
    detail: RunDetail,
    *,
    case_visuals: Mapping[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Synthesize one case row from top-level fields for single-case uploads."""
    evidence = dict(detail.evidence) if isinstance(detail.evidence, Mapping) else {}
    if not evidence:
        return []

    case_summary = (
        dict(detail.evidence_summary)
        if isinstance(detail.evidence_summary, Mapping)
        else {}
    )
    case_id = str(
        evidence.get("case_id")
        or case_summary.get("case_id")
        or "unknown"
    )
    analysis = dict(detail.analysis) if isinstance(detail.analysis, Mapping) else {}
    top_k_paths = list_of_dicts(detail.top_k_paths)
    ranked_root_causes = list_of_dicts(detail.ranked_root_causes)
    linked_entities = list_of_dicts(detail.linked_entities)
    correction_candidates = list_of_dicts(detail.correction_candidates)
    linked_entities, top_k_paths, ranked_root_causes, _changed = normalize_case_reasoning_payload(
        evidence,
        linked_entities=linked_entities,
        top_k_paths=top_k_paths,
        ranked_root_causes=ranked_root_causes,
    )
    source_edges = list_of_dicts(detail.source_edge_provenance)

    return [
        {
            "case_id": case_id,
            "case_label": evidence.get("case_label") or case_summary.get("case_id") or case_id,
            "label": evidence.get("case_label") or case_summary.get("case_id") or case_id,
            "dataset": evidence.get("dataset") or detail.run.dataset,
            "source": evidence.get("source"),
            "generated_evidence": evidence,
            "generated_evidence_path": detail.artifacts.get("input_path"),
            "linked_entities": linked_entities,
            "consistency_score": analysis.get("consistency_score"),
            "inconsistent_fields": _list_value(analysis.get("inconsistent_fields")),
            "correction_candidates": correction_candidates,
            "top_k_paths": top_k_paths,
            "ranked_root_causes": ranked_root_causes,
            "reasoning_metadata": dict(analysis.get("reasoning_metadata") or {}),
            "source_edge_provenance": source_edges,
            "path_graph": detail.path_graph or path_graph_from_paths(top_k_paths),
            "review_targets": detail.review_targets
            or review_targets(
                linked_entities=linked_entities,
                correction_candidates=correction_candidates,
                top_k_paths=top_k_paths,
                ranked_root_causes=ranked_root_causes,
                source_edges=source_edges,
            ),
            "visual_evidence": [dict(item) for item in case_visuals.get(case_id, [])],
        }
    ]


def _visual_evidence_by_case(
    items: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        case_id = str(item.get("case_id") or "").strip()
        if not case_id:
            continue
        grouped.setdefault(case_id, []).append(dict(item))
    return grouped


def _list_value(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    return list(value)


def _path_node_role(node_index: int, node_count: int) -> str:
    if node_index == 0:
        return "source"
    if node_index == node_count - 1:
        return "target"
    return "intermediate"


def _fallback_edge_id(nodes: list[str], edge_index: int, relation: str, path_id: str) -> str:
    head = nodes[edge_index] if edge_index < len(nodes) else path_id
    tail = nodes[edge_index + 1] if edge_index + 1 < len(nodes) else f"step_{edge_index}"
    return f"{head}|{relation}|{tail}|derived"
