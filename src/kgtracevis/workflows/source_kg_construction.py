"""Reusable workflow for source-to-KG construction builds."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha1
from pathlib import Path
from typing import Any, Literal

from kgtracevis.kg_construction import (
    ExtractorRegistry,
    KGConstructionManifest,
    KGConstructionReviewDecision,
    KGConstructionSource,
    MVTecCatalogExtractor,
    OfflineDocumentIEExtractor,
    RcaProfile,
    StructuredRecordExtractor,
    TepRcaGraphExtractor,
    TepSemanticLiftExtractor,
    TepVariableMappingExtractor,
    load_rca_profile,
    run_kg_construction,
    source_library_records_from_construction_sources,
    write_source_library_manifest,
)
from kgtracevis.kg_construction.artifact_diff import (
    build_kg_construction_artifact_snapshot,
    build_noop_kg_construction_diff,
    write_kg_construction_diff,
)
from kgtracevis.kg_construction.document_extraction import ALLOWED_DOCUMENT_IE_RELATIONS
from kgtracevis.kg_construction.models import (
    construction_output_path_payload,
    kg_construction_artifact_paths,
)
from kgtracevis.kg_construction.publish import (
    build_publish_snapshot,
    write_publish_snapshot,
)
from kgtracevis.kg_construction.review_queue import ReviewQueueItem, review_queue_payload

DEFAULT_SOURCE_KG_BUILD_DIR = Path("runs/source_kg_build")
SOURCE_TEXT_FORMATS = ("csv", "json", "jsonl", "txt", "md", "html")
SourceTextFormat = Literal["csv", "json", "jsonl", "txt", "md", "html"]
DOCUMENT_TEXT_SOURCE_TYPES = {"document", "markdown", "txt", "html", "web_snapshot"}


@dataclass(frozen=True)
class SourceKGConstructionWorkflowConfig:
    """Configuration for one source-to-KG construction build."""

    output_dir: Path
    sources: tuple[KGConstructionSource, ...]
    overwrite: bool = False
    run_id: str | None = None
    profile: RcaProfile | None = None
    profile_path: Path | None = None
    allow_reviewed_overwrite: bool = False
    review_decisions: tuple[KGConstructionReviewDecision, ...] = ()


@dataclass(frozen=True)
class SourceKGConstructionWorkflowResult:
    """Artifact envelope returned by the source-to-KG construction workflow."""

    run_id: str
    output_dir: Path
    nodes_path: Path
    edges_path: Path
    published_nodes_path: Path
    published_edges_path: Path
    summary_path: Path
    manifest_path: Path
    source_library_manifest_path: Path
    draft_manifest_path: Path
    profile_manifest_path: Path
    alignment_manifest_path: Path
    source_audit_graph_manifest_path: Path
    semantic_layer_manifest_path: Path
    rca_view_manifest_path: Path
    review_queue_path: Path
    document_understanding_manifest_path: Path
    document_map_path: Path
    chunk_prompt_context_path: Path
    cross_chunk_proposals_path: Path
    hypothesis_brainstorming_manifest_path: Path
    brainstorm_hypotheses_path: Path
    brainstorm_review_items_path: Path
    alignment_suggestions_path: Path
    semantic_layer_suggestions_path: Path
    profile_gap_suggestions_path: Path
    publish_manifest_path: Path
    publish_report_path: Path
    diff_path: Path
    summary: dict[str, object]
    manifest: KGConstructionManifest


def run_source_kg_construction_workflow(
    config: SourceKGConstructionWorkflowConfig,
    *,
    registry: ExtractorRegistry | None = None,
) -> SourceKGConstructionWorkflowResult:
    """Run source-constrained KG construction and write candidate artifacts."""
    if not config.sources:
        raise ValueError("at least one KG construction source is required")

    _ensure_output_dir(config.output_dir, overwrite=config.overwrite)
    sources = tuple(
        _materialize_text_source(source, config.output_dir) for source in config.sources
    )
    profile = _resolve_profile(config)
    result = run_kg_construction(
        sources,
        registry=registry or _runtime_extractor_registry(),
        allow_reviewed_overwrite=config.allow_reviewed_overwrite,
        run_id=config.run_id,
        profile=profile,
        review_decisions=config.review_decisions,
    )
    artifact_paths = kg_construction_artifact_paths(config.output_dir)
    source_library_manifest_path = write_source_library_manifest(
        artifact_paths["source_library_manifest"],
        source_library_records_from_construction_sources(sources),
    )
    nodes_path, edges_path = result.export_csv(config.output_dir)
    layer_artifacts = result.write_layer_artifacts(config.output_dir)
    artifact_paths["review_decisions"].parent.mkdir(parents=True, exist_ok=True)
    _write_review_decisions(artifact_paths["review_decisions"], config.review_decisions)
    publish_snapshot = build_publish_snapshot(
        kg_build_id=result.run_id,
        nodes=result.nodes,
        edges=result.edges,
        review_decisions=config.review_decisions,
    )
    published_nodes_path, published_edges_path, publish_report_path = write_publish_snapshot(
        publish_snapshot,
        nodes_path=artifact_paths["published_nodes"],
        edges_path=artifact_paths["published_edges"],
        report_path=artifact_paths["publish_report"],
    )
    artifact_paths.update(
        {
            "nodes": nodes_path,
            "edges": edges_path,
            "published_nodes": published_nodes_path,
            "published_edges": published_edges_path,
            "publish_report": publish_report_path,
            **layer_artifacts,
        }
    )
    document_understanding_artifacts = _write_document_understanding_artifacts(
        sources=sources,
        run_id=result.run_id,
        artifact_paths=artifact_paths,
        review_queue_path=layer_artifacts["review_queue"],
    )
    artifact_paths.update(document_understanding_artifacts)
    advisory_artifacts = _write_advisory_llm_artifacts(
        sources=sources,
        run_id=result.run_id,
        artifact_paths=artifact_paths,
        review_queue_path=layer_artifacts["review_queue"],
    )
    artifact_paths.update(advisory_artifacts)
    summary_path = artifact_paths["summary"]
    manifest_path = artifact_paths["manifest"]
    summary = {
        **result.summary,
        "kg_build_id": result.publish_manifest.kg_build_id,
        "source_ids": list(result.publish_manifest.source_ids),
        "extractor_versions": dict(result.publish_manifest.extractor_versions),
        "profile_version": result.publish_manifest.profile_version,
        "review_policy": result.publish_manifest.review_policy,
        "claim_boundary": (
            "source-to-KG outputs are candidate/reviewable KG rows; they are not "
            "published to Neo4j automatically"
        ),
        "output": construction_output_path_payload(
            output_dir=config.output_dir,
            artifact_paths=artifact_paths,
        ),
        "layer_manifests": {
            "draft": result.draft_manifest(),
            "profile": result.profile_manifest(),
            "alignment": result.alignment.manifest(),
            "source_audit_graph": result.audit_graph.manifest(),
            "semantic_layer": result.semantic_layer.manifest,
            "rca_view": result.rca_view.manifest,
            "hypothesis_brainstorming": json.loads(
                artifact_paths["hypothesis_brainstorming_manifest"].read_text(
                    encoding="utf-8"
                )
            ),
            "profile_gap_suggestions": json.loads(
                artifact_paths["profile_gap_suggestions"].read_text(encoding="utf-8")
            ),
            "publish": result.publish_manifest.model_dump(),
            "source_library": json.loads(
                source_library_manifest_path.read_text(encoding="utf-8")
            ),
        },
    }
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    artifact_paths["output_dir"] = config.output_dir
    manifest = result.manifest(
        artifact_paths=artifact_paths,
        review_decisions=config.review_decisions,
    )
    manifest_path.write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    diff_path = write_kg_construction_diff(
        artifact_paths["kg_construction_diff"],
        build_noop_kg_construction_diff(
            run_id=result.run_id,
            snapshot=build_kg_construction_artifact_snapshot(config.output_dir),
        ),
    )
    return SourceKGConstructionWorkflowResult(
        run_id=result.run_id,
        output_dir=config.output_dir,
        nodes_path=nodes_path,
        edges_path=edges_path,
        published_nodes_path=published_nodes_path,
        published_edges_path=published_edges_path,
        summary_path=summary_path,
        manifest_path=manifest_path,
        source_library_manifest_path=source_library_manifest_path,
        draft_manifest_path=layer_artifacts["draft_manifest"],
        profile_manifest_path=layer_artifacts["profile_manifest"],
        alignment_manifest_path=layer_artifacts["alignment_manifest"],
        source_audit_graph_manifest_path=layer_artifacts["source_audit_graph_manifest"],
        semantic_layer_manifest_path=layer_artifacts["semantic_layer_manifest"],
        rca_view_manifest_path=layer_artifacts["rca_view_manifest"],
        review_queue_path=layer_artifacts["review_queue"],
        document_understanding_manifest_path=artifact_paths["document_understanding_manifest"],
        document_map_path=artifact_paths["document_map"],
        chunk_prompt_context_path=artifact_paths["chunk_prompt_context"],
        cross_chunk_proposals_path=artifact_paths["cross_chunk_proposals"],
        hypothesis_brainstorming_manifest_path=artifact_paths[
            "hypothesis_brainstorming_manifest"
        ],
        brainstorm_hypotheses_path=artifact_paths["brainstorm_hypotheses"],
        brainstorm_review_items_path=artifact_paths["brainstorm_review_items"],
        alignment_suggestions_path=artifact_paths["alignment_suggestions"],
        semantic_layer_suggestions_path=artifact_paths["semantic_layer_suggestions"],
        profile_gap_suggestions_path=artifact_paths["profile_gap_suggestions"],
        publish_manifest_path=layer_artifacts["publish_manifest"],
        publish_report_path=publish_report_path,
        diff_path=diff_path,
        summary=summary,
        manifest=manifest,
    )


def _write_document_understanding_artifacts(
    *,
    sources: tuple[KGConstructionSource, ...],
    run_id: str,
    artifact_paths: dict[str, Path],
    review_queue_path: Path,
) -> dict[str, Path]:
    document_maps = _load_document_maps(sources)
    prompt_context_rows = _load_prompt_context_rows(sources)
    proposal_records, review_items = _cross_chunk_proposal_records(
        document_maps=document_maps,
        run_id=run_id,
    )
    manifest = {
        "artifact_type": "document_understanding_manifest_v1",
        "run_id": run_id,
        "source_ids": [source.source_id for source in sources],
        "document_map_count": len(document_maps),
        "prompt_context_record_count": len(prompt_context_rows),
        "cross_chunk_proposal_count": len(proposal_records),
        "review_required_count": sum(
            1 for record in proposal_records if record["validation_status"] == "review_required"
        ),
        "rejected_count": sum(
            1 for record in proposal_records if record["validation_status"] == "rejected"
        ),
        "claim_boundary": (
            "Document understanding artifacts are advisory review inputs. They "
            "do not create published KG edges without explicit review."
        ),
    }
    document_map_payload = {
        "artifact_type": "document_map_collection_v1",
        "run_id": run_id,
        "map_count": len(document_maps),
        "maps": document_maps,
        "claim_boundary": manifest["claim_boundary"],
    }
    _write_json_object(artifact_paths["document_understanding_manifest"], manifest)
    _write_json_object(artifact_paths["document_map"], document_map_payload)
    _write_jsonl(artifact_paths["chunk_prompt_context"], prompt_context_rows)
    _write_jsonl(artifact_paths["cross_chunk_proposals"], proposal_records)
    if review_items:
        existing_queue = json.loads(review_queue_path.read_text(encoding="utf-8"))
        if not isinstance(existing_queue, list):
            raise ValueError(f"review queue artifact must be a JSON array: {review_queue_path}")
        existing_queue.extend(review_queue_payload(tuple(review_items)))
        existing_queue = sorted(
            existing_queue,
            key=lambda item: (
                -int(item.get("priority", 0)) if isinstance(item, Mapping) else 0,
                str(item.get("target_key", "")) if isinstance(item, Mapping) else "",
            ),
        )
        _write_json_list(review_queue_path, existing_queue)
    return {
        "document_understanding_manifest": artifact_paths["document_understanding_manifest"],
        "document_map": artifact_paths["document_map"],
        "chunk_prompt_context": artifact_paths["chunk_prompt_context"],
        "cross_chunk_proposals": artifact_paths["cross_chunk_proposals"],
    }


def _write_advisory_llm_artifacts(
    *,
    sources: tuple[KGConstructionSource, ...],
    run_id: str,
    artifact_paths: dict[str, Path],
    review_queue_path: Path,
) -> dict[str, Path]:
    hypotheses = _load_jsonl_metadata_rows(sources, "brainstorm_hypotheses_path")
    evidence_tasks = _load_jsonl_metadata_rows(sources, "brainstorm_evidence_tasks_path")
    alignment_suggestions = _load_jsonl_metadata_rows(sources, "alignment_suggestions_path")
    semantic_suggestions = _load_jsonl_metadata_rows(
        sources,
        "semantic_layer_suggestions_path",
    )
    profile_gaps = _load_profile_gap_suggestions(sources)
    review_items = _load_brainstorm_review_items(sources)
    manifests = _load_json_metadata_objects(
        sources,
        "hypothesis_brainstorming_manifest_path",
    )
    aggregate_manifest = {
        "artifact_type": "hypothesis_brainstorming_manifest_v1",
        "run_id": run_id,
        "source_ids": [source.source_id for source in sources],
        "source_manifest_count": len(manifests),
        "mode_counts": _count_field(manifests, "mode"),
        "provider_counts": _count_field(manifests, "provider"),
        "influence_counts": _count_field(manifests, "influence"),
        "hypothesis_count": len(hypotheses),
        "evidence_task_count": len(evidence_tasks),
        "profile_gap_count": len(profile_gaps),
        "alignment_suggestion_count": len(alignment_suggestions),
        "semantic_layer_suggestion_count": len(semantic_suggestions),
        "review_item_count": len(review_items),
        "source_manifests": manifests,
        "claim_boundary": (
            "LLM-assisted brainstorming, alignment, and semantic suggestions "
            "are advisory review inputs. They do not mutate KG files unless a "
            "review workflow explicitly accepts an eligible item."
        ),
    }
    _write_jsonl(artifact_paths["brainstorm_hypotheses"], hypotheses)
    _write_jsonl(artifact_paths["brainstorm_evidence_tasks"], evidence_tasks)
    _write_json_object(
        artifact_paths["brainstorm_profile_gaps"],
        {
            "artifact_type": "brainstorm_profile_gaps_v1",
            "run_id": run_id,
            "profile_gaps": profile_gaps,
        },
    )
    _write_json_list(artifact_paths["brainstorm_review_items"], review_items)
    _write_json_object(
        artifact_paths["hypothesis_brainstorming_manifest"],
        aggregate_manifest,
    )
    _write_jsonl(artifact_paths["alignment_suggestions"], alignment_suggestions)
    _write_jsonl(artifact_paths["semantic_layer_suggestions"], semantic_suggestions)
    _write_json_object(
        artifact_paths["profile_gap_suggestions"],
        {
            "artifact_type": "profile_gap_suggestions_v1",
            "run_id": run_id,
            "profile_gaps": profile_gaps,
            "claim_boundary": "profile gaps are recorded but do not mutate profiles",
        },
    )
    for key, artifact_type in (
        ("accepted_alignment_overrides", "accepted_alignment_overrides_v1"),
        ("accepted_profile_gaps", "accepted_profile_gaps_v1"),
        ("accepted_hypotheses", "accepted_hypotheses_v1"),
        ("accepted_evidence_tasks", "accepted_evidence_tasks_v1"),
    ):
        _write_json_object(
            artifact_paths[key],
            {"artifact_type": artifact_type, "run_id": run_id, "items": []},
        )
    if review_items:
        existing_queue = json.loads(review_queue_path.read_text(encoding="utf-8"))
        if not isinstance(existing_queue, list):
            raise ValueError(f"review queue artifact must be a JSON array: {review_queue_path}")
        existing_queue.extend(review_items)
        existing_queue = sorted(
            existing_queue,
            key=lambda item: (
                -int(item.get("priority", 0)) if isinstance(item, Mapping) else 0,
                str(item.get("target_key", "")) if isinstance(item, Mapping) else "",
            ),
        )
        _write_json_list(review_queue_path, existing_queue)
    return {
        "brainstorm_hypotheses": artifact_paths["brainstorm_hypotheses"],
        "brainstorm_evidence_tasks": artifact_paths["brainstorm_evidence_tasks"],
        "brainstorm_profile_gaps": artifact_paths["brainstorm_profile_gaps"],
        "brainstorm_review_items": artifact_paths["brainstorm_review_items"],
        "hypothesis_brainstorming_manifest": artifact_paths[
            "hypothesis_brainstorming_manifest"
        ],
        "alignment_suggestions": artifact_paths["alignment_suggestions"],
        "semantic_layer_suggestions": artifact_paths["semantic_layer_suggestions"],
        "profile_gap_suggestions": artifact_paths["profile_gap_suggestions"],
        "accepted_alignment_overrides": artifact_paths["accepted_alignment_overrides"],
        "accepted_profile_gaps": artifact_paths["accepted_profile_gaps"],
        "accepted_hypotheses": artifact_paths["accepted_hypotheses"],
        "accepted_evidence_tasks": artifact_paths["accepted_evidence_tasks"],
    }


def _load_document_maps(sources: tuple[KGConstructionSource, ...]) -> list[dict[str, Any]]:
    maps: list[dict[str, Any]] = []
    for source in sources:
        path = _metadata_path(source.metadata, "document_understanding_map_path")
        if path is None:
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"document understanding map must be a JSON object: {path}")
        maps.append(
            {
                **payload,
                "source_id": str(payload.get("source_id") or source.source_id),
                "source_metadata_path": str(path),
            }
        )
    return maps


def _load_prompt_context_rows(sources: tuple[KGConstructionSource, ...]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source in sources:
        path = _metadata_path(source.metadata, "chunk_prompt_context_path")
        if path is None:
            continue
        rows.extend(_read_jsonl_objects(path))
    return rows


def _cross_chunk_proposal_records(
    *,
    document_maps: list[dict[str, Any]],
    run_id: str,
) -> tuple[list[dict[str, Any]], list[ReviewQueueItem]]:
    records: list[dict[str, Any]] = []
    review_items: list[ReviewQueueItem] = []
    for document_map in document_maps:
        source_id = str(document_map.get("source_id") or "document_understanding")
        scenario = str(document_map.get("scenario") or "shared").strip() or "shared"
        proposals = document_map.get("cross_chunk_proposals", [])
        if not isinstance(proposals, list):
            raise ValueError(f"cross_chunk_proposals must be a list for source {source_id}")
        for index, proposal in enumerate(proposals, start=1):
            if not isinstance(proposal, Mapping):
                raise ValueError(f"cross_chunk proposal must be an object for source {source_id}")
            record = _cross_chunk_proposal_record(
                proposal,
                source_id=source_id,
                scenario=scenario,
                index=index,
                run_id=run_id,
            )
            records.append(record)
            if record["validation_status"] == "review_required":
                review_items.append(_cross_chunk_review_item(record))
    return records, review_items


def _cross_chunk_proposal_record(
    proposal: Mapping[str, Any],
    *,
    source_id: str,
    scenario: str,
    index: int,
    run_id: str,
) -> dict[str, Any]:
    head = _proposal_text(proposal, "head")
    relation = _proposal_text(proposal, "relation").upper()
    tail = _proposal_text(proposal, "tail")
    spans = _proposal_spans(proposal.get("supporting_spans"))
    confidence = _proposal_confidence(proposal.get("confidence"))
    proposal_id = _cross_chunk_proposal_id(
        source_id=source_id,
        index=index,
        head=head,
        relation=relation,
        tail=tail,
        spans=spans,
    )
    errors: list[str] = []
    if not head:
        errors.append("missing head")
    if relation not in ALLOWED_DOCUMENT_IE_RELATIONS:
        errors.append("relation is not allowed for document IE")
    if not tail:
        errors.append("missing tail")
    if len(spans) < 2:
        errors.append("cross-chunk proposal requires at least two supporting spans")
    validation_status = "rejected" if errors else "review_required"
    record = {
        "proposal_id": proposal_id,
        "run_id": run_id,
        "source_id": source_id,
        "scenario": scenario,
        "head": head,
        "relation": relation,
        "tail": tail,
        "supporting_spans": spans,
        "confidence": min(confidence, 0.6),
        "relation_family": _proposal_text(proposal, "relation_family") or relation,
        "proposal_type": "derived/cross_chunk",
        "validation_status": validation_status,
        "validation_errors": errors,
        "review_status": "auto" if validation_status == "review_required" else "rejected",
        "why_hint_only": (
            str(proposal.get("why_hint_only") or proposal.get("reason") or "").strip()
            or "relation combines document-level evidence across multiple spans"
        ),
    }
    for policy_key in ("review_acceptance_policy", "rca_policy"):
        policy_value = proposal.get(policy_key)
        if isinstance(policy_value, Mapping):
            record[policy_key] = dict(policy_value)
    return record


def _cross_chunk_review_item(record: Mapping[str, Any]) -> ReviewQueueItem:
    target_key = f"cross_chunk_relation_candidate:{record['proposal_id']}"
    evidence = "; ".join(
        str(span.get("text") or span.get("evidence") or span.get("span_id") or "")
        for span in record["supporting_spans"]
        if isinstance(span, Mapping)
    ).strip()
    return ReviewQueueItem(
        target_key=target_key,
        item_type="cross_chunk_relation_candidate",
        priority=96,
        reason="cross-chunk relation candidate requires human review before KG use",
        candidate_payload=dict(record),
        source=str(record["source_id"]),
        evidence=evidence or str(record["why_hint_only"]),
        confidence=_proposal_confidence(record.get("confidence")),
        review_status="auto",
        scenario=str(record.get("scenario") or "shared"),
        relation_family=str(record["relation_family"]),
        graph_impact="can introduce RCA traversal relation after explicit review",
        recommended_action="verify_all_spans_then_accept_or_reject",
    )


def _load_jsonl_metadata_rows(
    sources: tuple[KGConstructionSource, ...],
    metadata_key: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source in sources:
        path = _metadata_path(source.metadata, metadata_key)
        if path is None:
            continue
        for row in _read_jsonl_objects(path):
            row.setdefault("source_id", source.source_id)
            row["source_metadata_path"] = str(path)
            rows.append(row)
    return rows


def _load_json_metadata_objects(
    sources: tuple[KGConstructionSource, ...],
    metadata_key: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source in sources:
        path = _metadata_path(source.metadata, metadata_key)
        if path is None:
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"{metadata_key} artifact must be a JSON object: {path}")
        payload.setdefault("source_id", source.source_id)
        payload["source_metadata_path"] = str(path)
        rows.append(payload)
    return rows


def _load_profile_gap_suggestions(
    sources: tuple[KGConstructionSource, ...],
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for source in sources:
        path = _metadata_path(source.metadata, "profile_gap_suggestions_path")
        if path is None:
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"profile gap suggestions must be a JSON object: {path}")
        records = payload.get("profile_gaps", [])
        if not isinstance(records, list):
            raise ValueError(f"profile_gaps must be a list: {path}")
        for record in records:
            if not isinstance(record, dict):
                continue
            record.setdefault("source_id", source.source_id)
            record["source_metadata_path"] = str(path)
            gaps.append(record)
    return gaps


def _load_brainstorm_review_items(
    sources: tuple[KGConstructionSource, ...],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for source in sources:
        path = _metadata_path(source.metadata, "brainstorm_review_items_path")
        if path is None:
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            rows = payload.get("items", [])
        else:
            rows = payload
        if not isinstance(rows, list):
            raise ValueError(f"brainstorm review items must be a JSON array/list: {path}")
        for row in rows:
            if not isinstance(row, dict):
                continue
            row.setdefault("source", source.source_id)
            row["source_metadata_path"] = str(path)
            items.append(row)
    return items


def _count_field(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _metadata_path(metadata: Mapping[str, Any], key: str) -> Path | None:
    value = metadata.get(key)
    if not value:
        return None
    path = Path(str(value))
    if not path.is_file():
        raise ValueError(f"{key} does not exist: {path}")
    return path


def _proposal_text(proposal: Mapping[str, Any], key: str) -> str:
    value = proposal.get(key)
    return str(value).strip() if value is not None else ""


def _proposal_spans(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    spans: list[dict[str, Any]] = []
    for index, span in enumerate(value, start=1):
        if isinstance(span, Mapping):
            payload = {str(key): str(item) for key, item in span.items() if item is not None}
        elif span is not None:
            payload = {"span_id": str(span)}
        else:
            continue
        if payload:
            payload.setdefault("span_id", f"span:{index}")
            spans.append(payload)
    return spans


def _proposal_confidence(value: object) -> float:
    if not isinstance(value, (int, float, str)):
        return 0.45
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = 0.45
    return max(0.0, min(1.0, confidence))


def _cross_chunk_proposal_id(
    *,
    source_id: str,
    index: int,
    head: str,
    relation: str,
    tail: str,
    spans: list[dict[str, Any]],
) -> str:
    payload = json.dumps(
        {
            "source_id": source_id,
            "index": index,
            "head": head,
            "relation": relation,
            "tail": tail,
            "spans": spans,
        },
        sort_keys=True,
    )
    return f"ccp_{sha1(payload.encode('utf-8')).hexdigest()[:12]}"


def _read_jsonl_objects(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"JSONL row must be an object: {path}:{line_number}")
        rows.append(payload)
    return rows


def _write_json_object(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_json_list(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    path.write_text(
        "".join(json.dumps(dict(row), sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _runtime_extractor_registry() -> ExtractorRegistry:
    return ExtractorRegistry(
        [
            StructuredRecordExtractor(),
            MVTecCatalogExtractor(),
            OfflineDocumentIEExtractor(),
            TepSemanticLiftExtractor(),
            TepVariableMappingExtractor(),
            TepRcaGraphExtractor(),
        ]
    )


def _resolve_profile(config: SourceKGConstructionWorkflowConfig) -> RcaProfile | None:
    if config.profile is not None and config.profile_path is not None:
        raise ValueError("pass either profile or profile_path, not both")
    if config.profile_path is None:
        return config.profile
    return load_rca_profile(config.profile_path)


def _write_review_decisions(
    path: Path,
    decisions: tuple[KGConstructionReviewDecision, ...],
) -> None:
    if not decisions:
        path.touch(exist_ok=True)
        return
    path.write_text(
        "".join(
            json.dumps(decision.model_dump(mode="json"), sort_keys=True) + "\n"
            for decision in decisions
        ),
        encoding="utf-8",
    )


def _ensure_output_dir(output_dir: Path, *, overwrite: bool) -> None:
    outputs = list(kg_construction_artifact_paths(output_dir).values())
    existing = [path for path in outputs if path.exists()]
    if existing and not overwrite:
        paths = ", ".join(str(path) for path in existing)
        raise ValueError(f"output files already exist; pass overwrite=true to replace: {paths}")
    output_dir.mkdir(parents=True, exist_ok=True)


def _materialize_text_source(
    source: KGConstructionSource,
    output_dir: Path,
) -> KGConstructionSource:
    if source.text is None:
        return source
    if source.path is not None:
        raise ValueError(f"{source.source_id} cannot set both path and source text")
    source_types_with_inline_text = {
        "structured_records",
        "manual_table",
        "mvtec_ad_catalog",
        *DOCUMENT_TEXT_SOURCE_TYPES,
    }
    if source.source_type not in source_types_with_inline_text:
        raise ValueError(
            f"source text is only supported for structured_records/manual_table/document: "
            f"{source.source_id}"
        )
    default_format = "jsonl"
    if source.source_type in DOCUMENT_TEXT_SOURCE_TYPES:
        default_format = "html" if source.source_type == "html" else "txt"
    source_format = str(source.metadata.get("source_format") or default_format).lower()
    if source_format not in SOURCE_TEXT_FORMATS:
        supported = ", ".join(SOURCE_TEXT_FORMATS)
        raise ValueError(f"unsupported source_format={source_format!r}; expected {supported}")

    source_dir = output_dir / "_sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    source_path = source_dir / f"{_safe_filename(source.source_id)}.{source_format}"
    source_path.write_text(source.text, encoding="utf-8")
    metadata = dict(source.metadata)
    metadata["materialized_source_text_path"] = source_path
    return KGConstructionSource(
        source_id=source.source_id,
        source_type=source.source_type,
        scenario=source.scenario,
        path=source_path,
        metadata=metadata,
    )


def _safe_filename(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip()).strip("._")
    return slug or "source"
