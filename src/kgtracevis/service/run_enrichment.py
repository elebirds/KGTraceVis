"""Dashboard enrichment helpers for run details."""

from __future__ import annotations

from typing import Any

from kgtracevis.core.result import AnalysisResult
from kgtracevis.schema.evidence_schema import Evidence
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
    }
    return payload


def dashboard_fields_from_analysis(
    evidence: Evidence,
    analysis: AnalysisResult,
) -> dict[str, Any]:
    """Build dashboard fields for a single analyzed Evidence object."""
    top_k_paths = list(analysis.top_k_paths)
    source_edges = unique_source_edges(top_k_paths)
    correction_candidates = list(analysis.correction_candidates)
    linked_entities = list(analysis.linked_entities)
    return {
        "evidence_summary": compact_evidence_summary(evidence),
        "linked_entities": linked_entities,
        "correction_candidates": correction_candidates,
        "top_k_paths": top_k_paths,
        "path_graph": path_graph_from_paths(top_k_paths),
        "source_edge_provenance": source_edges,
        "review_targets": review_targets(
            linked_entities=linked_entities,
            correction_candidates=correction_candidates,
            top_k_paths=top_k_paths,
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
    cases = []
    for case in detail.cases:
        row = dict(case)
        top_k_paths = list_of_dicts(row.get("top_k_paths"))
        linked_entities = list_of_dicts(row.get("linked_entities"))
        correction_candidates = list_of_dicts(row.get("correction_candidates"))
        source_edges = list_of_dicts(row.get("source_edge_provenance"))
        if not row.get("path_graph"):
            row["path_graph"] = path_graph_from_paths(top_k_paths)
            changed = True
        if not row.get("review_targets"):
            row["review_targets"] = review_targets(
                linked_entities=linked_entities,
                correction_candidates=correction_candidates,
                top_k_paths=top_k_paths,
                source_edges=source_edges,
            )
            changed = True
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


def enriched_case_rows(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach graph and review fields to adapter-pipeline case rows."""
    enriched: list[dict[str, Any]] = []
    for case in cases:
        row = dict(case)
        top_k_paths = list_of_dicts(row.get("top_k_paths"))
        linked_entities = list_of_dicts(row.get("linked_entities"))
        correction_candidates = list_of_dicts(row.get("correction_candidates"))
        source_edges = list_of_dicts(row.get("source_edge_provenance"))
        row["path_graph"] = path_graph_from_paths(top_k_paths)
        row["review_targets"] = review_targets(
            linked_entities=linked_entities,
            correction_candidates=correction_candidates,
            top_k_paths=top_k_paths,
            source_edges=source_edges,
        )
        enriched.append(row)
    return enriched


def dashboard_fields_from_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Build aggregate dashboard fields from adapter-pipeline case rows."""
    linked_entities: list[dict[str, Any]] = []
    correction_candidates: list[dict[str, Any]] = []
    top_k_paths: list[dict[str, Any]] = []
    source_edges_by_id: dict[str, dict[str, Any]] = {}
    evidence_summary: dict[str, Any] | None = None

    for case in cases:
        if evidence_summary is None and isinstance(case.get("generated_evidence"), dict):
            evidence_summary = dict(case["generated_evidence"])
        linked_entities.extend(list_of_dicts(case.get("linked_entities")))
        correction_candidates.extend(list_of_dicts(case.get("correction_candidates")))
        top_k_paths.extend(list_of_dicts(case.get("top_k_paths")))
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
        "path_graph": path_graph_from_paths(top_k_paths),
        "source_edge_provenance": source_edges,
        "review_targets": review_targets(
            linked_entities=linked_entities,
            correction_candidates=correction_candidates,
            top_k_paths=top_k_paths,
            source_edges=source_edges,
        ),
    }


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
                "supporting_evidence": path.get("supporting_evidence", []),
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
