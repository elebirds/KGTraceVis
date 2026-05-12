"""Coverage-first KG hardening helpers for paper case artifacts."""

from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kgtracevis.experiments.adapter_pipeline import (
    AdapterPipelineOutput,
    run_adapter_pipeline,
)
from kgtracevis.kg.graph import (
    DEFAULT_EDGE_PATHS,
    DEFAULT_NODE_PATHS,
    KGEdge,
    KGNode,
    KnowledgeGraph,
)
from kgtracevis.kg_construction.confidence_assigner import edge_weight
from kgtracevis.kg_construction.export_kg_csv import export_edges_csv, export_nodes_csv
from kgtracevis.kg_construction.qa import run_kg_qa
from kgtracevis.schema.evidence_schema import DatasetName

CLAIM_BOUNDARY = "candidate/plausible explanation only; not a verified root-cause label"
FORBIDDEN_VERIFIED_RCA_TEXT = (
    "verified root cause",
    "verified rca",
    "true root cause",
    "factory root cause",
    "ground truth root cause",
)

CASE_RANKING_COLUMNS = (
    "case_id",
    "dataset",
    "object",
    "defect_type",
    "score",
    "confidence",
    "pred_label",
    "mask_area_ratio",
    "morphology",
    "location",
    "linked_entity_count",
    "correction_candidate_count",
    "path_count",
    "top_target_entity_id",
    "top_target_name",
    "top_target_label",
    "kg_path_specific",
    "evidence_clean",
    "explainability_score",
    "notes",
)

BEFORE_AFTER_COLUMNS = (
    "dataset",
    "case_id",
    "anomaly_type",
    "base_linked_entity_count",
    "overlay_linked_entity_count",
    "linked_entity_delta",
    "base_path_count",
    "overlay_path_count",
    "path_count_delta",
    "base_top_target_entity_id",
    "overlay_top_target_entity_id",
    "base_consistency_score",
    "overlay_consistency_score",
    "claim_boundary",
)


@dataclass(frozen=True)
class CaseAuditRow:
    """One coverage-aware case ranking row."""

    case_id: str
    dataset: str
    object: str
    defect_type: str
    score: float | None
    confidence: float | None
    pred_label: str
    mask_area_ratio: float | None
    morphology: str
    location: str
    linked_entity_count: int
    correction_candidate_count: int
    path_count: int
    top_target_entity_id: str
    top_target_name: str
    top_target_label: str
    kg_path_specific: bool
    evidence_clean: bool
    explainability_score: float
    notes: str

    def model_dump(self) -> dict[str, Any]:
        """Return a CSV/JSON-serializable row."""
        return {
            "case_id": self.case_id,
            "dataset": self.dataset,
            "object": self.object,
            "defect_type": self.defect_type,
            "score": "" if self.score is None else round(self.score, 6),
            "confidence": "" if self.confidence is None else round(self.confidence, 6),
            "pred_label": self.pred_label,
            "mask_area_ratio": ""
            if self.mask_area_ratio is None
            else round(self.mask_area_ratio, 6),
            "morphology": self.morphology,
            "location": self.location,
            "linked_entity_count": self.linked_entity_count,
            "correction_candidate_count": self.correction_candidate_count,
            "path_count": self.path_count,
            "top_target_entity_id": self.top_target_entity_id,
            "top_target_name": self.top_target_name,
            "top_target_label": self.top_target_label,
            "kg_path_specific": self.kg_path_specific,
            "evidence_clean": self.evidence_clean,
            "explainability_score": round(self.explainability_score, 4),
            "notes": self.notes,
        }


@dataclass(frozen=True)
class CandidateKGOutput:
    """Candidate KG rows and generated reports."""

    nodes_path: Path
    edges_path: Path
    summary_path: Path
    validation_path: Path
    before_after_path: Path
    explanations_path: Path
    node_count: int
    edge_count: int
    validation_passed: bool


@dataclass(frozen=True)
class WaferPatternSpec:
    """Controlled vocabulary for one WM811K pattern."""

    pattern: str
    node_id: str
    aliases: tuple[str, ...]
    location_id: str
    location_name: str
    location_aliases: tuple[str, ...]
    morphology_id: str
    morphology_name: str
    morphology_aliases: tuple[str, ...]
    mechanism_ids: tuple[str, ...]


MORPHOLOGY_NODES: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "linear": ("LinearMorphology", "Linear morphology", ("linear", "line", "line-shaped")),
    "spot": ("SpotMorphology", "Spot morphology", ("spot", "localized spot")),
    "scattered": ("ScatteredMorphology", "Scattered morphology", ("scattered", "diffuse")),
    "ring": ("RingMorphology", "Ring morphology", ("ring", "annular")),
    "clustered": ("ClusteredMorphology", "Clustered morphology", ("clustered", "cluster")),
    "dense_particles": (
        "DenseParticles",
        "Dense particles",
        ("dense_particles", "dense particles"),
    ),
}

LOCATION_NODES: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "surface": ("SurfaceLocation", "Surface location", ("surface", "outer surface")),
    "edge": ("EdgeLocation", "Edge location", ("edge", "border")),
    "center": ("CenterLocation", "Center location", ("center", "centre")),
    "local": ("LocalLocation", "Local location", ("local", "localized")),
    "wafer_surface": ("WaferSurface", "Wafer surface", ("wafer_surface", "wafer surface")),
}

