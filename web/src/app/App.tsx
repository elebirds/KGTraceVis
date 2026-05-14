import { BrowserRouter, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { useCallback, useEffect, useMemo, useReducer } from "react";

import { api } from "../api/client";
import type { ReviewAction } from "../api/contracts";
import { WorkbenchShell } from "../components/layout/WorkbenchShell";
import {
  AnalysisDetailPage,
  AnalysisHistoryPage,
  AnalysisLivePage
} from "../features/analysis/AnalysisPages";
import { ExperimentsPage } from "../features/experiments/ExperimentsPage";
import { HomePage } from "../features/home/HomePage";
import { KGStudioPage } from "../features/kg-studio/KGStudioPages";
import type { KGStudioView } from "../features/kg-studio/KGStudioPages";
import { AppProviders } from "./providers";
import { initialState, reducer } from "../state/app-state";

export function App() {
  return (
    <AppProviders>
      <BrowserRouter>
        <RootLensWorkbench />
      </BrowserRouter>
    </AppProviders>
  );
}

function RootLensWorkbench() {
  const [state, dispatch] = useReducer(reducer, initialState);
  const navigate = useNavigate();
  const selectedTarget = useMemo(
    () =>
      state.selectedRun?.review_targets.find(
        (target) => target.target_key === state.selectedTargetKey
      ),
    [state.selectedRun?.review_targets, state.selectedTargetKey]
  );
  const selectedKGTarget = useMemo(
    () =>
      state.kgStudio?.review_targets.find(
        (target) => target.target_key === state.selectedKGEdgeKey
      ),
    [state.kgStudio?.review_targets, state.selectedKGEdgeKey]
  );

  const loadBootstrap = useCallback(async () => {
    dispatch({ type: "loading", value: true });
    try {
      const bootstrap = await api.bootstrap();
      dispatch({ type: "bootstrapLoaded", bootstrap });
    } catch (error) {
      dispatch({ type: "error", error: (error as Error).message });
    } finally {
      dispatch({ type: "loading", value: false });
    }
  }, []);

  const loadRuns = useCallback(async () => {
    dispatch({ type: "loading", value: true });
    try {
      const runs = await api.listRuns();
      dispatch({ type: "runsLoaded", runs });
    } catch (error) {
      dispatch({ type: "error", error: (error as Error).message });
    } finally {
      dispatch({ type: "loading", value: false });
    }
  }, []);

  const loadKGStudio = useCallback(async () => {
    try {
      const kgStudio = await api.kgStudio();
      dispatch({ type: "kgStudioLoaded", kgStudio });
    } catch (error) {
      dispatch({ type: "error", error: (error as Error).message });
    }
  }, []);

  const loadRun = useCallback(async (runId: string) => {
    dispatch({ type: "loading", value: true });
    try {
      const run = await api.getRun(runId);
      dispatch({ type: "runLoaded", run });
    } catch (error) {
      dispatch({ type: "error", error: (error as Error).message });
    } finally {
      dispatch({ type: "loading", value: false });
    }
  }, []);

  useEffect(() => {
    void loadBootstrap();
    void loadKGStudio();
  }, [loadBootstrap, loadKGStudio]);

  async function refreshAll() {
    await Promise.all([loadBootstrap(), loadKGStudio()]);
  }

  async function openRun(runId: string) {
    navigate(`/analysis/${runId}`);
    await loadRun(runId);
  }

  async function runUpload() {
    if (!state.upload.file) {
      dispatch({ type: "error", error: "Choose a file before uploading." });
      return;
    }
    dispatch({ type: "uploadStarted" });
    dispatch({ type: "loading", value: true });
    try {
      const run = await api.uploadRun({
        file: state.upload.file,
        mode: state.upload.mode,
        dataset: state.upload.dataset || undefined,
        object_name: state.upload.objectName || undefined,
        defect_type: state.upload.defectType || undefined,
        model_preset: state.upload.modelPreset || undefined,
        top_k: state.upload.topK
      });
      dispatch({ type: "uploadCompleted", run });
      await loadRuns();
      navigate(`/analysis/${run.run.run_id}`);
    } catch (error) {
      dispatch({ type: "error", error: (error as Error).message });
    } finally {
      dispatch({ type: "loading", value: false });
    }
  }

  async function submitReview(action: ReviewAction) {
    if (!state.selectedRun || !selectedTarget) return;
    const caseId =
      typeof state.selectedRun.evidence_summary?.case_id === "string" &&
      state.selectedRun.evidence_summary.case_id.trim()
        ? state.selectedRun.evidence_summary.case_id
        : undefined;
    dispatch({ type: "loading", value: true });
    try {
      const response = await api.submitReview({
        run_id: state.selectedRun.run.run_id,
        case_id: caseId,
        target_type: selectedTarget.target_type,
        target_id: selectedTarget.target_id,
        action,
        note: state.reviewNote || undefined,
        source: "kgtracevis-workbench",
        metadata: {
          run_label: state.selectedRun.run.label,
          target_key: selectedTarget.target_key
        }
      });
      dispatch({ type: "reviewRecorded", status: response.status });
    } catch (error) {
      dispatch({ type: "error", error: (error as Error).message });
    } finally {
      dispatch({ type: "loading", value: false });
    }
  }

  async function submitKGReview(action: ReviewAction) {
    if (!selectedKGTarget) return;
    dispatch({ type: "loading", value: true });
    try {
      const response = await api.submitReview({
        target_type: selectedKGTarget.target_type,
        target_id: selectedKGTarget.target_id,
        action,
        note: state.kgReviewNote || undefined,
        source: "kgtracevis-kg-studio",
        metadata: {
          target_key: selectedKGTarget.target_key,
          source: selectedKGTarget.source
        }
      });
      dispatch({ type: "kgReviewRecorded", status: response.status });
    } catch (error) {
      dispatch({ type: "error", error: (error as Error).message });
    } finally {
      dispatch({ type: "loading", value: false });
    }
  }

  async function submitKGDraft() {
    if (!selectedKGTarget) return;
    dispatch({ type: "loading", value: true });
    try {
      const confidence = state.kgDraftConfidence.trim()
        ? Number(state.kgDraftConfidence)
        : undefined;
      const response = await api.submitKGDraft({
        target_type: selectedKGTarget.target_type,
        target_id: selectedKGTarget.target_id,
        target_key: selectedKGTarget.target_key,
        draft_action: state.kgDraftAction,
        proposed_relation: state.kgDraftRelation || undefined,
        proposed_evidence: state.kgDraftEvidence || undefined,
        proposed_confidence: Number.isFinite(confidence) ? confidence : undefined,
        source: "kgtracevis-kg-studio",
        metadata: { selected_source: selectedKGTarget.source }
      });
      dispatch({ type: "kgDraftRecorded", status: response.status });
    } catch (error) {
      dispatch({ type: "error", error: (error as Error).message });
    } finally {
      dispatch({ type: "loading", value: false });
    }
  }

  async function generateSourceDraft() {
    dispatch({ type: "loading", value: true });
    try {
      const result = await api.generateKGSourceDraft({
        source_id: state.sourceDraftSourceId || "dashboard_source",
        source_text: state.sourceDraftText,
        provider: "heuristic",
        default_scenario: state.sourceDraftScenario || "mvtec",
        confidence: Number(state.sourceDraftConfidence || 0.55)
      });
      dispatch({ type: "sourceDraftGenerated", result });
    } catch (error) {
      dispatch({ type: "error", error: (error as Error).message });
    } finally {
      dispatch({ type: "loading", value: false });
    }
  }

  return (
    <WorkbenchShell
      status={state.bootstrap?.status ?? "offline"}
      apiVersion={state.bootstrap?.api_version ?? "api pending"}
      loading={state.loading}
      error={state.error}
      onRefresh={refreshAll}
    >
      <Routes>
        <Route
          path="/"
          element={
            <HomePage
              bootstrap={state.bootstrap}
              kgStudio={state.kgStudio}
              runs={state.runs}
              onOpenAnalysis={() => navigate("/analysis/live")}
              onOpenKGStudio={() => navigate("/kg-studio/overview")}
              onOpenRun={openRun}
            />
          }
        />
        <Route path="/analysis" element={<Navigate to="/analysis/live" replace />} />
        <Route
          path="/analysis/live"
          element={
            <AnalysisLivePage
              bootstrap={state.bootstrap}
              upload={state.upload}
              loading={state.loading}
              uploadStatus={state.uploadStatus}
              onUploadChanged={(patch) => dispatch({ type: "uploadChanged", patch })}
              onRunUpload={runUpload}
            />
          }
        />
        <Route
          path="/analysis/history"
          element={
            <AnalysisHistoryPage
              runs={state.runs}
              selectedRunId={state.selectedRun?.run.run_id ?? null}
              onRefresh={loadRuns}
              onOpenRun={openRun}
            />
          }
        />
        <Route
          path="/analysis/:runId"
          element={
            <AnalysisDetailPage
              run={state.selectedRun}
              loading={state.loading}
              selectedTarget={selectedTarget}
              selectedTargetKey={state.selectedTargetKey}
              reviewNote={state.reviewNote}
              reviewStatus={state.reviewStatus}
              onLoadRun={loadRun}
              onTargetSelected={(targetKey) => dispatch({ type: "targetSelected", targetKey })}
              onReviewNoteChanged={(note) => dispatch({ type: "reviewNoteChanged", note })}
              onSubmitReview={submitReview}
              onOpenHistory={() => navigate("/analysis/history")}
            />
          }
        />
        <Route path="/kg-studio" element={<Navigate to="/kg-studio/overview" replace />} />
        {(["overview", "sources", "graph", "review", "drafts"] as KGStudioView[]).map((view) => (
          <Route
            key={view}
            path={`/kg-studio/${view}`}
            element={
              <KGStudioPage
                view={view}
                payload={state.kgStudio}
                selectedTargetKey={state.selectedKGEdgeKey}
                reviewNote={state.kgReviewNote}
                reviewStatus={state.kgReviewStatus}
                draftAction={state.kgDraftAction}
                draftRelation={state.kgDraftRelation}
                draftEvidence={state.kgDraftEvidence}
                draftConfidence={state.kgDraftConfidence}
                draftStatus={state.kgDraftStatus}
                sourceDraftText={state.sourceDraftText}
                sourceDraftSourceId={state.sourceDraftSourceId}
                sourceDraftScenario={state.sourceDraftScenario}
                sourceDraftConfidence={state.sourceDraftConfidence}
                sourceDraftResult={state.sourceDraftResult}
                onRefresh={loadKGStudio}
                onTargetSelected={(targetKey) => dispatch({ type: "kgEdgeSelected", targetKey })}
                onReviewNoteChanged={(note) => dispatch({ type: "kgReviewNoteChanged", note })}
                onSubmitReview={submitKGReview}
                onDraftChanged={(patch) => dispatch({ type: "kgDraftChanged", patch })}
                onSubmitDraft={submitKGDraft}
                onSourceDraftChanged={(patch) => dispatch({ type: "sourceDraftChanged", patch })}
                onGenerateSourceDraft={generateSourceDraft}
              />
            }
          />
        ))}
        <Route
          path="/experiments"
          element={
            <ExperimentsPage
              runCount={state.runs.length}
              kgEdgeCount={state.kgStudio?.edge_count ?? 0}
              onOpenAnalysis={() => navigate("/analysis/history")}
              onOpenKG={() => navigate("/kg-studio/overview")}
            />
          }
        />
      </Routes>
    </WorkbenchShell>
  );
}
