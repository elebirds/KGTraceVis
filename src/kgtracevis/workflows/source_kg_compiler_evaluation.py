"""Evaluate the source KG compiler against KGBuilder artifacts and examples."""

from __future__ import annotations

import csv
import json
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kgtracevis.kg.graph import DEFAULT_EDGE_PATHS, DEFAULT_NODE_PATHS, KnowledgeGraph
from kgtracevis.schema.validators import load_evidence_json
from kgtracevis.source_kg_compiler.models import SourceKGLLMClient, SourceKGProgressCallback
from kgtracevis.source_kg_compiler.workflow import (
    DEFAULT_LLM_CONCURRENCY,
    SourceKGCompilerConfig,
    run_source_kg_compiler_workflow,
)
from kgtracevis.workflows.root_cause_provider_selection import build_pipeline

DEFAULT_KGBUILDER_MATERIALS_DIR = Path.home() / "code" / "KGBuilder" / "materials"
DEFAULT_KGBUILDER_OUTPUTS_DIR = Path.home() / "code" / "KGBuilder" / "outputs"
DEFAULT_SAMPLE_PATHS = (
    Path("data/examples/ds_mvtec_example.json"),
    Path("data/examples/mvtec_noisy_morphology_demo.json"),
    Path("data/examples/tep_example.json"),
    Path("data/examples/wafer_example.json"),
)


@dataclass(frozen=True)
class SourceKGCompilerEvaluationConfig:
    """Configuration for compiler parity and real-sample analysis."""

    output_dir: Path
    llm_client: SourceKGLLMClient | None = None
    materials_dir: Path = DEFAULT_KGBUILDER_MATERIALS_DIR
    source_paths: tuple[Path, ...] = ()
    baseline_output_dir: Path | None = DEFAULT_KGBUILDER_OUTPUTS_DIR
    sample_paths: tuple[Path, ...] = DEFAULT_SAMPLE_PATHS
    default_scenario: str = "shared"
    chunk_size: int = 8000
    chunk_overlap: int = 800
    top_k: int = 5
    overwrite: bool = False
    source_limit: int | None = None
    llm_concurrency: int = DEFAULT_LLM_CONCURRENCY
    progress_callback: SourceKGProgressCallback | None = None


@dataclass(frozen=True)
class SourceKGCompilerEvaluationResult:
    """Structured result for source KG compiler evaluation."""

    report: dict[str, Any]
    report_path: Path
    compiled_output_dir: Path