MECHANISM_NODES: dict[str, tuple[str, str, str, tuple[str, ...]]] = {
    "MechanicalContact": (
        "Mechanical contact",
        "RootCause",
        "Plausible contact-related candidate mechanism",
        ("mechanical contact", "contact damage"),
    ),
    "HandlingDamage": (
        "Handling damage",
        "CauseCategory",
        "Plausible handling or transport damage category",
        ("handling", "handling damage"),
    ),
    "AssemblyError": (
        "Assembly error",
        "RootCause",
        "Plausible assembly or placement issue",
        ("assembly error", "misassembly"),
    ),
    "MaterialDefect": (
        "Material defect",
        "RootCause",
        "Plausible material-quality candidate mechanism",
        ("material defect", "material issue"),
    ),
    "ContaminationCause": (
        "Contamination cause",
        "RootCause",
        "Plausible foreign material or residue candidate",
        ("contamination source", "foreign material"),
    ),
    "MissingComponent": (
        "Missing component",
        "RootCause",
        "Plausible missing-part candidate mechanism",
        ("missing component", "missing part"),
    ),
    "SurfaceWear": (
        "Surface wear",
        "RootCause",
        "Plausible wear or abrasion candidate mechanism",
        ("surface wear", "abrasion", "wear"),
    ),
    "ProcessMisalignment": (
        "Process misalignment",
        "RootCause",
        "Plausible fixture or process alignment candidate",
        ("misalignment", "positioning issue"),
    ),
    "PackagingPressure": (
        "Packaging pressure",
        "RootCause",
        "Plausible compression or packaging pressure candidate",
        ("packaging pressure", "compression pressure"),
    ),
    "AdhesiveOrResidueCandidate": (
        "Adhesive or residue candidate",
        "RootCause",
        "Low-confidence candidate for glue, residue, or surface deposit evidence",
        ("adhesive residue", "glue residue", "residue candidate"),
    ),
    "TextureIrregularityCandidate": (
        "Texture irregularity candidate",
        "RootCause",
        "Low-confidence candidate for texture/thread-like visual irregularities",
        ("texture irregularity", "thread irregularity"),
    ),
    "ComponentDamageCandidate": (
        "Component damage candidate",
        "RootCause",
        "Low-confidence candidate for damaged component evidence",
        ("component damage", "damaged part"),
    ),
    "GenericVisualDefectMechanism": (
        "Generic visual defect mechanism",
        "CauseCategory",
        "Low-confidence fallback candidate for broad visual anomaly labels",
        ("generic visual mechanism", "visual defect mechanism"),
    ),
    "VisualInspectionReviewNeeded": (
        "Visual inspection review needed",
        "CauseCategory",
        "Review bucket for weak or ambiguous visual anomaly evidence",
        ("review needed", "visual review"),
    ),
    "ProcessNonuniformity": (
        "Process nonuniformity",
        "RootCause",
        "Low-confidence wafer process nonuniformity investigation candidate",
        ("process nonuniformity", "nonuniform process"),
    ),
    "ParticleContaminationCandidate": (
        "Particle contamination candidate",
        "RootCause",
        "Low-confidence wafer particle or residue investigation candidate",
        ("particle contamination", "particle candidate"),
    ),
    "EdgeProcessIssueCandidate": (
        "Edge process issue candidate",
        "RootCause",
        "Low-confidence edge-process investigation candidate",
        ("edge process issue", "edge effect"),
    ),
    "HandlingScratchCandidate": (
        "Handling scratch candidate",
        "RootCause",
        "Low-confidence wafer handling scratch investigation candidate",
        ("handling scratch", "scratch candidate"),
    ),
    "ToolingOrMaskPatternCandidate": (
        "Tooling or mask pattern candidate",
        "RootCause",
        "Low-confidence patterned process/tooling investigation candidate",
        ("tooling pattern", "mask pattern"),
    ),
}

WAFER_PATTERNS: tuple[WaferPatternSpec, ...] = (
    WaferPatternSpec(
        "center",
        "CenterDefect",
        ("center", "centre", "center defect"),
        "WaferCenterLocation",
        "Wafer center",
        ("center", "wafer center"),
        "WaferClusteredMorphology",
        "Wafer clustered morphology",
        ("clustered", "central cluster"),
        ("ProcessNonuniformity",),
    ),
    WaferPatternSpec(
        "donut",
        "DonutDefect",
        ("donut", "donut defect"),
        "WaferCenterLocation",
        "Wafer center",
        ("center", "wafer center"),
        "WaferRingMorphology",
        "Wafer ring morphology",
        ("ring", "donut", "annular"),
        ("ToolingOrMaskPatternCandidate", "ProcessNonuniformity"),
    ),
    WaferPatternSpec(
        "edge_loc",
        "EdgeLocDefect",
        ("edge_loc", "edge-loc", "edge loc", "edge location"),
        "WaferEdgeLocation",
        "Wafer edge",
        ("edge", "wafer edge"),
        "WaferClusteredMorphology",
        "Wafer clustered morphology",
        ("clustered", "edge cluster"),
        ("EdgeProcessIssueCandidate",),
    ),
    WaferPatternSpec(
        "edge_ring",
        "EdgeRingDefect",
        ("edge_ring", "edge-ring", "edge ring"),
        "WaferEdgeLocation",
        "Wafer edge",
        ("edge", "wafer edge"),
        "WaferRingMorphology",
        "Wafer ring morphology",
        ("ring", "edge ring"),
        ("EdgeProcessIssueCandidate", "ToolingOrMaskPatternCandidate"),
    ),
    WaferPatternSpec(
        "loc",
        "LocDefect",
        ("loc", "local", "localized", "local defect"),
        "WaferLocalLocation",
        "Wafer local region",
        ("local", "localized", "wafer local"),
        "WaferClusteredMorphology",
        "Wafer clustered morphology",
        ("clustered", "local cluster"),
        ("ProcessNonuniformity",),
    ),
    WaferPatternSpec(
        "random",
        "RandomDefect",
        ("random", "random defect"),
        "WaferSurface",
        "Wafer surface",
        ("wafer_surface", "wafer surface"),
        "WaferScatteredMorphology",
        "Wafer scattered morphology",
        ("scattered", "random", "diffuse"),
        ("ParticleContaminationCandidate", "ProcessNonuniformity"),
    ),
    WaferPatternSpec(
        "scratch",
        "WaferScratchDefect",
        ("scratch", "scratch defect", "wafer scratch"),
        "WaferSurface",
        "Wafer surface",
        ("wafer_surface", "wafer surface"),
        "WaferLinearMorphology",
        "Wafer linear morphology",
        ("linear", "line", "scratch"),
        ("HandlingScratchCandidate",),
    ),
    WaferPatternSpec(
        "nearfull",
        "NearfullDefect",
        ("nearfull", "near-full", "near full", "full contamination"),
        "WaferSurface",
        "Wafer surface",
        ("wafer_surface", "wafer surface"),
        "DenseParticles",
        "Dense particles",
        ("dense_particles", "dense particles"),
        ("ParticleContaminationCandidate",),
    ),
)


