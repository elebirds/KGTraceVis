export type UploadMode = "evidence" | "records" | "image";
export type ReviewTargetType = "path" | "edge" | "entity_link" | "correction";
export type ReviewAction = "accept" | "reject" | "needs_review";

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
  path_graph: PathGraph;
  source_edge_provenance: Array<Record<string, unknown>>;
  review_targets: ReviewTarget[];
  artifacts: Record<string, string>;
}

export interface UploadModeInfo {
  mode: UploadMode;
  label: string;
  description: string;
  accepted_extensions: string[];
  required_fields: string[];
}

export interface DashboardBootstrap {
  status: string;
  api_version: string;
  claim_boundary: string;
  supported_datasets: string[];
  supported_feedback_targets: ReviewTargetType[];
  supported_feedback_actions: ReviewAction[];
  upload_modes: UploadModeInfo[];
  mvtec_model_presets: {
    default_preset: string;
    presets: Array<Record<string, unknown>>;
  };
  recent_runs: RunSummary[];
}

export interface UploadRequest {
  file: File;
  mode: UploadMode;
  dataset?: string;
  object_name?: string;
  defect_type?: string;
  model_preset?: string;
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