def run_source_kg_compiler_evaluation(
    config: SourceKGCompilerEvaluationConfig,
) -> SourceKGCompilerEvaluationResult:
    """Compile KGBuilder materials and analyze examples with generated-only KG."""
    started = time.perf_counter()
    source_paths = config.source_paths or (config.materials_dir,)
    output_dir = config.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    compiled_output_dir = output_dir / "compiled_kg"

    _emit_progress(
        config.progress_callback,
        stage="evaluation_config",
        event="stage_start",
        elapsed_seconds=0.0,
        output_dir=output_dir.as_posix(),
        compiled_output_dir=compiled_output_dir.as_posix(),
        source_paths=[Path(path).expanduser().as_posix() for path in source_paths],
        baseline_output_dir=(
            config.baseline_output_dir.expanduser().as_posix()
            if config.baseline_output_dir is not None
            else None
        ),
        sample_paths=[Path(path).as_posix() for path in config.sample_paths],
        default_scenario=config.default_scenario,
        chunk_size=config.chunk_size,
        chunk_overlap=config.chunk_overlap,
        top_k=config.top_k,
        overwrite=config.overwrite,
        source_limit=config.source_limit,
        llm_concurrency=config.llm_concurrency,
    )
    _emit_progress(
        config.progress_callback,
        stage="compile_start",
        event="stage_start",
        elapsed_seconds=round(time.perf_counter() - started, 3),
        output_dir=compiled_output_dir.as_posix(),
    )
    compiler_result = run_source_kg_compiler_workflow(
        SourceKGCompilerConfig(
            source_paths=tuple(Path(path) for path in source_paths),
            output_dir=compiled_output_dir,
            llm_client=config.llm_client,
            default_scenario=config.default_scenario,
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap,
            overwrite=config.overwrite,
            source_limit=config.source_limit,
            llm_concurrency=config.llm_concurrency,
            progress_callback=config.progress_callback,
        )
    )
    graph = KnowledgeGraph.from_csv(
        compiler_result.artifact_paths.nodes_csv,
        compiler_result.artifact_paths.edges_csv,
    )
    sample_reports = _analyze_samples(
        graph,
        sample_paths=config.sample_paths,
        top_k=config.top_k,
        progress_callback=config.progress_callback,
        started_at=started,
    )
    _emit_progress(
        config.progress_callback,
        stage="baseline_comparison",
        event="stage_start",
        elapsed_seconds=round(time.perf_counter() - started, 3),
        baseline_output_dir=(
            config.baseline_output_dir.expanduser().as_posix()
            if config.baseline_output_dir is not None
            else None
        ),
    )
    baseline_comparison = compare_kgbuilder_baseline(
        generated_output_dir=compiled_output_dir,
        baseline_output_dir=config.baseline_output_dir,
    )
    _emit_progress(
        config.progress_callback,
        stage="baseline_comparison",
        event="stage_finish",
        elapsed_seconds=round(time.perf_counter() - started, 3),
        status=baseline_comparison.get("status"),
    )
    report = _evaluation_report(
        config=config,
        source_paths=source_paths,
        compiler_summary=compiler_result.summary,
        qa_report=compiler_result.qa_report,
        validation_report=compiler_result.validation_report,
        baseline_comparison=baseline_comparison,
        graph=graph,
        sample_reports=sample_reports,
        runtime_seconds=round(time.perf_counter() - started, 6),
        compiled_output_dir=compiled_output_dir,
    )
    report_path = output_dir / "source_kg_compiler_evaluation_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    _emit_progress(
        config.progress_callback,
        stage="report_written",
        event="stage_finish",
        elapsed_seconds=round(time.perf_counter() - started, 3),
        report_path=report_path.as_posix(),
        compiled_output_dir=compiled_output_dir.as_posix(),
    )
    return SourceKGCompilerEvaluationResult(
        report=report,
        report_path=report_path,
        compiled_output_dir=compiled_output_dir,
    )


def compare_kgbuilder_baseline(
    *,
    generated_output_dir: Path,
    baseline_output_dir: Path | None,
) -> dict[str, Any]:
    """Compare generated artifacts with existing KGBuilder output artifacts."""
    generated = _artifact_inventory(generated_output_dir, generated=True)
    if baseline_output_dir is None:
        return {
            "status": "not_configured",
            "baseline_output_dir": None,
            "generated": generated,
            "baseline": {},
            "metrics": {},
        }
    baseline_dir = Path(baseline_output_dir).expanduser()
    baseline = _artifact_inventory(baseline_dir, generated=False)
    if not baseline["available"]:
        return {
            "status": "missing",
            "baseline_output_dir": baseline_dir.as_posix(),
            "generated": generated,
            "baseline": baseline,
            "metrics": {},
        }
    return {
        "status": "compared",
        "baseline_output_dir": baseline_dir.as_posix(),
        "generated": generated,
        "baseline": baseline,
        "metrics": _comparison_metrics(generated, baseline),
    }


def _analyze_samples(
    graph: KnowledgeGraph,
    *,
    sample_paths: tuple[Path, ...],
    top_k: int,
    progress_callback: SourceKGProgressCallback | None = None,
    started_at: float | None = None,
) -> list[dict[str, Any]]:
    started = time.perf_counter() if started_at is None else started_at
    pipeline = build_pipeline(graph=graph)
    reports: list[dict[str, Any]] = []
    _emit_progress(
        progress_callback,
        stage="sample_analysis",
        event="stage_start",
        elapsed_seconds=round(time.perf_counter() - started, 3),
        sample_count=len(sample_paths),
        top_k=top_k,
    )
    for index, sample_path in enumerate(sample_paths, start=1):
        path = Path(sample_path)
        _emit_progress(
            progress_callback,
            stage="sample_analysis",
            event="sample_start",
            elapsed_seconds=round(time.perf_counter() - started, 3),
            item=f"{index}/{len(sample_paths)}:{path.as_posix()}",
        )
        evidence = load_evidence_json(path)
        result = pipeline.analyze(evidence, top_k=top_k)
        payload = result.model_dump(mode="json")
        reports.append(
            _sample_report(
                evidence_path=path,
                dataset=evidence.dataset,
                result=payload,
                graph=graph,
            )
        )
        _emit_progress(
            progress_callback,
            stage="sample_analysis",
            event="sample_finish",
            elapsed_seconds=round(time.perf_counter() - started, 3),
            item=f"{index}/{len(sample_paths)}:{path.as_posix()}",
            case_id=evidence.case_id,
            linked_count=len(payload.get("linked_entities") or []),
            top_path_count=len(payload.get("top_k_paths") or []),
        )
    if not reports:
        raise ValueError("at least one sample evidence path is required")
    _emit_progress(
        progress_callback,
        stage="sample_analysis",
        event="stage_finish",
        elapsed_seconds=round(time.perf_counter() - started, 3),
        sample_count=len(reports),
    )
    return reports


