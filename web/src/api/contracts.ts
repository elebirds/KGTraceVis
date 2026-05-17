export type UploadMode = "evidence" | "records" | "image";
export type ReviewTargetType =
  | "path"
  | "edge"
  | "entity_link"
  | "correction"
  | "root_cause_candidate";
export type ReviewAction = "accept" | "reject" | "needs_review";
export type KGConstructionSourceType =
  | "structured_records"
  | "manual_table"
  | "tep_semantic_lift"
  | "tep_variable_mapping";
export type KGConstructionSourceFormat = "csv" | "json" | "jsonl";

export interface WorkflowStep {
  step_id: string;
  title: string;
  status: "completed" | "failed";
  summary: string;
  details: Record<string, unknown>;
}

export interface RunSummary {
  run_id: string;
  created_at: string;
  mode: UploadMode;
  source_filename: string;
  top_k: number;
  run_dir: string;
  status: "completed" | "failed";
  dataset: string | null;
  case_count: number;
  evidence_count: number;
  label: string;
  model_preset: string | null;
  model_backend: string | null;
}

export interface EvidenceSummary {
  case_id?: string;
  dataset?: string;
  source?: string;
  object?: string | null;
  anomaly_type?: string | null;
  location?: string | null;
  morphology?: string | null;
  severity?: number | null;
  confidence?: number | null;
  observation_count?: number;
  [key: string]: unknown;
}

export interface ReviewTarget {
  target_type: ReviewTargetType;
  target_id: string;
  target_key: string;
  label: string;
}

export interface PathGraphNode {
  node_id: string;
  label: string;
  role: "source" | "intermediate" | "target" | string;
}

export interface PathGraphEdge {
  edge_id: string;
  target_key: string;
  source_node_id: string;
  target_node_id: string;
  relation: string;
  source?: string | null;
  evidence?: string | null;
  confidence?: number | null;
  review_status?: string | null;
}

export interface PathGraphPath {
  path_id: string;
  target_key: string;
  source_entity_id?: string | null;
  target_entity_id?: string | null;
  score?: number | null;
  confidence?: number | null;
  supporting_evidence: unknown[];
  nodes: PathGraphNode[];
  edges: PathGraphEdge[];
}

export interface PathGraph {
  paths: PathGraphPath[];
  path_count: number;
  node_count: number;
  edge_count: number;
}

export interface VisualEvidenceItem {
  artifact_id: string;
  case_id: string;
  dataset: string;
  kind: "image" | "mask" | "heatmap" | "wafer_map";
  title: string;
  source_key: string;
  source_path: string | null;
  url: string | null;
  preview_path: string | null;
  available: boolean;
  note: string;
  metadata: Record<string, unknown>;
}

export interface RunDetail {
  run: RunSummary;
  workflow_steps: WorkflowStep[];
  claim_boundary: string;
  evidence: Record<string, unknown> | null;
  evidence_summary: EvidenceSummary | null;
  evidence_with_analysis: Record<string, unknown> | null;
  analysis: Record<string, unknown> | null;
  summary: Record<string, unknown> | null;
  cases: Array<Record<string, unknown>>;
  linked_entities: Array<Record<string, unknown>>;
  correction_candidates: Array<Record<string, unknown>>;
  top_k_paths: Array<Record<string, unknown>>;
  ranked_root_causes: Array<Record<string, unknown>>;
  reasoning_metadata: Record<string, unknown>;
  path_graph: PathGraph;
  source_edge_provenance: Array<Record<string, unknown>>;
  review_targets: ReviewTarget[];
  artifacts: Record<string, string>;
  visual_evidence: VisualEvidenceItem[];
}

export interface UploadModeInfo {
  mode: UploadMode;
  label: string;
  description: string;
  accepted_extensions: string[];
  required_fields: string[];
}

export interface DashboardReasoningProfileOption {
  profile_id: string;
  reasoner_adapter: string;
  default: boolean;
}

export interface DashboardBootstrap {
  status: string;
  api_version: string;
  claim_boundary: string;
  supported_datasets: string[];
  supported_feedback_targets: ReviewTargetType[];
  supported_feedback_actions: ReviewAction[];
  upload_modes: UploadModeInfo[];
  reasoning_profile_options: Record<string, DashboardReasoningProfileOption[]>;
  mvtec_model_presets: {
    default_preset: string;
    presets: Array<Record<string, unknown>>;
  };
  recent_runs: RunSummary[];
}

