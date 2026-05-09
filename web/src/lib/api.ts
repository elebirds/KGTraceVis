import type {
  AnalysisResponse,
  CaseSummary,
  Evidence,
  RunDetail,
  RunSummary,
} from "../types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const isFormData = init?.body instanceof FormData;
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed with status ${response.status}`);
  }

  return (await response.json()) as T;
}

export function listCases(): Promise<CaseSummary[]> {
  return requestJson<CaseSummary[]>("/api/cases");
}

export function listRuns(): Promise<RunSummary[]> {
  return requestJson<RunSummary[]>("/api/runs");
}

export function loadCase(caseId: string): Promise<AnalysisResponse> {
  return requestJson<AnalysisResponse>(`/api/cases/${encodeURIComponent(caseId)}`);
}

export function loadRun(runId: string): Promise<RunDetail> {
  return requestJson<RunDetail>(`/api/runs/${encodeURIComponent(runId)}`);
}

export function analyzeEvidence(
  evidence: Evidence,
  topK: number,
): Promise<AnalysisResponse> {
  return requestJson<AnalysisResponse>("/api/analyze", {
    method: "POST",
    body: JSON.stringify({ evidence, top_k: topK }),
  });
}

export function runWhatIf(request: {
  case_id: string;
  anomaly_type: string;
  location: string;
  morphology: string;
  variables: string[];
  log_events: string[];
  severity?: number | null;
  confidence?: number | null;
  top_k: number;
}): Promise<AnalysisResponse> {
  return requestJson<AnalysisResponse>("/api/what-if", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function sendFeedback(request: {
  case_id: string;
  target_type: "case" | "link" | "correction" | "path";
  decision: "accept" | "reject" | "comment";
  target_id?: string | null;
  comment?: string | null;
  metadata?: Record<string, unknown>;
}): Promise<{ status: string; feedback_path: string }> {
  return requestJson<{ status: string; feedback_path: string }>("/api/feedback", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function uploadRun(request: {
  file: File;
  mode: "evidence" | "records";
  dataset?: string | null;
  top_k: number;
}): Promise<RunDetail> {
  const form = new FormData();
  form.append("file", request.file);
  form.append("mode", request.mode);
  form.append("top_k", String(request.top_k));
  if (request.dataset) {
    form.append("dataset", request.dataset);
  }
  return requestJson<RunDetail>("/api/runs/upload", {
    method: "POST",
    body: form,
  });
}