def _sample_report(
    *,
    evidence_path: Path,
    dataset: str,
    result: dict[str, Any],
    graph: KnowledgeGraph,
) -> dict[str, Any]:
    linked_entities = list(result.get("linked_entities") or [])
    selected_links = [
        link for link in linked_entities if isinstance(link.get("selected_entity_id"), str)
    ]
    paths = list(result.get("top_k_paths") or [])
    scenario_counts = _scenario_runtime_counts(graph, dataset)
    flags = _reasonableness_flags(
        selected_link_count=len(selected_links),
        path_count=len(paths),
        scenario_node_count=scenario_counts["nodes"],
        scenario_edge_count=scenario_counts["edges"],
        inconsistent_fields=list(result.get("inconsistent_fields") or []),
    )
    return {
        "path": evidence_path.as_posix(),
        "case_id": result.get("case_id"),
        "dataset": dataset,
        "strict_generated_only": True,
        "linked_entities": linked_entities,
        "linked_count": len(linked_entities),
        "selected_link_count": len(selected_links),
        "consistency_score": result.get("consistency_score"),
        "inconsistent_fields": list(result.get("inconsistent_fields") or []),
        "correction_candidate_count": len(result.get("correction_candidates") or []),
        "top_path_count": len(paths),
        "path_exists": bool(paths),
        "top_paths": [_path_summary(path) for path in paths[:3]],
        "ranked_root_cause_count": len(result.get("ranked_root_causes") or []),
        "coverage": scenario_counts,
        "reasonableness_flags": flags,
    }


def _evaluation_report(
    *,
    config: SourceKGCompilerEvaluationConfig,
    source_paths: tuple[Path, ...],
    compiler_summary: dict[str, Any],
    qa_report: dict[str, Any],
    validation_report: dict[str, Any],
    baseline_comparison: dict[str, Any],
    graph: KnowledgeGraph,
    sample_reports: list[dict[str, Any]],
    runtime_seconds: float,
    compiled_output_dir: Path,
) -> dict[str, Any]:
    validation_metrics = dict(validation_report.get("metrics") or {})
    domain_profile_counts = _domain_profile_counts(compiled_output_dir)
    sample_flag_counts = Counter(
        flag for sample in sample_reports for flag in sample["reasonableness_flags"]
    )
    return {
        "artifact_type": "source_kg_compiler_parity_real_sample_report_v1",
        "generated_at": _utc_now(),
        "config": {
            "materials_dir": config.materials_dir.expanduser().as_posix(),
            "source_paths": [Path(path).expanduser().as_posix() for path in source_paths],
            "baseline_output_dir": (
                config.baseline_output_dir.expanduser().as_posix()
                if config.baseline_output_dir is not None
                else None
            ),
            "sample_paths": [Path(path).as_posix() for path in config.sample_paths],
            "default_scenario": config.default_scenario,
            "chunk_size": config.chunk_size,
            "chunk_overlap": config.chunk_overlap,
            "top_k": config.top_k,
            "overwrite": config.overwrite,
            "source_limit": config.source_limit,
            "llm_concurrency": config.llm_concurrency,
        },
        "compiled_output_dir": compiled_output_dir.as_posix(),
        "summary": {
            "runtime_seconds": runtime_seconds,
            "compiler_runtime_seconds": validation_metrics.get("runtime_seconds"),
            "llm_calls": validation_metrics.get("llm_calls", 0),
            "llm_input_tokens": validation_metrics.get("llm_input_tokens", 0),
            "llm_output_tokens": validation_metrics.get("llm_output_tokens", 0),
            "llm_total_tokens": validation_metrics.get("llm_total_tokens", 0),
            "counts": {
                **dict(compiler_summary.get("counts") or {}),
                "loaded_nodes": len(graph.nodes),
                "loaded_edges": len(graph.edges),
                "domain_profiles": domain_profile_counts,
            },
            "qa_status": qa_report.get("status"),
            "validation_status": validation_report.get("status"),
            "baseline_status": baseline_comparison.get("status"),
            "sample_count": len(sample_reports),
            "sample_flag_counts": dict(sorted(sample_flag_counts.items())),
        },
        "compiler": {
            "summary": compiler_summary,
            "qa_report": qa_report,
            "validation_report": validation_report,
        },
        "baseline_comparison": baseline_comparison,
        "strict_runtime": {
            "strict_generated_only": True,
            "default_kg_layers_loaded": False,
            "tep_root_kgd_reasoner_enabled": True,
            "loaded_node_files": [compiled_output_dir.joinpath("nodes.csv").as_posix()],
            "loaded_edge_files": [compiled_output_dir.joinpath("edges.csv").as_posix()],
            "forbidden_default_layers": [
                *(path.as_posix() for path in DEFAULT_NODE_PATHS),
                *(path.as_posix() for path in DEFAULT_EDGE_PATHS),
            ],
            "node_count": len(graph.nodes),
            "edge_count": len(graph.edges),
            "scenario_counts": _graph_scenario_counts(graph),
        },
        "samples": sample_reports,
    }


