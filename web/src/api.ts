import type {
  DashboardBootstrap,
  KGStudioPayload,
  ReviewRequest,
  RunDetail,
  RunSummary,
  UploadRequest
} from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed with ${response.status}`);
  }
  return (await response.json()) as T;
}

export const api = {
  bootstrap: () => requestJson<DashboardBootstrap>("/api/dashboard/bootstrap"),
  kgStudio: () => requestJson<KGStudioPayload>("/api/kg/studio"),
  listRuns: () => requestJson<RunSummary[]>("/api/runs"),
  getRun: (runId: string) => requestJson<RunDetail>(`/api/runs/${runId}`),
  uploadRun: (request: UploadRequest) => {
    const form = new FormData();
    form.append("file", request.file);
    form.append("mode", request.mode);
    form.append("top_k", String(request.top_k));
    if (request.dataset) form.append("dataset", request.dataset);
    if (request.object_name) form.append("object_name", request.object_name);
    if (request.defect_type) form.append("defect_type", request.defect_type);
    if (request.model_preset) form.append("model_preset", request.model_preset);
    return requestJson<RunDetail>("/api/runs/upload", {
      method: "POST",
      body: form
    });
  },
  submitReview: (request: ReviewRequest) =>
    requestJson<{ status: string; record: Record<string, unknown> }>("/api/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request)
    })
};
