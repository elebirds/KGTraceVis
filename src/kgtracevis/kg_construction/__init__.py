"""Source-constrained KG construction modules."""

from kgtracevis.kg_construction.candidate_entity_extractor import (
    CandidateEntity,
    extract_candidate_entities,
)
from kgtracevis.kg_construction.candidate_triple_extractor import (
    CandidateTriple,
    extract_candidate_triples,
)
from kgtracevis.kg_construction.case_kg_hardening import (
    CandidateKGOutput,
    CaseAuditRow,
    audit_mvtec_cases,
    audit_wm811k_cases,
    build_candidate_kg,
    build_coverage_report,
    run_before_after_comparison,
    validate_candidate_claim_boundaries,
    write_candidate_kg_artifacts,
    write_case_audit_artifacts,
    write_edge_review_queue,
)
from kgtracevis.kg_construction.confidence_assigner import assign_confidence, edge_weight
from kgtracevis.kg_construction.draft import (
    DraftEntity,
    DraftKG,
    DraftRelation,
    KGConstructionSource,
    draft_relations_from_source_text,
    draft_status_to_review_status,
)
from kgtracevis.kg_construction.end_to_end_interpretability_audit import (
    EndToEndInterpretabilityAuditOutput,
    write_end_to_end_interpretability_audit,
)
from kgtracevis.kg_construction.export_kg_csv import (
    export_edges_csv,
    export_kg_csv,
    export_nodes_csv,
    validate_edges,
    validate_kg_csv_contract,
    validate_nodes,
)
from kgtracevis.kg_construction.extractors import (
    ExtractorRegistry,
    KGSourceExtractor,
    StructuredRecordExtractor,
    default_extractor_registry,
)
from kgtracevis.kg_construction.models import (
    KGConstructionBuildSummary,
    KGConstructionDraftRow,
    KGConstructionManifest,
    KGConstructionReviewDecision,
    KGConstructionRunRecord,
    build_construction_manifest,
    build_construction_summary,
    build_kg_construction_run_id,
    build_review_decision_id,
    draft_rows_from_draft,
    review_decision_for_edge,
)
from kgtracevis.kg_construction.mvtec_source_bundle import (
    DEFAULT_MVTEC_SOURCE_DIR,
    DEFAULT_MVTEC_SOURCES,
    DownloadableSource,
    download_mvtec_source_bundle,
)
from kgtracevis.kg_construction.pipeline import KGConstructionResult, run_kg_construction
from kgtracevis.kg_construction.qa import KGQAFinding, KGQAReport, run_kg_qa
from kgtracevis.kg_construction.source_loader import (
    SourceRecord,
    load_source_registry,
    load_source_text,
    load_structured_records,
)
from kgtracevis.kg_construction.tep_import import (
    TepSemanticLiftExtractor,
    TepVariableMappingExtractor,
    tep_external_id_to_kg_id,
)
from kgtracevis.kg_construction.triple_cleaner import (
    clean_candidate_nodes,
    clean_candidate_triples,
)

__all__ = [
    "CandidateEntity",
    "CandidateKGOutput",
    "CandidateTriple",
    "CaseAuditRow",
    "DEFAULT_MVTEC_SOURCES",
    "DEFAULT_MVTEC_SOURCE_DIR",
    "DownloadableSource",
    "DraftEntity",
    "DraftKG",
    "DraftRelation",
    "EndToEndInterpretabilityAuditOutput",
    "ExtractorRegistry",
    "KGConstructionResult",
    "KGConstructionBuildSummary",
    "KGConstructionDraftRow",
    "KGConstructionManifest",
    "KGConstructionReviewDecision",
    "KGConstructionRunRecord",
    "KGConstructionSource",
    "KGQAFinding",
    "KGQAReport",
    "KGSourceExtractor",
    "SourceRecord",
    "StructuredRecordExtractor",
    "TepSemanticLiftExtractor",
    "TepVariableMappingExtractor",
    "assign_confidence",
    "audit_mvtec_cases",
    "audit_wm811k_cases",
    "build_construction_manifest",
    "build_construction_summary",
    "build_candidate_kg",
    "build_kg_construction_run_id",
    "build_review_decision_id",
    "build_coverage_report",
    "clean_candidate_nodes",
    "clean_candidate_triples",
    "default_extractor_registry",
    "download_mvtec_source_bundle",
    "draft_relations_from_source_text",
    "draft_rows_from_draft",
    "draft_status_to_review_status",
    "edge_weight",
    "export_edges_csv",
    "export_kg_csv",
    "export_nodes_csv",
    "extract_candidate_entities",
    "extract_candidate_triples",
    "load_source_registry",
    "load_source_text",
    "load_structured_records",
    "review_decision_for_edge",
    "run_kg_construction",
    "run_kg_qa",
    "run_before_after_comparison",
    "tep_external_id_to_kg_id",
    "validate_candidate_claim_boundaries",
    "validate_edges",
    "validate_kg_csv_contract",
    "validate_nodes",
    "write_candidate_kg_artifacts",
    "write_case_audit_artifacts",
    "write_end_to_end_interpretability_audit",
    "write_edge_review_queue",
]