def _artifact_inventory(output_dir: Path, *, generated: bool) -> dict[str, Any]:
    if not output_dir.exists():
        return {"available": False, "output_dir": output_dir.as_posix(), "artifacts": {}}
    artifacts: dict[str, Any] = {}
    names = {
        "knowledge_cards": "knowledge_cards.jsonl" if generated else "knowledge_cards.json",
        "entities": "entities.jsonl" if generated else "entities.json",
        "edges": "edges.jsonl" if generated else "edges.json",
        "nodes_csv": "nodes.csv",
        "edges_csv": "edges.csv",
    }
    for key, filename in names.items():
        path = output_dir / filename
        artifacts[key] = _artifact_summary(path, key=key)
    return {
        "available": any(item["exists"] for item in artifacts.values()),
        "output_dir": output_dir.as_posix(),
        "artifacts": artifacts,
        "counts": {
            key: value["count"] for key, value in artifacts.items() if value["exists"]
        },
        "ids": {
            key: value["ids"] for key, value in artifacts.items() if value["exists"]
        },
        "edge_signatures": {
            key: value["edge_signatures"]
            for key, value in artifacts.items()
            if value["exists"] and value["edge_signatures"]
        },
    }


def _artifact_summary(path: Path, *, key: str) -> dict[str, Any]:
    if not path.is_file():
        return {
            "exists": False,
            "path": path.as_posix(),
            "count": 0,
            "ids": [],
            "edge_signatures": [],
        }
    records = _read_records(path)
    ids = _record_ids(records, key=key)
    edge_signatures = _edge_signatures(records) if key in {"edges", "edges_csv"} else []
    return {
        "exists": True,
        "path": path.as_posix(),
        "count": len(records),
        "ids": ids,
        "edge_signatures": edge_signatures,
        "size_bytes": path.stat().st_size,
    }


