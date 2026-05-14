"""Adapter-to-pipeline orchestration for producer-output records."""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kgtracevis.adapters.batch import evidence_from_records, load_records, write_evidence_files
from kgtracevis.core import KGTracePipeline
from kgtracevis.kg.graph import DEFAULT_EDGE_PATHS, DEFAULT_NODE_PATHS, KnowledgeGraph
from kgtracevis.schema.evidence_schema import DatasetName, Evidence
from kgtracevis.workflows.root_cause_provider_selection import (
    RootCauseProviderSelectionConfig,
    build_pipeline,
    normalize_root_cause_provider_selection,
)

SUMMARY_FILENAME = "adapter_pipeline_summary.json"
TABLE_FILENAME = "adapter_pipeline_table.csv"
EVIDENCE_DIRNAME = "evidence"
ARTIFACT_TYPE = "adapter_pipeline_v0"
EXPLANATION_SCOPE = "candidate_plausible_explanation_not_verified_rca"
TABLE_COLUMNS = (
    "case_id",
    "dataset",
    "adapter_name",
    "anomaly_type",
    "location",
    "morphology",
    "consistency_score",
    "linked_entity_count",
    "correction_candidate_count",
    "path_count",
    "top_target_entity_id",
    "top_target_name",
    "top_target_label",
    "best_score",
    "explanation_scope",
    "claim_boundary",
)


@dataclass(frozen=True)
class AdapterPipelineOutput:
    """Paths and payload produced by one adapter-to-pipeline run."""

    summary_path: Path
    table_path: Path
    evidence_paths: list[Path]
    summary: dict[str, Any]


def run_adapter_pipeline(
    input_path: str | Path,
    output_dir: str | Path,
    *,
    dataset: DatasetName | None = None,
    top_k: int = 5,
    overwrite: bool = False,
    pipeline: KGTracePipeline | None = None,
    kg_node_paths: list[str | Path] | None = None,
    kg_edge_paths: list[str | Path] | None = None,
    tep_rca_provider: str | None = None,
    tep_rca_artifact_dir: str | Path | None = None,
    tep_rca_ranking_path: str | Path | None = None,
    tep_rca_contributions_path: str | Path | None = None,
) -> AdapterPipelineOutput:
    """Run records through Evidence adapters and ``KGTracePipeline``.

    The output is intentionally scoped as candidate/plausible explanation
    provenance, not verified root-cause analysis.
    """
    if top_k < 1:
        raise ValueError("top_k must be >= 1")

    source_path = Path(input_path)
    destination_dir = Path(output_dir)
    evidence_dir = destination_dir / EVIDENCE_DIRNAME
    summary_path = destination_dir / SUMMARY_FILENAME
    table_path = destination_dir / TABLE_FILENAME
    _ensure_can_write(summary_path, overwrite=overwrite)
    _ensure_can_write(table_path, overwrite=overwrite)

    records = load_records(source_path)
    evidence_items = evidence_from_records(records, dataset=dataset)
    evidence_paths = write_evidence_files(
        evidence_items,
        evidence_dir,
        overwrite=overwrite,
    )

    if pipeline is not None and (kg_node_paths or kg_edge_paths):
        raise ValueError("pass either pipeline or KG CSV overlay paths, not both")
    provider_config = _root_cause_provider_config(
        tep_rca_provider=tep_rca_provider,
        tep_rca_artifact_dir=tep_rca_artifact_dir,
        tep_rca_ranking_path=tep_rca_ranking_path,
        tep_rca_contributions_path=tep_rca_contributions_path,
    )
    if pipeline is not None and provider_config.tep_rca_provider != "none":
        raise ValueError("pass either pipeline or TEP RCA provider options, not both")

    active_pipeline = pipeline or _pipeline_from_kg_paths(
        kg_node_paths=kg_node_paths,
        kg_edge_paths=kg_edge_paths,
        root_cause_provider_config=provider_config,
    )
    cases = [
        _case_summary(
            evidence_path=evidence_path,
            evidence=evidence,
            analysis=active_pipeline.analyze(evidence, top_k=top_k).model_dump(mode="json"),
            pipeline=active_pipeline,
        )
        for evidence_path, evidence in zip(evidence_paths, evidence_items, strict=True)
    ]

    summary = _run_summary(
        input_path=source_path,
        output_dir=destination_dir,
        dataset=dataset,
        top_k=top_k,
        kg_node_paths=kg_node_paths,
        kg_edge_paths=kg_edge_paths,
        root_cause_provider_config=provider_config,
        evidence_paths=evidence_paths,
        cases=cases,
    )
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_adapter_pipeline_table(summary, table_path, overwrite=overwrite)
    return AdapterPipelineOutput(
        summary_path=summary_path,
        table_path=table_path,
        evidence_paths=evidence_paths,
        summary=summary,
    )