export interface KGStudioSource {
  source_id: string;
  title: string;
  source_type: string;
  path_or_url: string;
  used_for: string;
  notes: string;
}

export interface KGStudioSourceDocument {
  path: string;
  title: string;
  line_count: number;
}

export interface KGStudioGraphNode {
  node_id: string;
  label: string;
  node_type: string;
  scenario: string;
  description: string;
}

export interface KGStudioGraphEdge {
  edge_id: string;
  target_key: string;
  head: string;
  relation: string;
  tail: string;
  scenario: string;
  source: string;
  evidence: string;
  confidence: number | null;
  weight: number | null;
  review_status: string;
}

export interface KGStudioReviewTarget {
  target_type: "edge";
  target_id: string;
  target_key: string;
  label: string;
  source: string;
  confidence: number | null;
  review_status: string;
}

export interface KGStudioPayload {
  status: "ok" | "empty" | string;
  claim_boundary: string;
  candidate_dir: string | null;
  nodes_path: string | null;
  edges_path: string | null;
  source_registry_path: string;
  node_count: number;
  edge_count: number;
  scenario_counts: Record<string, number>;
  review_status_counts: Record<string, number>;
  source_counts: Record<string, number>;
  confidence_summary: Record<string, number | null>;
  validation_summary: Record<string, unknown> | null;
  sources: KGStudioSource[];
  source_documents: KGStudioSourceDocument[];
  graph_nodes: KGStudioGraphNode[];
  graph_edges: KGStudioGraphEdge[];
  review_targets: KGStudioReviewTarget[];
  note: string;
}

export interface KGMaterialRecord {
  material_id: string;
  title: string;
  source_type: string;
  source_format?: string | null;
  scenario?: string | null;
  path?: string | null;
  url?: string | null;
  uri?: string | null;
  filename?: string | null;
  content_type?: string | null;
  size_bytes?: number | null;
  status?: string | null;
  processing_status?: string | null;
  extraction_status?: string | null;
  chunk_count?: number | null;
  page_count?: number | null;
  source_id?: string | null;
  notes?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  metadata?: Record<string, unknown>;
  extraction?: KGMaterialExtractionState;
}

export interface KGMaterialExtractionState {
  status?: string | null;
  structured_records_path?: string | null;
  source_format?: KGConstructionSourceFormat | null;
  source_id?: string | null;
  extractor_name?: string | null;
  extractor_version?: string | null;
  prompt_version?: string | null;
  document_understanding_mode?: "chunk" | "long_context" | "agentic" | null;
  hypothesis_mode?: "none" | "brainstorm" | null;
  hypothesis_provider?: "none" | "openai" | "offline_fixture" | null;
  hypothesis_influence?: "review_only" | "prompt_context" | "profile_suggestions" | null;
  extracted_at?: string | null;
  record_count?: number | null;
  chunk_count?: number | null;
  error_count?: number | null;
  extraction_manifest_path?: string | null;
  chunk_results_path?: string | null;
  document_understanding_map_path?: string | null;
  chunk_prompt_context_path?: string | null;
  hypothesis_brainstorming_manifest_path?: string | null;
  brainstorm_hypotheses_path?: string | null;
  brainstorm_review_items_path?: string | null;
  brainstorm_evidence_tasks_path?: string | null;
  brainstorm_profile_gaps_path?: string | null;
  alignment_suggestions_path?: string | null;
  semantic_layer_suggestions_path?: string | null;
  profile_gap_suggestions_path?: string | null;
  error_message?: string | null;
}

export interface KGMaterialListResponse {
  status: string;
  materials: KGMaterialRecord[];
  count?: number;
  material_dir?: string | null;
  note?: string | null;
}

export interface KGMaterialUploadRequest {
  file: File;
  title?: string;
  scenario?: string;
  source_type?: string;
  notes?: string;
  metadata?: Record<string, unknown>;
}

export interface KGMaterialUploadResponse {
  status: string;
  material: KGMaterialRecord;
  note?: string | null;
}

export interface KGMaterialRegisterUrlRequest {
  url: string;
  title?: string;
  scenario?: string;
  source_type?: string;
  notes?: string;
  metadata?: Record<string, unknown>;
}

export interface KGMaterialRegisterUrlResponse {
  status: string;
  material: KGMaterialRecord;
  note?: string | null;
}

