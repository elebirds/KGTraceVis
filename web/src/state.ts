import type {
  DashboardBootstrap,
  KGStudioPayload,
  KGSourceDraftResponse,
  RunDetail,
  RunSummary,
  UploadMode
} from "./types";

export interface UploadFormState {
  mode: UploadMode;
  file: File | null;
  dataset: string;
  objectName: string;
  defectType: string;
  modelPreset: string;
  topK: number;
}

export interface AppState {
  bootstrap: DashboardBootstrap | null;
  kgStudio: KGStudioPayload | null;
  runs: RunSummary[];
  selectedRun: RunDetail | null;
  selectedTargetKey: string;
  selectedKGEdgeKey: string;
  upload: UploadFormState;
  loading: boolean;
  error: string | null;
  uploadStatus: string | null;
  reviewNote: string;
  reviewStatus: string | null;
  kgReviewNote: string;
  kgReviewStatus: string | null;
  kgDraftAction: "keep" | "revise" | "reject" | "promote_later";
  kgDraftRelation: string;
  kgDraftEvidence: string;
  kgDraftConfidence: string;
  kgDraftStatus: string | null;
  sourceDraftText: string;
  sourceDraftSourceId: string;
  sourceDraftScenario: string;
  sourceDraftConfidence: string;
  sourceDraftResult: KGSourceDraftResponse | null;
}

export type AppAction =
  | { type: "bootstrapLoaded"; bootstrap: DashboardBootstrap }
  | { type: "kgStudioLoaded"; kgStudio: KGStudioPayload }
  | { type: "runsLoaded"; runs: RunSummary[] }
  | { type: "runLoaded"; run: RunDetail }
  | { type: "uploadStarted" }
  | { type: "uploadCompleted"; run: RunDetail }
  | { type: "uploadChanged"; patch: Partial<UploadFormState> }
  | { type: "targetSelected"; targetKey: string }
  | { type: "kgEdgeSelected"; targetKey: string }
  | { type: "reviewNoteChanged"; note: string }
  | { type: "kgReviewNoteChanged"; note: string }
  | { type: "reviewRecorded"; status: string }
  | { type: "kgReviewRecorded"; status: string }
  | {
      type: "kgDraftChanged";
      patch: Partial<
        Pick<
          AppState,
          "kgDraftAction" | "kgDraftRelation" | "kgDraftEvidence" | "kgDraftConfidence"
        >
      >;
    }
  | { type: "kgDraftRecorded"; status: string }
  | {
      type: "sourceDraftChanged";
      patch: Partial<
        Pick<
          AppState,
          | "sourceDraftText"
          | "sourceDraftSourceId"
          | "sourceDraftScenario"
          | "sourceDraftConfidence"
        >
      >;
    }
  | { type: "sourceDraftGenerated"; result: KGSourceDraftResponse }
  | { type: "loading"; value: boolean }
  | { type: "error"; error: string | null };

export const initialState: AppState = {
  bootstrap: null,
  kgStudio: null,
  runs: [],
  selectedRun: null,
  selectedTargetKey: "",
  selectedKGEdgeKey: "",
  upload: {
    mode: "records",
    file: null,
    dataset: "",
    objectName: "capsule",
    defectType: "",
    modelPreset: "auto",
    topK: 5
  },
  loading: false,
  error: null,
  uploadStatus: null,
  reviewNote: "",
  reviewStatus: null,
  kgReviewNote: "",
  kgReviewStatus: null,
  kgDraftAction: "revise",
  kgDraftRelation: "",
  kgDraftEvidence: "",
  kgDraftConfidence: "",
  kgDraftStatus: null,
  sourceDraftText:
    "ScratchDefect,SUGGESTS_PLAUSIBLE_MECHANISM,MechanicalContact,mvtec,Scratch source wording supports a candidate contact mechanism.",
  sourceDraftSourceId: "dashboard_source",
  sourceDraftScenario: "mvtec",
  sourceDraftConfidence: "0.55",
  sourceDraftResult: null
};

export function reducer(state: AppState, action: AppAction): AppState {
  switch (action.type) {
    case "bootstrapLoaded":
      return {
        ...state,
        bootstrap: action.bootstrap,
        runs: action.bootstrap.recent_runs,
        error: null
      };
    case "kgStudioLoaded":
      return {
        ...state,
        kgStudio: action.kgStudio,
        selectedKGEdgeKey:
          state.selectedKGEdgeKey || action.kgStudio.review_targets[0]?.target_key || "",
        error: null
      };
    case "runsLoaded":
      return { ...state, runs: action.runs, error: null };
    case "runLoaded":
      return {
        ...state,
        selectedRun: action.run,
        selectedTargetKey: action.run.review_targets[0]?.target_key ?? "",
        error: null,
        reviewStatus: null
      };
    case "uploadStarted":
      return { ...state, error: null, uploadStatus: null, reviewStatus: null };
    case "uploadCompleted":
      return {
        ...state,
        selectedRun: action.run,
        selectedTargetKey: action.run.review_targets[0]?.target_key ?? "",
        error: null,
        reviewStatus: null,
        uploadStatus: `Uploaded ${action.run.run.source_filename}; ${action.run.run.case_count} case(s) ready for review.`
      };
    case "uploadChanged":
      return {
        ...state,
        upload: { ...state.upload, ...action.patch },
        uploadStatus: action.patch.file !== undefined ? null : state.uploadStatus
      };
    case "targetSelected":
      return { ...state, selectedTargetKey: action.targetKey, reviewStatus: null };
    case "kgEdgeSelected":
      return {
        ...state,
        selectedKGEdgeKey: action.targetKey,
        kgReviewStatus: null,
        kgDraftStatus: null
      };
    case "reviewNoteChanged":
      return { ...state, reviewNote: action.note };
    case "kgReviewNoteChanged":
      return { ...state, kgReviewNote: action.note };
    case "reviewRecorded":
      return { ...state, reviewStatus: action.status, reviewNote: "" };
    case "kgReviewRecorded":
      return { ...state, kgReviewStatus: action.status, kgReviewNote: "" };
    case "kgDraftChanged":
      return { ...state, ...action.patch, kgDraftStatus: null };
    case "kgDraftRecorded":
      return {
        ...state,
        kgDraftStatus: action.status,
        kgDraftEvidence: "",
        kgDraftConfidence: "",
        kgDraftRelation: ""
      };
    case "sourceDraftChanged":
      return { ...state, ...action.patch };
    case "sourceDraftGenerated":
      return { ...state, sourceDraftResult: action.result, error: null };
    case "loading":
      return { ...state, loading: action.value };
    case "error":
      return { ...state, error: action.error, loading: false };
    default:
      return state;
  }
}