def audit_mvtec_cases(
    records_path: str | Path,
    adapter_table_path: str | Path,
) -> list[CaseAuditRow]:
    """Build coverage-aware ranking rows for MVTec records."""
    records = {str(record["case_id"]): record for record in _load_jsonl(records_path)}
    table_rows = _load_csv_rows(adapter_table_path)
    audited = [
        _mvtec_audit_row(row, records.get(str(row.get("case_id", "")), {}))
        for row in table_rows
    ]
    return _sort_audit_rows(audited)


def audit_wm811k_cases(
    record_paths: Sequence[str | Path],
    adapter_table_paths: Sequence[str | Path],
) -> list[CaseAuditRow]:
    """Build coverage-aware ranking rows for WM811K/wafer records."""
    records: dict[str, dict[str, Any]] = {}
    for path in record_paths:
        if Path(path).exists():
            records.update({str(record["case_id"]): record for record in _load_jsonl(path)})
    table_rows: list[dict[str, str]] = []
    for path in adapter_table_paths:
        if Path(path).exists():
            table_rows.extend(_load_csv_rows(path))
    audited = [
        _wm811k_audit_row(row, records.get(str(row.get("case_id", "")), {}))
        for row in table_rows
    ]
    return _sort_audit_rows(audited)


def write_case_audit_artifacts(
    rows: Sequence[CaseAuditRow],
    output_dir: str | Path,
    *,
    prefix: str,
    top_n: int = 8,
) -> dict[str, str]:
    """Write case ranking CSV, JSON, and Markdown top-case artifacts."""
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    csv_path = destination / f"{prefix}_case_ranking.csv"
    json_path = destination / f"{prefix}_case_ranking.json"
    md_path = destination / ("top_cases.md" if prefix == "mvtec" else f"{prefix}_top_cases.md")
    _write_dict_csv([row.model_dump() for row in rows], csv_path, CASE_RANKING_COLUMNS)
    json_path.write_text(
        json.dumps([row.model_dump() for row in rows], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    md_path.write_text(
        _top_cases_markdown(rows[:top_n], title=f"{prefix.upper()} Top Cases"),
        encoding="utf-8",
    )
    return {
        "csv_path": str(csv_path),
        "json_path": str(json_path),
        "markdown_path": str(md_path),
    }


def build_candidate_kg(
    *,
    mvtec_records_path: str | Path | None = None,
    mvtec_adapter_table_path: str | Path | None = None,
    wm811k_record_paths: Sequence[str | Path] = (),
    existing_node_paths: Sequence[str | Path] = DEFAULT_NODE_PATHS,
    existing_edge_paths: Sequence[str | Path] = DEFAULT_EDGE_PATHS,
) -> tuple[list[KGNode], list[KGEdge], dict[str, object]]:
    """Generate coverage-first candidate KG rows for MVTec and WM811K."""
    existing_graph = KnowledgeGraph.from_paths(
        existing_node_paths,
        existing_edge_paths,
        skip_missing=True,
    )
    existing_node_ids = set(existing_graph.nodes)
    existing_edge_ids = {edge.edge_id for edge in existing_graph.edges}
    nodes: dict[str, KGNode] = {}
    edges: dict[str, KGEdge] = {}

    if mvtec_records_path is not None and Path(mvtec_records_path).exists():
        adapter_rows = (
            _load_csv_rows(mvtec_adapter_table_path)
            if mvtec_adapter_table_path is not None and Path(mvtec_adapter_table_path).exists()
            else []
        )
        _add_mvtec_candidate_rows(
            _load_jsonl(mvtec_records_path),
            adapter_rows,
            nodes=nodes,
            edges=edges,
            existing_node_ids=existing_node_ids,
            existing_edge_ids=existing_edge_ids,
        )

    wm811k_records: list[dict[str, Any]] = []
    for path in wm811k_record_paths:
        if Path(path).exists():
            wm811k_records.extend(_load_jsonl(path))
    _add_wafer_candidate_rows(
        wm811k_records,
        nodes=nodes,
        edges=edges,
        existing_node_ids=existing_node_ids,
        existing_edge_ids=existing_edge_ids,
    )

    validation_findings = validate_candidate_claim_boundaries(edges.values())
    if validation_findings:
        raise ValueError("; ".join(validation_findings))

    summary = {
        "artifact_type": "coverage_first_candidate_kg_v0",
        "artifact_scope": "generated_reproducibility_output",
        "claim_boundary": CLAIM_BOUNDARY,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "mvtec_source_records": str(mvtec_records_path) if mvtec_records_path else None,
        "wm811k_source_records": [str(path) for path in wm811k_record_paths],
        "wm811k_pattern_coverage": [spec.pattern for spec in WAFER_PATTERNS],
        "note": (
            "Candidate KG rows are source-constrained paper artifacts. "
            "They support candidate paths and must not be described as verified RCA."
        ),
    }
    return (
        sorted(nodes.values(), key=lambda item: item.id),
        sorted(edges.values(), key=lambda item: item.edge_id),
        summary,
    )


def write_candidate_kg_artifacts(
    *,
    output_dir: str | Path,
    mvtec_records_path: str | Path | None = None,
    mvtec_adapter_table_path: str | Path | None = None,
    wm811k_record_paths: Sequence[str | Path] = (),
    before_after_inputs: Sequence[tuple[str | Path, DatasetName, str]] = (),
    top_k: int = 5,
    overwrite: bool = False,
) -> CandidateKGOutput:
    """Write candidate KG CSVs, validation report, and before/after artifacts."""
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    nodes_path = destination / "nodes_candidate.csv"
    edges_path = destination / "edges_candidate.csv"
    summary_path = destination / "kg_generation_summary.json"
    validation_path = destination / "validation_report.json"
    before_after_path = destination / "selected_case_reasoning_before_after.csv"
    explanations_path = destination / "top_case_explanations.md"
    output_paths = [
        nodes_path,
        edges_path,
        summary_path,
        validation_path,
        before_after_path,
        explanations_path,
    ]
    _ensure_outputs_can_write(output_paths, overwrite=overwrite)

    nodes, edges, summary = build_candidate_kg(
        mvtec_records_path=mvtec_records_path,
        mvtec_adapter_table_path=mvtec_adapter_table_path,
        wm811k_record_paths=wm811k_record_paths,
    )
    export_nodes_csv(nodes, nodes_path)
    export_edges_csv(edges, edges_path)

    validation = run_kg_qa(
        [*DEFAULT_NODE_PATHS, nodes_path],
        [*DEFAULT_EDGE_PATHS, edges_path],
    )
    validation_payload = validation.model_dump()
    validation_path.write_text(json.dumps(validation_payload, indent=2), encoding="utf-8")
    summary_payload = {
        **summary,
        "output": {
            "nodes_candidate": str(nodes_path),
            "edges_candidate": str(edges_path),
            "validation_report": str(validation_path),
            "before_after": str(before_after_path),
            "top_case_explanations": str(explanations_path),
        },
        "validation_summary": validation.summary(),
    }
    summary_path.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")

    before_after_rows: list[dict[str, object]] = []
    top_case_sections: list[str] = ["# Top Candidate Explanations", "", CLAIM_BOUNDARY, ""]
    for input_path, dataset, label in before_after_inputs:
        if not Path(input_path).exists():
            continue
        comparison = run_before_after_comparison(
            input_path,
            destination / f"{label}_before_after",
            dataset=dataset,
            candidate_nodes_path=nodes_path,
            candidate_edges_path=edges_path,
            top_k=top_k,
            overwrite=overwrite,
        )
        before_after_rows.extend(comparison)
        top_case_sections.extend(_comparison_markdown_section(label, comparison[:8]))
    _write_dict_csv(before_after_rows, before_after_path, BEFORE_AFTER_COLUMNS)
    explanations_path.write_text("\n".join(top_case_sections), encoding="utf-8")

    return CandidateKGOutput(
        nodes_path=nodes_path,
        edges_path=edges_path,
        summary_path=summary_path,
        validation_path=validation_path,
        before_after_path=before_after_path,
        explanations_path=explanations_path,
        node_count=len(nodes),
        edge_count=len(edges),
        validation_passed=validation.passed,
    )


def run_before_after_comparison(
    input_path: str | Path,
    output_dir: str | Path,
    *,
    dataset: DatasetName,
    candidate_nodes_path: str | Path,
    candidate_edges_path: str | Path,
    top_k: int = 5,
    overwrite: bool = False,
) -> list[dict[str, object]]:
    """Compare base KG reasoning with candidate overlay KG reasoning."""
    destination = Path(output_dir)
    base = run_adapter_pipeline(
        input_path,
        destination / "base",
        dataset=dataset,
        top_k=top_k,
        overwrite=overwrite,
    )
    overlay = run_adapter_pipeline(
        input_path,
        destination / "overlay",
        dataset=dataset,
        top_k=top_k,
        overwrite=overwrite,
        kg_node_paths=[candidate_nodes_path],
        kg_edge_paths=[candidate_edges_path],
    )
    return _compare_pipeline_outputs(base, overlay)


def validate_candidate_claim_boundaries(edges: Iterable[KGEdge]) -> list[str]:
    """Return claim-boundary violations for candidate KG edges."""
    findings: list[str] = []
    for edge in edges:
        text = f"{edge.relation} {edge.evidence}".lower()
        for forbidden in FORBIDDEN_VERIFIED_RCA_TEXT:
            if forbidden in text:
                findings.append(f"{edge.edge_id} contains forbidden claim: {forbidden}")
        if edge.relation == "CAUSED_BY" and edge.review_status != "reviewed":
            findings.append(f"{edge.edge_id} uses CAUSED_BY without reviewed status")
    return findings


def _mvtec_audit_row(row: Mapping[str, str], record: Mapping[str, Any]) -> CaseAuditRow:
    label = _text(record.get("source_label") or row.get("anomaly_type"))
    path_count = _int(row.get("path_count"))
    linked_count = _int(row.get("linked_entity_count"))
    correction_count = _int(row.get("correction_candidate_count"))
    area_ratio = _float(_nested(record, "mask_stats", "area_ratio"))
    pred_label = _text(record.get("pred_label"))
    confidence = _float(record.get("confidence") or _nested(record, "detector", "confidence"))
    score = _float(record.get("score") or _nested(record, "detector", "pred_score"))
    top_target = _text(row.get("top_target_entity_id"))
    notes = []
    if path_count == 0:
        notes.append("no current KG path")
    if _is_generic_target(top_target):
        notes.append("generic top target")
    if label == "good":
        notes.append("normal reference case")
    explainability = 0.0
    explainability += 2.0 if pred_label == "anomalous" and label != "good" else -0.5
    explainability += _area_score(area_ratio)
    explainability += min(2.0, 0.65 * _semantic_token_count(label))
    explainability += min(1.5, 0.25 * linked_count)
    explainability += min(2.0, 0.8 * path_count)
    explainability += 0.5 if top_target else 0.0
    if _is_generic_target(top_target):
        explainability -= 0.75
    return CaseAuditRow(
        case_id=_text(row.get("case_id")),
        dataset="mvtec",
        object=_text(record.get("object")),
        defect_type=label,
        score=score,
        confidence=confidence,
        pred_label=pred_label,
        mask_area_ratio=area_ratio,
        morphology=_text(row.get("morphology")),
        location=_text(row.get("location")),
        linked_entity_count=linked_count,
        correction_candidate_count=correction_count,
        path_count=path_count,
        top_target_entity_id=top_target,
        top_target_name=_text(row.get("top_target_name")),
        top_target_label=_text(row.get("top_target_label")),
        kg_path_specific=bool(path_count and not _is_generic_target(top_target)),
        evidence_clean=(
            pred_label == "anomalous" and label != "good" and _area_score(area_ratio) > 0
        ),
        explainability_score=explainability,
        notes="; ".join(notes),
    )


def _wm811k_audit_row(row: Mapping[str, str], record: Mapping[str, Any]) -> CaseAuditRow:
    anomaly_type = _text(row.get("anomaly_type") or record.get("predicted_pattern")).lower()
    path_count = _int(row.get("path_count"))
    linked_count = _int(row.get("linked_entity_count"))
    correction_count = _int(row.get("correction_candidate_count"))
    confidence = _float(record.get("classification_confidence") or record.get("score"))
    top_target = _text(row.get("top_target_entity_id"))
    notes = []
    if anomaly_type == "loc" and top_target == "GlueRemovalInsufficient":
        notes.append("misleading nearfull target under base KG")
    if path_count == 0:
        notes.append("no current KG path")
    explainability = 1.0
    known_patterns = {_pattern_alias_token(spec.pattern) for spec in WAFER_PATTERNS}
    explainability += 1.5 if anomaly_type in known_patterns else 0.0
    explainability += min(1.5, 0.25 * linked_count)
    explainability += min(2.0, 0.8 * path_count)
    explainability += 0.5 if top_target else 0.0
    if notes:
        explainability -= 0.75
    return CaseAuditRow(
        case_id=_text(row.get("case_id")),
        dataset="wafer",
        object="wafer",
        defect_type=anomaly_type,
        score=_float(record.get("score")),
        confidence=confidence,
        pred_label=_text(record.get("predicted_pattern") or record.get("failure_pattern")),
        mask_area_ratio=_float(record.get("defect_density")),
        morphology=_text(row.get("morphology")),
        location=_text(row.get("location")),
        linked_entity_count=linked_count,
        correction_candidate_count=correction_count,
        path_count=path_count,
        top_target_entity_id=top_target,
        top_target_name=_text(row.get("top_target_name")),
        top_target_label=_text(row.get("top_target_label")),
        kg_path_specific=bool(
            path_count and top_target and top_target != "GlueRemovalInsufficient"
        ),
        evidence_clean=not notes,
        explainability_score=explainability,
        notes="; ".join(notes),
    )


def _add_mvtec_candidate_rows(
    records: Sequence[Mapping[str, Any]],
    adapter_rows: Sequence[Mapping[str, str]],
    *,
    nodes: dict[str, KGNode],
    edges: dict[str, KGEdge],
    existing_node_ids: set[str],
    existing_edge_ids: set[str],
) -> None:
    rows_by_case = {str(row.get("case_id", "")): row for row in adapter_rows}
    observations_by_defect: dict[str, set[tuple[str, str]]] = defaultdict(set)
    object_defects: set[tuple[str, str]] = set()
    for record in records:
        label = _canonical_defect_label(record.get("source_label") or record.get("defect_type"))
        if not label or label == "good":
            continue
        object_name = _text(record.get("object"))
        object_id = f"{_pascal(object_name)}Object"
        defect_id = f"{_pascal(label)}Defect"
        object_defects.add((object_id, defect_id))
        _add_node(
            nodes,
            existing_node_ids,
            KGNode(
                id=object_id,
                name=_humanize(object_name),
                label="Object",
                scenario="mvtec",
                aliases=(_alias_token(object_name), object_name.replace("_", " ")),
                description="MVTec object covered by candidate KG generation",
            ),
        )
        _add_node(
            nodes,
            existing_node_ids,
            KGNode(
                id=defect_id,
                name=f"{_humanize(label)} defect",
                label="AnomalyType",
                scenario="mvtec",
                aliases=_defect_aliases(label),
                description="MVTec source-label visual defect covered by candidate KG generation",
            ),
        )
        row = rows_by_case.get(str(record.get("case_id")), {})
        morphology = _text(row.get("morphology")) or _infer_mvtec_morphology(label)
        location = _text(row.get("location")) or "surface"
        observations_by_defect[defect_id].add((morphology, location))

    for object_id, defect_id in sorted(object_defects):
        _add_edge(
            edges,
            existing_edge_ids,
            object_id,
            "HAS_ANOMALY",
            defect_id,
            "mvtec",
            "mvtec_calibrated_source_label",
            f"MVTec calibrated records include {defect_id} evidence for {object_id}.",
            0.82,
        )
    for defect_id, observations in observations_by_defect.items():
        label = _label_from_defect_id(defect_id)
        for morphology, location in sorted(observations):
            morphology_node = _mvtec_morphology_node(morphology)
            location_node = _mvtec_location_node(location)
            _add_node(nodes, existing_node_ids, morphology_node)
            _add_node(nodes, existing_node_ids, location_node)
            _add_edge(
                edges,
                existing_edge_ids,
                defect_id,
                "HAS_MORPHOLOGY",
                morphology_node.id,
                "mvtec",
                "mvtec_mask_geometry",
                f"Adapter/mask geometry maps {label} evidence to {morphology} morphology.",
                0.78,
            )
            _add_edge(
                edges,
                existing_edge_ids,
                defect_id,
                "OCCURS_ON",
                location_node.id,
                "mvtec",
                "mvtec_mask_geometry",
                f"Adapter/mask geometry maps {label} evidence to {location} location.",
                0.74,
            )
        for mechanism_id in _mvtec_mechanisms(label):
            _add_mechanism_node(nodes, existing_node_ids, mechanism_id, scenario="mvtec")
            _add_edge(
                edges,
                existing_edge_ids,
                defect_id,
                "HAS_PLAUSIBLE_CAUSE",
                mechanism_id,
                "mvtec",
                "mvtec_plausible_visual_mechanism",
                (
                    f"{label} is mapped to {MECHANISM_NODES[mechanism_id][0]} as a "
                    "candidate visual investigation path, not verified MVTec factory RCA."
                ),
                (
                    0.58
                    if mechanism_id
                    in {"GenericVisualDefectMechanism", "VisualInspectionReviewNeeded"}
                    else 0.66
                ),
            )


def _add_wafer_candidate_rows(
    records: Sequence[Mapping[str, Any]],
    *,
    nodes: dict[str, KGNode],
    edges: dict[str, KGEdge],
    existing_node_ids: set[str],
    existing_edge_ids: set[str],
) -> None:
    observed_patterns = {
        _canonical_wafer_pattern(record.get("predicted_pattern") or record.get("failure_pattern"))
        for record in records
    }
    observed_patterns.discard("")
    _add_node(
        nodes,
        existing_node_ids,
        KGNode(
            id="WaferObject",
            name="Wafer",
            label="Object",
            scenario="wafer",
            aliases=("wafer",),
            description="Wafer object for WM811K evidence",
        ),
    )
    for spec in WAFER_PATTERNS:
        _add_node(
            nodes,
            existing_node_ids,
            KGNode(
                id=spec.node_id,
                name=f"{_humanize(spec.pattern)} defect",
                label="AnomalyType",
                scenario="wafer",
                aliases=spec.aliases,
                description="WM811K public defect-pattern class covered by candidate KG generation",
            ),
        )
        _add_node(
            nodes,
            existing_node_ids,
            KGNode(
                id=spec.location_id,
                name=spec.location_name,
                label="Location",
                scenario="wafer",
                aliases=spec.location_aliases,
                description="Wafer-map spatial zone for WM811K evidence",
            ),
        )
        _add_node(
            nodes,
            existing_node_ids,
            KGNode(
                id=spec.morphology_id,
                name=spec.morphology_name,
                label="Morphology",
                scenario="wafer",
                aliases=spec.morphology_aliases,
                description="Wafer-map morphology for WM811K evidence",
            ),
        )
        _add_edge(
            edges,
            existing_edge_ids,
            "WaferObject",
            "HAS_ANOMALY",
            spec.node_id,
            "wafer",
            "wm811k_public_pattern_classes",
            f"WM811K public classifier/dataset pattern vocabulary includes {spec.pattern}.",
            0.86,
        )
        _add_edge(
            edges,
            existing_edge_ids,
            spec.node_id,
            "HAS_MORPHOLOGY",
            spec.morphology_id,
            "wafer",
            "wm811k_pattern_semantics",
            f"WM811K {spec.pattern} pattern is represented with {spec.morphology_name}.",
            0.82,
        )
        _add_edge(
            edges,
            existing_edge_ids,
            spec.node_id,
            "OCCURS_ON",
            spec.location_id,
            "wafer",
            "wm811k_pattern_semantics",
            f"WM811K {spec.pattern} pattern is represented at {spec.location_name}.",
            0.8,
        )
        for mechanism_id in spec.mechanism_ids:
            _add_mechanism_node(nodes, existing_node_ids, mechanism_id, scenario="wafer")
            confidence = 0.6 if spec.pattern in observed_patterns else 0.55
            _add_edge(
                edges,
                existing_edge_ids,
                spec.node_id,
                "HAS_PLAUSIBLE_CAUSE",
                mechanism_id,
                "wafer",
                "wm811k_low_confidence_investigation_rule",
                (
                    f"WM811K {spec.pattern} pattern maps to {MECHANISM_NODES[mechanism_id][0]} "
                    "as a low-confidence candidate investigation path, not verified process RCA."
                ),
                confidence,
            )


def _add_node(nodes: dict[str, KGNode], existing_node_ids: set[str], node: KGNode) -> None:
    if node.id in existing_node_ids:
        return
    existing = nodes.get(node.id)
    if existing is not None and existing != node:
        aliases = tuple(dict.fromkeys((*existing.aliases, *node.aliases)))
        nodes[node.id] = KGNode(
            id=existing.id,
            name=existing.name,
            label=existing.label,
            scenario=existing.scenario,
            aliases=aliases,
            description=existing.description or node.description,
        )
        return
    nodes[node.id] = node


def _add_mechanism_node(
    nodes: dict[str, KGNode],
    existing_node_ids: set[str],
    mechanism_id: str,
    *,
    scenario: str,
) -> None:
    name, label, description, aliases = MECHANISM_NODES[mechanism_id]
    _add_node(
        nodes,
        existing_node_ids,
        KGNode(
            id=mechanism_id,
            name=name,
            label=label,
            scenario=scenario,
            aliases=aliases,
            description=description,
        ),
    )


def _add_edge(
    edges: dict[str, KGEdge],
    existing_edge_ids: set[str],
    head: str,
    relation: str,
    tail: str,
    scenario: str,
    source: str,
    evidence: str,
    confidence: float,
    *,
    review_status: str = "auto",
) -> None:
    edge = KGEdge(
        head=head,
        relation=relation,
        tail=tail,
        scenario=scenario,
        source=source,
        evidence=evidence,
        confidence=confidence,
        weight=edge_weight(confidence),
        review_status=review_status,
        feedback_count=0,
        accepted_count=0,
        rejected_count=0,
    )
    if edge.edge_id in existing_edge_ids:
        return
    edges.setdefault(edge.edge_id, edge)


def _mvtec_morphology_node(value: str) -> KGNode:
    node_id, name, aliases = MORPHOLOGY_NODES.get(
        _alias_token(value),
        (f"{_pascal(value)}Morphology", f"{_humanize(value)} morphology", (_alias_token(value),)),
    )
    return KGNode(node_id, name, "Morphology", "mvtec", aliases, "Visual morphology")


def _mvtec_location_node(value: str) -> KGNode:
    node_id, name, aliases = LOCATION_NODES.get(
        _alias_token(value),
        (f"{_pascal(value)}Location", f"{_humanize(value)} location", (_alias_token(value),)),
    )
    return KGNode(node_id, name, "Location", "mvtec", aliases, "Visual anomaly location")


def _mvtec_mechanisms(label: str) -> tuple[str, ...]:
    token = _alias_token(label)
    if "scratch" in token:
        return ("MechanicalContact", "SurfaceWear")
    if "crack" in token:
        return ("MaterialDefect", "PackagingPressure")
    if "cut" in token or "poke" in token:
        return ("MechanicalContact", "HandlingDamage")
    if "bent" in token or "misplaced" in token or "manipulated" in token:
        return ("AssemblyError", "ProcessMisalignment")
    if "broken" in token or "damaged" in token or "split" in token:
        return ("ComponentDamageCandidate", "HandlingDamage")
    if "missing" in token:
        return ("MissingComponent", "AssemblyError")
    if "contamination" in token or "dirt" in token or "oil" in token or "liquid" in token:
        return ("ContaminationCause",)
    if "squeeze" in token:
        return ("PackagingPressure", "HandlingDamage")
    if "glue" in token:
        return ("AdhesiveOrResidueCandidate",)
    if "thread" in token or "rough" in token or "color" in token or "print" in token:
        return ("TextureIrregularityCandidate", "GenericVisualDefectMechanism")
    if "hole" in token:
        return ("MechanicalContact", "MaterialDefect")
    return ("GenericVisualDefectMechanism", "VisualInspectionReviewNeeded")


def _infer_mvtec_morphology(label: str) -> str:
    token = _alias_token(label)
    if any(part in token for part in ("scratch", "crack", "cut", "thread", "split")):
        return "linear"
    if any(part in token for part in ("contamination", "color", "oil", "liquid")):
        return "scattered"
    return "spot"


def _compare_pipeline_outputs(
    base: AdapterPipelineOutput,
    overlay: AdapterPipelineOutput,
) -> list[dict[str, object]]:
    base_cases = {case["case_id"]: case for case in base.summary["cases"]}
    rows: list[dict[str, object]] = []
    for overlay_case in overlay.summary["cases"]:
        case_id = str(overlay_case["case_id"])
        base_case = base_cases.get(case_id, {})
        base_target = _first_target(base_case)
        overlay_target = _first_target(overlay_case)
        evidence = overlay_case.get("generated_evidence", {})
        evidence_map = evidence if isinstance(evidence, Mapping) else {}
        base_linked = _int(base_case.get("linked_entity_count"))
        overlay_linked = _int(overlay_case.get("linked_entity_count"))
        base_paths = len(base_case.get("top_k_paths", []))
        overlay_paths = len(overlay_case.get("top_k_paths", []))
        rows.append(
            {
                "dataset": overlay_case.get("dataset", ""),
                "case_id": case_id,
                "anomaly_type": evidence_map.get("anomaly_type", ""),
                "base_linked_entity_count": base_linked,
                "overlay_linked_entity_count": overlay_linked,
                "linked_entity_delta": overlay_linked - base_linked,
                "base_path_count": base_paths,
                "overlay_path_count": overlay_paths,
                "path_count_delta": overlay_paths - base_paths,
                "base_top_target_entity_id": base_target,
                "overlay_top_target_entity_id": overlay_target,
                "base_consistency_score": base_case.get("consistency_score", ""),
                "overlay_consistency_score": overlay_case.get("consistency_score", ""),
                "claim_boundary": CLAIM_BOUNDARY,
            }
        )
    rows.sort(key=lambda item: (-_int(item["path_count_delta"]), str(item["case_id"])))
    return rows


def _first_target(case: Mapping[str, Any]) -> str:
    targets = case.get("candidate_plausible_explanation_targets", [])
    if isinstance(targets, list) and targets and isinstance(targets[0], Mapping):
        return str(targets[0].get("target_entity_id", ""))
    return ""


def _sort_audit_rows(rows: Sequence[CaseAuditRow]) -> list[CaseAuditRow]:
    return sorted(rows, key=lambda item: (-item.explainability_score, item.case_id))


def _top_cases_markdown(rows: Sequence[CaseAuditRow], *, title: str) -> str:
    lines = [f"# {title}", "", CLAIM_BOUNDARY, ""]
    for index, row in enumerate(rows, start=1):
        lines.append(
            f"{index}. `{row.case_id}` — {row.object}/{row.defect_type}, "
            f"score={row.explainability_score:.2f}, paths={row.path_count}, "
            f"target={row.top_target_entity_id or 'none'}"
        )
        if row.notes:
            lines.append(f"   Notes: {row.notes}")
    lines.append("")
    return "\n".join(lines)


def _comparison_markdown_section(label: str, rows: Sequence[Mapping[str, object]]) -> list[str]:
    lines = [f"## {label}", ""]
    for row in rows:
        lines.append(
            f"- `{row['case_id']}`: paths {row['base_path_count']} -> "
            f"{row['overlay_path_count']}, target "
            f"{row['base_top_target_entity_id'] or 'none'} -> "
            f"{row['overlay_top_target_entity_id'] or 'none'}"
        )
    lines.append("")
    return lines


def _write_dict_csv(
    rows: Sequence[Mapping[str, object]],
    path: Path,
    fieldnames: Sequence[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _load_csv_rows(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _ensure_outputs_can_write(paths: Sequence[Path], *, overwrite: bool) -> None:
    for path in paths:
        if path.exists() and not overwrite:
            raise FileExistsError(f"{path} already exists; pass --overwrite to replace it")


def _nested(data: Mapping[str, Any], *keys: str) -> Any:
    value: Any = data
    for key in keys:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
    return value


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _int(value: Any) -> int:
    if value in (None, ""):
        return 0
    return int(float(str(value)))


def _float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _area_score(area_ratio: float | None) -> float:
    if area_ratio is None:
        return 0.0
    if 0.005 <= area_ratio <= 0.18:
        return 1.5
    if 0.001 <= area_ratio <= 0.3:
        return 0.5
    return -1.0


def _semantic_token_count(label: str) -> int:
    token = _alias_token(label)
    return sum(
        part in token
        for part in (
            "crack",
            "scratch",
            "broken",
            "bent",
            "cut",
            "hole",
            "missing",
            "contamination",
            "poke",
            "squeeze",
            "damaged",
            "split",
            "teeth",
        )
    )


def _is_generic_target(target_id: str) -> bool:
    return target_id in {"", "GenericVisualDefectMechanism", "VisualInspectionReviewNeeded"}


def _canonical_defect_label(value: Any) -> str:
    return _alias_token(_text(value))


def _canonical_wafer_pattern(value: Any) -> str:
    token = _alias_token(_text(value))
    aliases = {
        "nearfull": "nearfull",
        "near_full": "nearfull",
        "near-full": "nearfull",
        "edge_loc": "edge_loc",
        "edgeloc": "edge_loc",
        "edge_loc_": "edge_loc",
        "edge_ring": "edge_ring",
        "edgering": "edge_ring",
        "loc": "loc",
        "local": "loc",
    }
    return aliases.get(token, token)


def _pattern_alias_token(pattern: str) -> str:
    return _canonical_wafer_pattern(pattern)


def _label_from_defect_id(defect_id: str) -> str:
    return re.sub(r"Defect$", "", defect_id)


def _defect_aliases(label: str) -> tuple[str, ...]:
    human = label.replace("_", " ")
    aliases = [label, human, f"{human} defect"]
    for part in label.split("_"):
        if len(part) > 3:
            aliases.append(part)
    return tuple(dict.fromkeys(alias for alias in aliases if alias))


def _alias_token(value: str) -> str:
    return "_".join(re.findall(r"[a-z0-9]+", value.lower().replace("-", "_")))


def _pascal(value: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", value.replace("-", "_"))
    return "".join(word[:1].upper() + word[1:] for word in words) or "Unknown"


def _humanize(value: str) -> str:
    return " ".join(part for part in re.split(r"[_\s-]+", value.strip()) if part).capitalize()