def write_adapter_pipeline_table(
    summary: Mapping[str, Any],
    output_path: str | Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Write paper-review scoped adapter pipeline case rows to CSV."""
    destination = Path(output_path)
    _ensure_can_write(destination, overwrite=overwrite)
    destination.parent.mkdir(parents=True, exist_ok=True)
    rows = adapter_pipeline_table_rows(summary)
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=TABLE_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return destination


def adapter_pipeline_table_rows(summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return one scoped table row per adapter pipeline case."""
    explanation_scope = str(summary.get("explanation_scope", EXPLANATION_SCOPE))
    cases = summary.get("cases", [])
    if not isinstance(cases, list):
        return []
    return [
        _case_table_row(case, explanation_scope=explanation_scope)
        for case in cases
        if isinstance(case, Mapping)
    ]


def _run_summary(
    *,
    input_path: Path,
    output_dir: Path,
    dataset: DatasetName | None,
    top_k: int,
    kg_node_paths: list[str | Path] | None,
    kg_edge_paths: list[str | Path] | None,
    root_cause_provider_config: RootCauseProviderSelectionConfig,
    evidence_paths: list[Path],
    cases: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "artifact_type": ARTIFACT_TYPE,
        "artifact_scope": "generated_reproducibility_output",
        "explanation_scope": EXPLANATION_SCOPE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input": {
            "record_path": str(input_path),
            "dataset_override": dataset,
        },
        "output": {
            "output_dir": str(output_dir),
            "evidence_dir": str(output_dir / EVIDENCE_DIRNAME),
            "summary_path": str(output_dir / SUMMARY_FILENAME),
            "table_path": str(output_dir / TABLE_FILENAME),
            "evidence_paths": [str(path) for path in evidence_paths],
        },
        "pipeline": {
            "name": "KGTracePipeline",
            "kg_backend": "explicit_seed_overlay"
            if kg_node_paths or kg_edge_paths
            else "neo4j_runtime",
            "top_k": top_k,
            "kg_node_paths": [str(path) for path in kg_node_paths or []],
            "kg_edge_paths": [str(path) for path in kg_edge_paths or []],
            **_root_cause_provider_summary(root_cause_provider_config),
        },
        "note": (
            "Path targets are candidate/plausible explanation nodes generated from "
            "source-constrained KG edges; they are not verified process RCA claims."
        ),
        "case_count": len(cases),
        "cases": cases,
    }


def _pipeline_from_kg_paths(
    *,
    kg_node_paths: list[str | Path] | None,
    kg_edge_paths: list[str | Path] | None,
    root_cause_provider_config: RootCauseProviderSelectionConfig,
) -> KGTracePipeline:
    if not kg_node_paths and not kg_edge_paths:
        return build_pipeline(root_cause_provider_config=root_cause_provider_config)
    graph = KnowledgeGraph.from_paths(
        [*DEFAULT_NODE_PATHS, *(kg_node_paths or [])],
        [*DEFAULT_EDGE_PATHS, *(kg_edge_paths or [])],
        skip_missing=True,
    )
    return build_pipeline(
        graph=graph,
        root_cause_provider_config=root_cause_provider_config,
    )


def _root_cause_provider_config(
    *,
    tep_rca_provider: str | None,
    tep_rca_artifact_dir: str | Path | None,
    tep_rca_ranking_path: str | Path | None,
    tep_rca_contributions_path: str | Path | None,
) -> RootCauseProviderSelectionConfig:
    return RootCauseProviderSelectionConfig(
        tep_rca_provider=normalize_root_cause_provider_selection(tep_rca_provider),
        tep_rca_artifact_dir=Path(tep_rca_artifact_dir)
        if tep_rca_artifact_dir is not None
        else None,
        tep_rca_ranking_path=Path(tep_rca_ranking_path)
        if tep_rca_ranking_path is not None
        else None,
        tep_rca_contributions_path=Path(tep_rca_contributions_path)
        if tep_rca_contributions_path is not None
        else None,
    )


def _root_cause_provider_summary(
    config: RootCauseProviderSelectionConfig,
) -> dict[str, Any]:
    if config.tep_rca_provider == "none":
        return {}
    return {
        "root_cause_provider": config.tep_rca_provider,
        "tep_rca_artifact_dir": (
            str(config.tep_rca_artifact_dir) if config.tep_rca_artifact_dir else None
        ),
        "tep_rca_ranking_path": (
            str(config.tep_rca_ranking_path) if config.tep_rca_ranking_path else None
        ),
        "tep_rca_contributions_path": (
            str(config.tep_rca_contributions_path)
            if config.tep_rca_contributions_path
            else None
        ),
    }


