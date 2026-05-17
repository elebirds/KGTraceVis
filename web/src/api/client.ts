import type {
  DashboardBootstrap,
  KGConstructionBuildListResponse,
  KGConstructionBuildRequest,
  KGConstructionBuildResponse,
  KGConstructionOverlayValidationRequest,
  KGConstructionOverlayValidationResponse,
  KGConstructionReviewQueueResponse,
  KGConstructionReviewRequest,
  KGConstructionReviewResponse,
  KGDraftListResponse,
  KGDraftRequest,
  KGMaterialBuildSourcesRequest,
  KGMaterialBuildSourcesResponse,
  KGMaterialChunkListResponse,
  KGMaterialExtractionArtifactListResponse,
  KGMaterialExtractionRequest,
  KGMaterialExtractionResponse,
  KGMaterialExtractionRunListResponse,
  KGMaterialListResponse,
  KGMaterialRegisterUrlRequest,
  KGMaterialRegisterUrlResponse,
  KGMaterialUploadRequest,
  KGMaterialUploadResponse,
  KGSourceDraftRequest,
  KGSourceDraftResponse,
  KGStudioPayload,
  ReviewLedgerListResponse,
  ReviewRequest,
  RunDetail,
  RunSummary,
  UploadRequest
} from "./contracts";

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
  listKGMaterials: () => requestJson<KGMaterialListResponse>("/api/kg/materials"),
  getKGMaterialChunks: (materialId: string) =>
    requestJson<KGMaterialChunkListResponse>(
      `/api/kg/materials/${encodeURIComponent(materialId)}/chunks`
    ),
  getKGMaterialExtractions: (materialId: string) =>
    requestJson<KGMaterialExtractionRunListResponse>(
      `/api/kg/materials/${encodeURIComponent(materialId)}/extractions`
    ),
  getKGMaterialArtifacts: (materialId: string) =>
    requestJson<KGMaterialExtractionArtifactListResponse>(
      `/api/kg/materials/${encodeURIComponent(materialId)}/artifacts`
    ),
  uploadKGMaterial: (request: KGMaterialUploadRequest) => {
    const form = new FormData();
    form.append("file", request.file);
    if (request.title) form.append("title", request.title);
    if (request.scenario) form.append("scenario", request.scenario);
    if (request.source_type) form.append("source_type", request.source_type);
    if (request.notes) form.append("notes", request.notes);
    if (request.metadata) form.append("metadata", JSON.stringify(request.metadata));
    return requestJson<KGMaterialUploadResponse>("/api/kg/materials/upload", {
      method: "POST",
      body: form
    });
  },
  registerKGMaterialUrl: (request: KGMaterialRegisterUrlRequest) =>
    requestJson<KGMaterialRegisterUrlResponse>("/api/kg/materials/register-url", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request)
    }),
  extractKGMaterial: (materialId: string, request: KGMaterialExtractionRequest = {}) =>
    requestJson<KGMaterialExtractionResponse>(`/api/kg/materials/${materialId}/extract`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request)
    }),
  buildKGMaterialSources: (request: KGMaterialBuildSourcesRequest) =>
    requestJson<KGMaterialBuildSourcesResponse>("/api/kg/materials/build-sources", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request)
    }),
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
    if (request.reasoning_profile_id) {
      form.append("reasoning_profile_id", request.reasoning_profile_id);
    }
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
    }),
  listReviews: () => requestJson<ReviewLedgerListResponse>("/api/feedback"),
  listKGDrafts: () => requestJson<KGDraftListResponse>("/api/kg/drafts"),
  submitKGDraft: (request: KGDraftRequest) =>
    requestJson<{ status: string; record: Record<string, unknown> }>("/api/kg/drafts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request)
    }),
  generateKGSourceDraft: (request: KGSourceDraftRequest) =>
    requestJson<KGSourceDraftResponse>("/api/kg/source-draft", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request)
    }),
  buildKGConstruction: (request: KGConstructionBuildRequest) =>
    requestJson<KGConstructionBuildResponse>("/api/kg/construction/build", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request)
    }),
  listKGConstructionBuilds: () =>
    requestJson<KGConstructionBuildListResponse>("/api/kg/construction/builds"),
  getKGConstructionReviewQueue: (runId: string) =>
    requestJson<KGConstructionReviewQueueResponse>(
      `/api/kg/construction/builds/${encodeURIComponent(runId)}/review-queue?review_status=auto&limit=100`
    ),
  reviewKGConstructionItem: (runId: string, request: KGConstructionReviewRequest) =>
    requestJson<KGConstructionReviewResponse>(
      `/api/kg/construction/builds/${encodeURIComponent(runId)}/review`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request)
      }
    ),
  validateKGConstructionOverlay: (
    runId: string,
    request: KGConstructionOverlayValidationRequest = {}
  ) =>
    requestJson<KGConstructionOverlayValidationResponse>(
      `/api/kg/construction/builds/${encodeURIComponent(runId)}/validate-overlay`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request)
      }
    )
};
