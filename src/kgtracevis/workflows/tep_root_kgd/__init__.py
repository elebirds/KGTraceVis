# mypy: ignore-errors
"""Root-KGD TEP RCA provider adapted from TEP_KG for KGTraceVis."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from kgtracevis.core.result import RankedRootCause, RcaReasoningResult
from kgtracevis.kg.graph import KGEdge, KnowledgeGraph
from kgtracevis.schema.evidence_schema import Evidence
from kgtracevis.workflows.tep_root_kgd.assets import read_jsonl
from kgtracevis.workflows.tep_root_kgd.propagation import (
    default_relation_params,
    initial_edge_weight,
)
from kgtracevis.workflows.tep_root_kgd.root_kgd import rank_scenario, variable_order

DEFAULT_ROOT_KGD_ASSET_DIR = Path("data/kg/tep_root_kgd")
REQUIRED_ASSET_FILES = (
    "nodes.jsonl",
    "edges.jsonl",
    "tep_variable_mapping.jsonl",
    "anchor_discriminators.json",
    "relation_family_params.json",
    "rca_edge_weights.jsonl",
    "anchor_memory_profiles.json",
)


class TepRootKgdConfig(BaseModel):
    """Runtime asset configuration for TEP Root-KGD inference."""

    model_config = ConfigDict(extra="forbid")

    asset_dir: Path = DEFAULT_ROOT_KGD_ASSET_DIR
    source_name: str = "tep_root_kgd"


@dataclass(frozen=True)
class TepRootKgdAssets:
    """Loaded Root-KGD graph and model parameters."""

    asset_dir: Path
    graph: dict[str, object]
    ordered_variables: list[str]
    variable_mapping: dict[str, str]
    anchor_discriminators: dict[str, dict[str, object]]
    anchor_memory_profiles: dict[str, dict[str, object]]


class TepRootKgdRcaProvider:
    """Rank TEP RCA candidates with TEP_KG Root-KGD runtime inference."""

    def __init__(self, config: TepRootKgdConfig | str | Path | None = None) -> None:
        """Create a provider from checked-in Root-KGD model assets."""
        if config is None:
            self.config = TepRootKgdConfig()
        elif isinstance(config, TepRootKgdConfig):
            self.config = config
        else:
            self.config = TepRootKgdConfig(asset_dir=Path(config))
        self.assets = load_root_kgd_assets(self.config.asset_dir)

    def reason_root_causes(
        self,
        evidence: Evidence,
        *,
        graph: KnowledgeGraph,
        linked_entities: list[dict[str, Any]],
        top_k: int = 5,
    ) -> RcaReasoningResult:
        """Return Root-KGD rankings and explanation paths for one Evidence item."""
        del linked_entities
        ranked, paths, metadata = self._rank_with_paths(evidence, graph=graph, top_k=top_k)
        return RcaReasoningResult(
            case_id=evidence.case_id,
            top_k_paths=paths,
            ranked_root_causes=ranked,
            scoring_method="tep_root_kgd",
            metadata=metadata,
        )

    def rank_root_causes(
        self,
        evidence: Evidence,
        *,
        graph: KnowledgeGraph | None = None,
        top_k: int = 5,
        top_k_paths: list[dict[str, Any]] | None = None,
    ) -> list[RankedRootCause]:
        """Return Root-KGD root-cause candidates for one TEP Evidence item."""
        del top_k_paths
        ranked, _paths, _metadata = self._rank_with_paths(
            evidence,
            graph=graph,
            top_k=top_k,
        )
        return ranked

    def _rank_with_paths(
        self,
        evidence: Evidence,
        *,
        graph: KnowledgeGraph | None = None,
        top_k: int,
    ) -> tuple[list[RankedRootCause], list[dict[str, Any]], dict[str, Any]]:
        if evidence.dataset != "tep":
            return [], [], _metadata(self.assets, uses_fault_number=False)

        graph_contributions = extract_root_kgd_graph_contributions(
            evidence,
            self.assets.variable_mapping,
        )
        if not graph_contributions:
            return [], [], _metadata(self.assets, uses_fault_number=False)

        dynamic_features = extract_root_kgd_dynamic_features(evidence)
        scenario = {
            "scenario_id": evidence.case_id,
            "fault_number": _fault_number_metadata(evidence) or 0,
            "simulation_run": _simulation_run_metadata(evidence) or 0,
            "graph_contributions": graph_contributions,
        }
        rows = rank_scenario(
            self.assets.graph,
            scenario,
            self.assets.ordered_variables,
            anchor_discriminators=self.assets.anchor_discriminators,
            scenario_dynamic_features={
                evidence.case_id: {
                    "scenario_id": evidence.case_id,
                    "features": dynamic_features,
                }
            },
            anchor_memory_profiles=self.assets.anchor_memory_profiles,
        )
        rows = rows[:top_k]
        overlay_index = _runtime_overlay_index(graph)
        paths = _select_top_k_paths(
            _top_k_paths_from_rows(
                evidence.case_id,
                rows,
                self.assets.graph,
                runtime_overlay_index=overlay_index,
            ),
            rows,
            top_k=top_k,
        )
        ranked = [
            _ranked_root_cause_from_row(
                evidence.case_id,
                row,
                graph=self.assets.graph,
                top_k_paths=paths,
                source_name=self.config.source_name,
            )
            for row in rows
        ]
        return ranked, paths[:top_k], {
            **_metadata(self.assets, uses_fault_number=False),
            "graph_contribution_count": len(graph_contributions),
            "dynamic_feature_count": len(dynamic_features),
            "runtime_overlay_provenance_edges": sum(len(edges) for edges in overlay_index.values()),
            "runtime_overlay_kg_build_ids": _unique_values(
                edge.kg_build_id
                for edges in overlay_index.values()
                for edge in edges
            ),
        }


def _select_top_k_paths(
    paths: list[dict[str, Any]],
    rows: list[dict[str, object]],
    *,
    top_k: int,
) -> list[dict[str, Any]]:
    """Pick review paths so ranked candidates only reference returned paths."""
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    by_candidate: dict[str, list[dict[str, Any]]] = {}
    for path in paths:
        candidate_id = str(path.get("root_cause_candidate_id") or "")
        by_candidate.setdefault(candidate_id, []).append(path)

    for row in rows:
        candidate_id = str(row.get("candidate_id") or "")
        candidate_paths = by_candidate.get(candidate_id, [])
        if not candidate_paths:
            continue
        path = candidate_paths[0]
        path_id = str(path.get("path_id") or "")
        if path_id and path_id not in selected_ids:
            selected.append(path)
            selected_ids.add(path_id)
        if len(selected) >= top_k:
            return selected

    for path in paths:
        path_id = str(path.get("path_id") or "")
        if path_id and path_id in selected_ids:
            continue
        selected.append(path)
        if path_id:
            selected_ids.add(path_id)
        if len(selected) >= top_k:
            break
    return selected


def load_root_kgd_assets(asset_dir: str | Path = DEFAULT_ROOT_KGD_ASSET_DIR) -> TepRootKgdAssets:
    """Load Root-KGD runtime graph/model assets from ``asset_dir``."""
    root = Path(asset_dir)
    missing = [name for name in REQUIRED_ASSET_FILES if not (root / name).is_file()]
    if missing:
        raise FileNotFoundError(
            f"Missing TEP Root-KGD asset file(s) in {root}: {', '.join(missing)}"
        )

    nodes = {str(row["entity_id"]): row for row in read_jsonl(root / "nodes.jsonl")}
    relation_params = _load_relation_params(root / "relation_family_params.json")
    edge_weights = _load_edge_weights(root / "rca_edge_weights.jsonl")
    edges = []
    for row in read_jsonl(root / "edges.jsonl"):
        if not bool(row.get("propagation_enabled", False)):
            continue
        edge_id = str(row["edge_id"])
        edge_weight = (
            round(float(edge_weights[edge_id]), 6)
            if edge_id in edge_weights
            else initial_edge_weight(row, {})
        )
        edges.append({**row, "edge_id": edge_id, "edge_weight": edge_weight})
    outgoing: dict[str, list[dict[str, object]]] = {}
    incoming: dict[str, list[dict[str, object]]] = {}
    for edge in edges:
        outgoing.setdefault(str(edge["head_id"]), []).append(edge)
        incoming.setdefault(str(edge["tail_id"]), []).append(edge)
    for edge_list in outgoing.values():
        edge_list.sort(
            key=lambda edge: (
                -int(relation_params[str(edge["relation_family"])]["priority"]),
                str(edge["tail_id"]),
                str(edge["edge_id"]),
            )
        )
    graph = {
        "nodes": nodes,
        "edges": {str(edge["edge_id"]): edge for edge in edges},
        "outgoing": outgoing,
        "incoming": incoming,
        "relation_params": relation_params,
    }
    variable_mapping = _load_variable_mapping(root / "tep_variable_mapping.jsonl")
    ordered_variables = [
        str(row["kg_entity_id"])
        for row in _load_ordered_mapping(root / "tep_variable_mapping.jsonl")
    ]
    return TepRootKgdAssets(
        asset_dir=root,
        graph=graph,
        ordered_variables=ordered_variables,
        variable_mapping=variable_mapping,
        anchor_discriminators=_load_anchor_rows(root / "anchor_discriminators.json"),
        anchor_memory_profiles=_load_anchor_memory_profiles(root / "anchor_memory_profiles.json"),
    )


def extract_root_kgd_graph_contributions(
    evidence: Evidence,
    variable_mapping: dict[str, str],
) -> dict[str, float]:
    """Extract current-sample Root-KGD graph contributions from Evidence."""
    contributions: dict[str, float] = {}
    for payload in _candidate_contribution_payloads(evidence):
        for raw_key, raw_value in payload.items():
            value = _optional_float(raw_value)
            if value is None or value <= 0.0:
                continue
            entity_id = _root_kgd_variable_id(str(raw_key), variable_mapping)
            if not entity_id:
                continue
            contributions[entity_id] = max(contributions.get(entity_id, 0.0), value)
    return {
        entity_id: round(value, 8)
        for entity_id, value in sorted(contributions.items())
    }


def extract_root_kgd_dynamic_features(evidence: Evidence) -> dict[str, float]:
    """Extract current-window dynamic features from Evidence extra payloads."""
    raw_extra = evidence.raw_evidence.extra or {}
    normalized = evidence.normalized_evidence or {}
    for container in (raw_extra, normalized):
        for key in (
            "root_kgd_dynamic_features",
            "scenario_dynamic_features",
            "dynamic_features",
        ):
            features = _feature_dict(container.get(key))
            if features:
                return features
    return {}


def _load_ordered_mapping(path: Path) -> list[dict[str, object]]:
    return sorted(
        read_jsonl(path),
        key=lambda row: (
            str(row.get("tep_variable_family", "")),
            int(row.get("tep_variable_index", 0)),
            str(row.get("sequence_column", "")),
        ),
    )


def _load_variable_mapping(path: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for row in read_jsonl(path):
        entity_id = str(row.get("kg_entity_id") or "")
        if not entity_id:
            continue
        keys = {
            str(row.get("sequence_column") or ""),
            str(row.get("tep_channel") or ""),
            entity_id,
            entity_id.removeprefix("variable:"),
        }
        keys.update(str(row.get("alternate_entity_ids") or "").replace("|", ",").split(","))
        for key in keys:
            normalized = _channel_key(key)
            if normalized:
                mapping[normalized] = entity_id
    return mapping


def _load_relation_params(path: Path) -> dict[str, dict[str, float]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    families = payload.get("families", payload)
    if not isinstance(families, dict):
        return default_relation_params()
    return {
        str(family): {
            "sigma": float(values["sigma"]),
            "priority": int(values["priority"]),
        }
        for family, values in families.items()
        if isinstance(values, dict)
        and "sigma" in values
        and "priority" in values
    } or default_relation_params()


def _load_edge_weights(path: Path) -> dict[str, float]:
    return {
        str(row["edge_id"]): float(row["edge_weight"])
        for row in read_jsonl(path)
        if row.get("edge_id") and row.get("edge_weight") is not None
    }


def _load_anchor_rows(path: Path) -> dict[str, dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("anchors", [])
    if not isinstance(rows, list):
        return {}
    return {
        str(row["anchor_id"]): row
        for row in rows
        if isinstance(row, dict) and row.get("anchor_id")
    }


def _load_anchor_memory_profiles(path: Path) -> dict[str, dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("anchors", [])
    if not isinstance(rows, list):
        return {}
    return {
        str(row["anchor_id"]): row
        for row in rows
        if isinstance(row, dict) and row.get("anchor_id")
    }


def _candidate_contribution_payloads(evidence: Evidence) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    if evidence.raw_evidence.variable_contributions:
        payloads.append(dict(evidence.raw_evidence.variable_contributions))
    raw_extra = evidence.raw_evidence.extra or {}
    normalized = evidence.normalized_evidence or {}
    for container in (raw_extra, normalized):
        for key in (
            "graph_contributions",
            "channel_contributions",
            "variable_contributions",
            "variable_scores",
            "contribution_scores",
        ):
            value = container.get(key)
            if isinstance(value, dict):
                payloads.append(dict(value))
    return payloads


def _root_kgd_variable_id(raw_name: str, variable_mapping: dict[str, str]) -> str | None:
    key = _channel_key(raw_name)
    if key in variable_mapping:
        return variable_mapping[key]
    if key.startswith("variable:"):
        return key
    if key.startswith("xmeas_"):
        return f"variable:{key}"
    return None


def _channel_key(raw_name: str) -> str:
    text = raw_name.strip().lower()
    if not text:
        return ""
    text = text.replace(" ", "_")
    text = re.sub(r"^variable[:_]", "variable:", text)
    for prefix in ("xmeas", "xmv"):
        match = re.fullmatch(rf"{prefix}_?(\d+)", text)
        if match:
            return f"{prefix}_{int(match.group(1))}"
    return text


def _feature_dict(value: Any) -> dict[str, float]:
    if isinstance(value, dict) and isinstance(value.get("features"), dict):
        value = value["features"]
    if not isinstance(value, dict):
        return {}
    features: dict[str, float] = {}
    for key, raw_value in value.items():
        parsed = _optional_float(raw_value)
        if parsed is not None:
            features[str(key)] = parsed
    return features


def _fault_number_metadata(evidence: Evidence) -> int | None:
    return _int_metadata(evidence, "fault_number", "fault_id")


def _simulation_run_metadata(evidence: Evidence) -> int | None:
    return _int_metadata(evidence, "simulation_run", "simulation_id", "run_id")


def _int_metadata(evidence: Evidence, *keys: str) -> int | None:
    raw_extra = evidence.raw_evidence.extra or {}
    for key in keys:
        for container in (raw_extra, evidence.normalized_evidence or {}):
            value = container.get(key)
            if value not in (None, ""):
                try:
                    return int(str(value))
                except ValueError:
                    continue
    return None


def _top_k_paths_from_rows(
    case_id: str,
    rows: list[dict[str, object]],
    graph: dict[str, object],
    *,
    runtime_overlay_index: dict[str, list[KGEdge]],
) -> list[dict[str, Any]]:
    paths: list[dict[str, Any]] = []
    for row in rows:
        for path_index, node_path in enumerate(row.get("top_support_paths", []), start=1):
            if not isinstance(node_path, list) or len(node_path) < 2:
                continue
            edge_rows = _edge_rows_for_node_path(node_path, graph)
            source_edges = [
                payload
                for edge in edge_rows
                for payload in _source_edge_payloads(edge, runtime_overlay_index)
            ]
            candidate_id = str(row["candidate_id"])
            paths.append(
                {
                    "path_id": f"root_kgd_{case_id}_{_safe_token(candidate_id)}_{path_index}",
                    "source_entity_id": candidate_id,
                    "target_entity_id": str(node_path[-1]),
                    "root_cause_candidate_id": candidate_id,
                    "nodes": [str(node_id) for node_id in node_path],
                    "node_names": [_node_name(graph, str(node_id)) for node_id in node_path],
                    "relations": [str(edge.get("relation_family", "")) for edge in edge_rows],
                    "score": float(row.get("ranking_score", 0.0)),
                    "confidence": float(row.get("root_score", 0.0)),
                    "evidence_match": float(row.get("discriminator_alignment", 0.0)),
                    "source_edges": source_edges,
                    "source_edge_ids": _unique_values(
                        edge.get("edge_id") for edge in source_edges
                    ),
                    "kg_build_ids": _unique_values(
                        edge.get("kg_build_id") for edge in source_edges
                    ),
                    "supporting_evidence": [
                        (
                            f"{row.get('candidate_name', candidate_id)} propagated to "
                            f"{_node_name(graph, str(node_path[-1]))}"
                        )
                    ],
                    "scoring_method": "tep_root_kgd",
                }
            )
    return paths


def _ranked_root_cause_from_row(
    case_id: str,
    row: dict[str, object],
    *,
    graph: dict[str, object],
    top_k_paths: list[dict[str, Any]],
    source_name: str,
) -> RankedRootCause:
    candidate_id = str(row["candidate_id"])
    candidate_paths = [
        path for path in top_k_paths if path.get("root_cause_candidate_id") == candidate_id
    ]
    supporting_edges = _dedupe_source_edges(
        edge
        for path in candidate_paths
        for edge in path.get("source_edges", [])
        if isinstance(edge, dict)
    )
    return RankedRootCause(
        ranking_id=str(row["ranking_id"]),
        rank=int(row["rank"]),
        candidate_id=candidate_id,
        candidate_name=str(row.get("candidate_name") or _node_name(graph, candidate_id)),
        candidate_label=str(row.get("candidate_type") or "") or None,
        candidate_role=str(row.get("candidate_role") or "") or None,
        score=round(float(row.get("ranking_score", 0.0)), 8),
        confidence=max(0.0, min(1.0, float(row.get("root_score", 0.0)))),
        evidence_match=max(0.0, min(1.0, float(row.get("discriminator_alignment", 0.0)))),
        explanation_paths=candidate_paths,
        supporting_edges=supporting_edges,
        supporting_evidence=[
            {
                "evidence_id": f"{row['ranking_id']}_affected_{index}",
                "source": "tep_root_kgd_current_evidence",
                "variable": item.get("entity_id"),
                "text": (
                    f"{item.get('name', item.get('entity_id'))} has current "
                    f"contribution {item.get('rbc_contribution', 0.0)}"
                ),
            }
            for index, item in enumerate(row.get("top_affected_variables", []), start=1)
            if isinstance(item, dict)
        ],
        scoring_method="tep_root_kgd",
        scoring_details={
            key: value
            for key, value in row.items()
            if not str(key).startswith("_")
            and key
            not in {
                "ranking_id",
                "rank",
                "candidate_id",
                "candidate_name",
                "candidate_type",
                "candidate_role",
                "top_support_paths",
                "top_affected_variables",
            }
        },
        source=source_name,
        review_status="auto",
    )


def _edge_rows_for_node_path(
    node_path: list[object],
    graph: dict[str, object],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for head_id, tail_id in zip(node_path, node_path[1:], strict=False):
        edge = _best_edge(str(head_id), str(tail_id), graph)
        if edge is not None:
            rows.append(edge)
    return rows


def _best_edge(
    head_id: str,
    tail_id: str,
    graph: dict[str, object],
) -> dict[str, object] | None:
    candidates = [
        edge
        for edge in graph["outgoing"].get(head_id, [])
        if str(edge.get("tail_id")) == tail_id
    ]
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda edge: (-float(edge.get("edge_weight", 0.0)), str(edge.get("edge_id", ""))),
    )[0]


def _source_edge_payloads(
    edge: dict[str, object],
    runtime_overlay_index: dict[str, list[KGEdge]],
) -> list[dict[str, Any]]:
    static_edge_id = str(edge.get("edge_id", ""))
    overlay_edges = runtime_overlay_index.get(static_edge_id, [])
    if not overlay_edges:
        return [_static_source_edge_payload(edge)]
    return [_overlay_source_edge_payload(edge, overlay_edge) for overlay_edge in overlay_edges]


def _static_source_edge_payload(edge: dict[str, object]) -> dict[str, Any]:
    edge_id = str(edge.get("edge_id", ""))
    return {
        "edge_id": edge_id,
        "head": str(edge.get("head_id", "")),
        "relation": str(edge.get("relation_family") or edge.get("relation") or ""),
        "tail": str(edge.get("tail_id", "")),
        "confidence": _optional_float(edge.get("confidence")),
        "weight": _optional_float(edge.get("edge_weight")),
        "source": ",".join(str(item) for item in edge.get("source_types", []) or []),
        "evidence": ",".join(str(item) for item in edge.get("provenance_ids", []) or []),
        "review_status": str(edge.get("review_status", "auto")),
        "external_edge_id": edge_id,
        "root_kgd_edge_id": edge_id,
    }


def _overlay_source_edge_payload(
    root_kgd_edge: dict[str, object],
    overlay_edge: KGEdge,
) -> dict[str, Any]:
    payload = overlay_edge.model_dump()
    root_edge_id = str(root_kgd_edge.get("edge_id", ""))
    payload.update(
        {
            "external_edge_id": overlay_edge.external_edge_id or root_edge_id,
            "root_kgd_edge_id": root_edge_id,
            "root_kgd_head": str(root_kgd_edge.get("head_id", "")),
            "root_kgd_relation": str(
                root_kgd_edge.get("relation_family") or root_kgd_edge.get("relation") or ""
            ),
            "root_kgd_tail": str(root_kgd_edge.get("tail_id", "")),
        }
    )
    return payload


def _runtime_overlay_index(graph: KnowledgeGraph | None) -> dict[str, list[KGEdge]]:
    if graph is None:
        return {}
    by_external_id: dict[str, list[KGEdge]] = {}
    for edge in graph.edges:
        external_edge_id = edge.external_edge_id.strip()
        if not external_edge_id:
            continue
        by_external_id.setdefault(external_edge_id, []).append(edge)
    for edges in by_external_id.values():
        edges.sort(key=lambda edge: (edge.edge_id, edge.kg_build_id))
    return by_external_id


def _dedupe_source_edges(edges: Any) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for edge in edges:
        edge_id = str(edge.get("edge_id") or "")
        if edge_id:
            by_id.setdefault(edge_id, dict(edge))
    return [by_id[edge_id] for edge_id in sorted(by_id)]


def _unique_values(values: Any) -> list[str]:
    unique = set()
    for value in values:
        if value is None:
            continue
        text = str(value)
        if text:
            unique.add(text)
    return sorted(unique)


def _node_name(graph: dict[str, object], node_id: str) -> str:
    node = graph["nodes"].get(node_id, {})
    return str(node.get("name") or node_id)


def _metadata(assets: TepRootKgdAssets, *, uses_fault_number: bool) -> dict[str, Any]:
    return {
        "reasoner": "tep_root_kgd",
        "asset_dir": str(assets.asset_dir),
        "node_count": len(assets.graph["nodes"]),
        "edge_count": len(assets.graph["edges"]),
        "ordered_variable_count": len(assets.ordered_variables),
        "anchor_discriminator_count": len(assets.anchor_discriminators),
        "anchor_memory_profile_count": len(assets.anchor_memory_profiles),
        "uses_fault_number_for_scoring": uses_fault_number,
    }


def _optional_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_token(value: str) -> str:
    token = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return token or "candidate"


__all__ = [
    "DEFAULT_ROOT_KGD_ASSET_DIR",
    "TepRootKgdAssets",
    "TepRootKgdConfig",
    "TepRootKgdRcaProvider",
    "extract_root_kgd_dynamic_features",
    "extract_root_kgd_graph_contributions",
    "load_root_kgd_assets",
    "rank_scenario",
    "variable_order",
]