def _case_summary(
    *,
    evidence_path: Path,
    evidence: Evidence,
    analysis: Mapping[str, Any],
    pipeline: KGTracePipeline,
) -> dict[str, Any]:
    top_k_paths = list(analysis["top_k_paths"])
    ranked_root_causes = list(analysis.get("ranked_root_causes", []))
    source_edges = _unique_source_edges(top_k_paths)
    return {
        "case_id": evidence.case_id,
        "dataset": evidence.dataset,
        "source": evidence.source,
        "adapter_name": evidence.adapter.name if evidence.adapter else None,
        "generated_evidence_path": str(evidence_path),
        "generated_evidence": _compact_evidence_summary(evidence),
        "linked_entity_count": len(analysis["linked_entities"]),
        "linked_entities": analysis["linked_entities"],
        "consistency_score": analysis["consistency_score"],
        "inconsistent_fields": analysis["inconsistent_fields"],
        "correction_candidates": analysis["correction_candidates"],
        "top_k_paths": top_k_paths,
        "ranked_root_causes": ranked_root_causes,
        "candidate_plausible_explanation_targets": _candidate_targets(
            top_k_paths,
            source_edges=source_edges,
            graph=pipeline.graph_for_evidence(evidence),
        ),
        "source_edge_provenance": source_edges,
        "claim_boundary": (
            "candidate/plausible explanation only; not a verified root-cause label"
        ),
    }


def _compact_evidence_summary(evidence: Evidence) -> dict[str, Any]:
    return {
        "case_id": evidence.case_id,
        "dataset": evidence.dataset,
        "object": evidence.object,
        "anomaly_type": evidence.anomaly_type,
        "location": evidence.location,
        "morphology": evidence.morphology,
        "severity": evidence.severity,
        "confidence": evidence.confidence,
        "observation_count": len(evidence.observations),
    }


def _case_table_row(
    case: Mapping[str, Any],
    *,
    explanation_scope: str,
) -> dict[str, Any]:
    evidence = case.get("generated_evidence", {})
    evidence_summary = evidence if isinstance(evidence, Mapping) else {}
    top_target = _top_table_target(case)
    return {
        "case_id": case.get("case_id", ""),
        "dataset": case.get("dataset", ""),
        "adapter_name": case.get("adapter_name", ""),
        "anomaly_type": evidence_summary.get("anomaly_type", ""),
        "location": evidence_summary.get("location", ""),
        "morphology": evidence_summary.get("morphology", ""),
        "consistency_score": case.get("consistency_score", ""),
        "linked_entity_count": case.get("linked_entity_count", 0),
        "correction_candidate_count": len(_list_value(case.get("correction_candidates"))),
        "path_count": len(_list_value(case.get("top_k_paths"))),
        "top_target_entity_id": top_target.get("target_entity_id", ""),
        "top_target_name": top_target.get("target_name", ""),
        "top_target_label": top_target.get("target_label", ""),
        "best_score": top_target.get("best_score", ""),
        "explanation_scope": explanation_scope,
        "claim_boundary": case.get("claim_boundary", ""),
    }


def _top_table_target(case: Mapping[str, Any]) -> Mapping[str, Any]:
    targets = _list_value(case.get("candidate_plausible_explanation_targets"))
    if not targets:
        return {}
    first = targets[0]
    return first if isinstance(first, Mapping) else {}


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _candidate_targets(
    top_k_paths: list[Mapping[str, Any]],
    *,
    source_edges: list[dict[str, Any]],
    graph: KnowledgeGraph,
) -> list[dict[str, Any]]:
    targets: dict[str, dict[str, Any]] = {}
    edges_by_id = {edge["edge_id"]: edge for edge in source_edges}
    for path in top_k_paths:
        target_id = str(path["target_entity_id"])
        target = targets.setdefault(
            target_id,
            _target_seed(target_id, graph=graph),
        )
        target["supporting_path_ids"].append(path["path_id"])
        target["best_score"] = max(float(target["best_score"]), float(path["score"]))
        for edge_id in path.get("source_edge_ids", []):
            edge = edges_by_id.get(edge_id)
            if edge is not None and edge not in target["source_edges"]:
                target["source_edges"].append(edge)

    return sorted(
        targets.values(),
        key=lambda item: (-float(item["best_score"]), str(item["target_entity_id"])),
    )


def _target_seed(target_id: str, *, graph: KnowledgeGraph) -> dict[str, Any]:
    node = graph.nodes.get(target_id)
    return {
        "target_entity_id": target_id,
        "target_name": node.name if node else target_id,
        "target_label": node.label if node else None,
        "interpretation": "candidate_plausible_explanation",
        "best_score": 0.0,
        "supporting_path_ids": [],
        "source_edges": [],
    }


def _unique_source_edges(top_k_paths: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    edges_by_id: dict[str, dict[str, Any]] = {}
    for path in top_k_paths:
        for edge in path.get("source_edges", []):
            if not isinstance(edge, Mapping):
                continue
            edge_id = str(edge.get("edge_id", ""))
            if edge_id:
                edges_by_id.setdefault(edge_id, dict(edge))
    return [edges_by_id[edge_id] for edge_id in sorted(edges_by_id)]


def _ensure_can_write(path: Path, *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"{path} already exists; pass --overwrite to replace it")
