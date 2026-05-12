export type CaseSummary = {
  case_id: string;
  dataset: string;
  source: string;
  evidence_path: string;
  source_kind: string;
  observation_count: number;
  label: string;
  is_real_output: boolean;
};

export type EvidenceObservation = {
  obs_id: string;
  facet: string;
  name: string;
  display_name?: string | null;
  value?: unknown;
  value_type?: string | null;
  confidence?: number | null;
  source_ref?: string | null;
  raw_ref?: string | null;
};

export type Evidence = {
  case_id: string;
  dataset: "mvtec" | "tep" | "wafer";
  source: string;
  object: string;
  anomaly_type: string;
  location?: string | null;
  morphology?: string | null;
  severity?: number | null;
  confidence?: number | null;
  timestamp?: string | null;
  raw_evidence: {
    image_region?: string | null;
    heatmap_path?: string | null;
    variables: string[];
    variable_contributions: Record<string, number>;
    log_events: string[];
    description?: string | null;
    extra: Record<string, unknown>;
  };
  observations: EvidenceObservation[];
  adapter?: {
    name: string;
    version?: string | null;
    produces_root_cause: boolean;
    metadata: Record<string, unknown>;
  } | null;
  normalized_evidence: Record<string, unknown>;
  kg_analysis: {
    linked_entities: LinkedEntity[];
    consistency_score?: number | null;
    inconsistent_fields: string[];
    correction_candidates: CorrectionCandidate[];
    top_k_paths: PathResult[];
  };
  human_feedback?: Record<string, unknown> | null;
};

export type LinkedEntity = {
  link_id: string;
  field: string;
  mention: string;
  selected_entity_id?: string | null;
  score?: number;
  match_type?: string;
  ambiguous?: boolean;
  candidates?: Array<Record<string, unknown>>;
  facet?: string;
};

export type CorrectionCandidate = {
  candidate_id: string;
  field: string;
  suggested_value?: string;
  suggested_entity_id?: string;
  score?: number;
  reason?: string;
  supporting_edge_ids?: string[];
};

export type PathResult = {
  path_id: string;
  source_entity_id: string;
  target_entity_id: string;
  node_names: string[];
  relations: string[];
  score: number;
  confidence?: number;
  evidence_match?: number;
  supporting_evidence?: string[];
  source_edge_ids?: string[];
  source_edges?: Array<Record<string, unknown>>;
};

export type AnalysisResponse = {
  case?: CaseSummary | null;
  evidence: Evidence;
  analysis: {
    case_id: string;
    linked_entities: LinkedEntity[];
    consistency_score?: number | null;
    inconsistent_fields: string[];
    correction_candidates: CorrectionCandidate[];
    top_k_paths: PathResult[];
    human_feedback?: Record<string, unknown> | null;
  };
  evidence_with_analysis: Evidence;
  workflow_steps: RunStep[];
  claim_boundary: string;
};

export type RunSummary = {
  run_id: string;
  created_at: string;
  mode: "evidence" | "records" | "image";
  source_filename: string;
  top_k: number;
  run_dir: string;
  status: "completed" | "failed";
  dataset?: string | null;
  case_count: number;
  evidence_count: number;
  label: string;
  model_preset?: string | null;
  model_backend?: string | null;
};

export type RunStep = {
  step_id: string;
  title: string;
  status: "completed" | "failed";
  summary: string;
  details: Record<string, unknown>;
};

export type RunDetail = {
  run: RunSummary;
  workflow_steps: RunStep[];
  claim_boundary: string;
  evidence?: Evidence | null;
  evidence_with_analysis?: Evidence | null;
  analysis?: AnalysisResponse["analysis"] | null;
  summary?: Record<string, unknown> | null;
  cases?: Array<Record<string, unknown>>;
  artifacts: Record<string, string>;
};

export type MvtecModelPreset = {
  preset: string;
  label: string;
  description: string;
  available: boolean;
  recommended?: boolean;
  backend?: string | null;
  checkpoint_path?: string | null;
  checkpoint_hint?: string | null;
  download_asset?: string | null;
  resolved_preset?: string | null;
  resolved_label?: string | null;
};

export type MvtecModelPresetResponse = {
  default_preset: string;
  presets: MvtecModelPreset[];
};

export type ModelAssetDownloadResponse = {
  artifact_type: string;
  assets_root: string;
  assets: Record<string, Record<string, unknown>>;
};