def _read_records(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if path.suffix.lower() == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    payload = json.loads(text)
    if isinstance(payload, list):
        return [dict(item) for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("cards", "entities", "edges", "records"):
            value = payload.get(key)
            if isinstance(value, list):
                return [dict(item) for item in value if isinstance(item, dict)]
        return [payload]
    return []


def _record_ids(records: list[dict[str, Any]], *, key: str) -> list[str]:
    fields_by_key = {
        "knowledge_cards": ("card_id", "id"),
        "entities": ("entity_id", "id", "canonical_name", "name"),
        "nodes_csv": ("id", "entity_id", "canonical_name", "name"),
        "edges": ("edge_id", "id"),
        "edges_csv": ("edge_id", "id"),
    }
    fields = fields_by_key.get(key, ("id",))
    ids = []
    for record in records:
        for field in fields:
            value = str(record.get(field) or "").strip()
            if value:
                ids.append(value)
                break
    return sorted(set(ids))


def _edge_signatures(records: list[dict[str, Any]]) -> list[str]:
    signatures = []
    for record in records:
        head = str(record.get("head") or record.get("source") or "").strip()
        relation = str(record.get("relation") or "").strip()
        tail = str(record.get("tail") or record.get("target") or "").strip()
        scenario = str(record.get("scenario") or "").strip()
        if head and relation and tail:
            signatures.append("|".join((head, relation, tail, scenario)))
    return sorted(set(signatures))


def _comparison_metrics(generated: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    generated_counts = dict(generated.get("counts") or {})
    baseline_counts = dict(baseline.get("counts") or {})
    count_deltas = {
        key: int(generated_counts.get(key, 0)) - int(baseline_counts.get(key, 0))
        for key in sorted(set(generated_counts) | set(baseline_counts))
    }
    generated_ids = dict(generated.get("ids") or {})
    baseline_ids = dict(baseline.get("ids") or {})
    generated_edges = set()
    baseline_edges = set()
    for values in dict(generated.get("edge_signatures") or {}).values():
        generated_edges.update(values)
    for values in dict(baseline.get("edge_signatures") or {}).values():
        baseline_edges.update(values)
    return {
        "count_deltas": count_deltas,
        "entity_id_overlap": _overlap(
            set(generated_ids.get("entities") or generated_ids.get("nodes_csv") or []),
            set(baseline_ids.get("entities") or baseline_ids.get("nodes_csv") or []),
        ),
        "node_csv_id_overlap": _overlap(
            set(generated_ids.get("nodes_csv") or []),
            set(baseline_ids.get("nodes_csv") or []),
        ),
        "edge_signature_overlap": _overlap(generated_edges, baseline_edges),
    }


def _overlap(left: set[str], right: set[str]) -> dict[str, Any]:
    intersection = sorted(left & right)
    union_count = len(left | right)
    return {
        "generated_count": len(left),
        "baseline_count": len(right),
        "overlap_count": len(intersection),
        "jaccard": round(len(intersection) / union_count, 4) if union_count else 1.0,
        "sample": intersection[:20],
    }


def _domain_profile_counts(output_dir: Path) -> dict[str, int]:
    report_path = output_dir / "domain_profile_report.json"
    if not report_path.is_file():
        return {}
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    counts = payload.get("profile_counts") if isinstance(payload, dict) else {}
    if not isinstance(counts, dict):
        return {}
    return {str(key): int(value) for key, value in counts.items()}


def _scenario_runtime_counts(graph: KnowledgeGraph, scenario: str) -> dict[str, int]:
    nodes = [
        node_id
        for node_id, node in graph.nodes.items()
        if node.scenario in {scenario, "shared"}
    ]
    edges = [edge for edge in graph.edges if edge.scenario in {scenario, "shared"}]
    return {"nodes": len(nodes), "edges": len(edges)}


def _graph_scenario_counts(graph: KnowledgeGraph) -> dict[str, dict[str, int]]:
    return {
        "nodes": dict(sorted(Counter(node.scenario for node in graph.nodes.values()).items())),
        "edges": dict(sorted(Counter(edge.scenario for edge in graph.edges).items())),
    }


def _reasonableness_flags(
    *,
    selected_link_count: int,
    path_count: int,
    scenario_node_count: int,
    scenario_edge_count: int,
    inconsistent_fields: list[str],
) -> list[str]:
    flags: list[str] = []
    if scenario_node_count == 0:
        flags.append("no_generated_nodes_for_scenario")
    if scenario_edge_count == 0:
        flags.append("no_generated_edges_for_scenario")
    if selected_link_count == 0:
        flags.append("no_linked_entities")
    if selected_link_count < 2 or scenario_edge_count < 2:
        flags.append("low_coverage")
    if path_count == 0:
        flags.append("no_path")
    else:
        flags.append("path_found")
    if inconsistent_fields:
        flags.append("inconsistent_fields")
    return flags


def _path_summary(path: dict[str, Any]) -> dict[str, Any]:
    return {
        "path_id": path.get("path_id"),
        "source_entity_id": path.get("source_entity_id"),
        "target_entity_id": path.get("target_entity_id"),
        "score": path.get("score"),
        "confidence": path.get("confidence"),
        "path_strength": path.get("path_strength"),
        "nodes": list(path.get("nodes") or []),
        "node_names": list(path.get("node_names") or []),
        "relations": list(path.get("relations") or []),
        "source_edge_ids": list(path.get("source_edge_ids") or []),
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _emit_progress(
    progress_callback: SourceKGProgressCallback | None,
    **event: Any,
) -> None:
    if progress_callback is not None:
        progress_callback(event)