export interface KGMaterialExtractionRequest {
  provider?: "openai" | "offline_fixture";
  max_chars?: number;
  overlap_chars?: number;
  source_format?: Extract<KGConstructionSourceFormat, "jsonl">;
  prompt_version?: string;
  document_understanding_mode?: "chunk" | "long_context" | "agentic";
  document_understanding_provider?: "none" | "openai" | "offline_fixture";
  document_understanding_prompt_version?: string;
  hypothesis_mode?: "none" | "brainstorm";
  hypothesis_provider?: "none" | "openai" | "offline_fixture";
  hypothesis_influence?: "review_only" | "prompt_context" | "profile_suggestions";
  hypothesis_prompt_version?: string;
  default_confidence?: number;
  strict_grounding?: boolean;
  continue_on_chunk_error?: boolean;
  document_ie_fixture_path?: string | null;
  document_ie_payload?: Record<string, unknown> | null;
  document_understanding_fixture_path?: string | null;
  document_understanding_payload?: Record<string, unknown> | null;
  hypothesis_fixture_path?: string | null;
  hypothesis_payload?: Record<string, unknown> | null;
  overwrite?: boolean;
}

export interface KGMaterialExtractionResponse {
  status: string;
  material: KGMaterialRecord;
  structured_records_path: string;
  record_count: number;
  extraction_manifest_path: string;
  chunk_results_path: string;
  document_understanding_map_path?: string | null;
  chunk_prompt_context_path?: string | null;
  hypothesis_brainstorming_manifest_path?: string | null;
  brainstorm_hypotheses_path?: string | null;
  brainstorm_review_items_path?: string | null;
  chunk_count: number;
  error_count: number;
  provider: "openai" | "offline_fixture";
  extractor_name: string;
  extractor_version: string;
  prompt_version: string;
  claim_boundary: string;
}

export interface KGMaterialBuildSourcesRequest {
  material_ids: string[];
  output_name?: string;
  overwrite?: boolean;
  run_id?: string;
  source_type?: Extract<KGConstructionSourceType, "structured_records" | "manual_table">;
}

export interface KGMaterialBuildSourcesResponse {
  status: "ready" | string;
  material_root: string;
  request: KGMaterialBuildSourcesRequest;
  materials: KGMaterialRecord[];
  sources: KGConstructionSourceInput[];
  construction_request: KGConstructionBuildRequest;
  claim_boundary: string;
}

export interface UploadRequest {
  file: File;
  mode: UploadMode;
  dataset?: string;
  object_name?: string;
  defect_type?: string;
  model_preset?: string;
  reasoning_profile_id?: string;
  top_k: number;
}

export interface ReviewRequest {
  run_id?: string;
  case_id?: string;
  target_type: ReviewTargetType;
  target_id: string;
  action: ReviewAction;
  note?: string;
  reviewer?: string;
  source: string;
  metadata?: Record<string, unknown>;
}

export type KGDraftAction = "keep" | "revise" | "reject" | "promote_later";

export interface KGDraftRequest {
  target_type: "edge";
  target_id: string;
  target_key?: string;
  draft_action: KGDraftAction;
  proposed_relation?: string;
  proposed_evidence?: string;
  proposed_confidence?: number;
  note?: string;
  reviewer?: string;
  source: string;
  metadata?: Record<string, unknown>;
}

export interface KGSourceDraftRequest {
  source_id: string;
  source_text: string;
  provider: "heuristic";
  default_scenario: string;
  confidence: number;
}

export interface KGSourceDraftEdge {
  edge_id: string;
  head: string;
  relation: string;
  tail: string;
  scenario: string;
  source: string;
  evidence: string;
  confidence: number;
  weight: number;
  review_status: string;
}

export interface KGSourceDraftResponse {
  provider: "heuristic";
  source_id: string;
  claim_boundary: string;
  candidate_edges: KGSourceDraftEdge[];
  note: string;
}

export interface KGConstructionSourceInput {
  source_id: string;
  source_type: KGConstructionSourceType;
  scenario: string;
  path?: string;
  source_text?: string;
  source_format?: KGConstructionSourceFormat;
  semantic_nodes_path?: string;
  semantic_edges_path?: string;
  metadata?: Record<string, unknown>;
}

export interface KGConstructionBuildRequest {
  sources: KGConstructionSourceInput[];
  output_name: string;
  overwrite: boolean;
  run_id?: string;
}

