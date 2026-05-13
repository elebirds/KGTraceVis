import type { DashboardBootstrap, RunDetail, RunSummary, UploadMode } from "./types";

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
  runs: RunSummary[];
  selectedRun: RunDetail | null;
  selectedTargetKey: string;
  upload: UploadFormState;
  loading: boolean;
  error: string | null;
  uploadStatus: string | null;
  reviewNote: string;
  reviewStatus: string | null;
}

export type AppAction =
  | { type: "bootstrapLoaded"; bootstrap: DashboardBootstrap }
  | { type: "runsLoaded"; runs: RunSummary[] }
  | { type: "runLoaded"; run: RunDetail }
  | { type: "uploadStarted" }
  | { type: "uploadCompleted"; run: RunDetail }
  | { type: "uploadChanged"; patch: Partial<UploadFormState> }
  | { type: "targetSelected"; targetKey: string }
  | { type: "reviewNoteChanged"; note: string }
  | { type: "reviewRecorded"; status: string }
  | { type: "loading"; value: boolean }
  | { type: "error"; error: string | null };

export const initialState: AppState = {
  bootstrap: null,
  runs: [],
  selectedRun: null,
  selectedTargetKey: "",
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
  reviewStatus: null
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
    case "reviewNoteChanged":
      return { ...state, reviewNote: action.note };
    case "reviewRecorded":
      return { ...state, reviewStatus: action.status, reviewNote: "" };
    case "loading":
      return { ...state, loading: action.value };
    case "error":
      return { ...state, error: action.error, loading: false };
    default:
      return state;
  }
}