export interface KGConstructionBuildResponse {
  status: string;
  run_id: string;
  output_dir: string;
  nodes_path: string;
  edges_path: string;
  published_nodes_path?: string | null;
  published_edges_path?: string | null;
  summary_path: string;
  manifest_path: string;
  source_library_manifest_path?: string | null;
  draft_manifest_path?: string | null;
  profile_manifest_path?: string | null;
  alignment_manifest_path?: string | null;
  source_audit_graph_manifest_path?: string | null;
  semantic_layer_manifest_path?: string | null;
  rca_view_manifest_path?: string | null;
  review_queue_path?: string | null;
  document_understanding_manifest_path?: string | null;
  document_map_path?: string | null;
  chunk_prompt_context_path?: string | null;
  cross_chunk_proposals_path?: string | null;
  hypothesis_brainstorming_manifest_path?: string | null;
  brainstorm_hypotheses_path?: string | null;
  brainstorm_review_items_path?: string | null;
  alignment_suggestions_path?: string | null;
  semantic_layer_suggestions_path?: string | null;
  profile_gap_suggestions_path?: string | null;
  publish_manifest_path?: string | null;
  publish_report_path?: string | null;
  diff_path?: string | null;
  summary: Record<string, unknown>;
  claim_boundary: string;
}

export interface KGConstructionBuildRecord {
  run_id: string;
  status: string;
  created_at?: string | null;
  output_dir: string;
  nodes_path: string;
  edges_path: string;
  published_nodes_path?: string | null;
  published_edges_path?: string | null;
  summary_path: string;
  manifest_path: string;
  source_library_manifest_path?: string | null;
  draft_manifest_path?: string | null;
  profile_manifest_path?: string | null;
  alignment_manifest_path?: string | null;
  source_audit_graph_manifest_path?: string | null;
  semantic_layer_manifest_path?: string | null;
  rca_view_manifest_path?: string | null;
  review_queue_path?: string | null;
  document_understanding_manifest_path?: string | null;
  document_map_path?: string | null;
  chunk_prompt_context_path?: string | null;
  cross_chunk_proposals_path?: string | null;
  hypothesis_brainstorming_manifest_path?: string | null;
  brainstorm_hypotheses_path?: string | null;
  brainstorm_review_items_path?: string | null;
  alignment_suggestions_path?: string | null;
  semantic_layer_suggestions_path?: string | null;
  profile_gap_suggestions_path?: string | null;
  publish_manifest_path?: string | null;
  publish_report_path?: string | null;
  diff_path?: string | null;
  source_ids: string[];
  source_count: number;
  node_count: number;
  edge_count: number;
  scenarios: Record<string, number>;
  review_status_counts: Record<string, number>;
  claim_boundary: string;
}

export interface KGConstructionBuildListResponse {
  build_root: string;
  builds: KGConstructionBuildRecord[];
}

export interface KGConstructionReviewQueueEdge {
  target_key: string;
  head: string;
  relation: string;
  tail: string;
  scenario: string;
  source: string;
  evidence: string;
  confidence: number;
  weight: number;
  review_status: string;
  feedback_count: number;
  accepted_count: number;
  rejected_count: number;
  item_type: string;
  priority?: number | null;
  reason: string;
  relation_family: string;
  graph_impact: string;
  recommended_action: string;
  candidate_payload: Record<string, unknown>;
}

export interface KGConstructionReviewQueueResponse {
  build: KGConstructionBuildRecord;
  filters: Record<string, unknown>;
  total_count: number;
  returned_count: number;
  offset: number;
  limit: number;
  edges: KGConstructionReviewQueueEdge[];
  summary: {
    review_status_counts: Record<string, number>;
    relation_counts: Record<string, number>;
    scenario_counts: Record<string, number>;
    source_counts: Record<string, number>;
  };
  claim_boundary: string;
}

export interface KGConstructionReviewRequest {
  action: Extract<ReviewAction, "accept" | "reject">;
  item_type?: string;
  target_key: string;
  reviewer?: string;
  note?: string;
  metadata?: Record<string, unknown>;
}

export interface KGConstructionReviewResponse {
  build: KGConstructionBuildRecord;
  decision: Record<string, unknown>;
  edge: Record<string, unknown>;
  item: Record<string, unknown>;
  summary: Record<string, unknown>;
  manifest_path: string;
  edges_path: string;
  claim_boundary: string;
}

export interface KGConstructionOverlayValidationRequest {
  example_dir?: string;
  overlay_only_runtime?: boolean;
  overlay_only_import?: boolean;
  top_k?: number;
}

export interface KGConstructionOverlayValidationResponse {
  build: KGConstructionBuildRecord;
  report: Record<string, unknown>;
  report_path?: string | null;
  claim_boundary: string;
}
