import {
  AlertTriangle,
  Check,
  ChevronRight,
  Circle,
  Database,
  FileUp,
  GitBranch,
  History,
  Info,
  RefreshCw,
  Send,
  X
} from "lucide-react";
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  type SimulationLinkDatum,
  type SimulationNodeDatum
} from "d3-force";
import { ChangeEvent, FormEvent, useEffect, useMemo, useReducer } from "react";

import { api } from "./api";
import { initialState, reducer } from "./state";
import type {
  ReviewAction,
  KGDraftAction,
  ReviewTarget,
  KGStudioGraphEdge,
  KGStudioGraphNode,
  KGStudioPayload,
  KGStudioReviewTarget,
  KGStudioSource,
  KGStudioSourceDocument,
  KGSourceDraftResponse,
  RunDetail,
  PathGraphEdge,
  PathGraphPath,
  UploadMode,
  UploadModeInfo
} from "./types";

const EXAMPLE_UPLOADS: Record<UploadMode, Array<{ path: string; label: string }>> = {
  records: [
    { path: "data/examples/records/mvtec_records.jsonl", label: "MVTec producer records" },
    { path: "data/examples/records/wm811k_records.jsonl", label: "WM811K producer records" }
  ],
  evidence: [
    { path: "data/examples/mvtec_noisy_morphology_demo.json", label: "Single MVTec evidence" },
    { path: "data/examples/tep_example.json", label: "Single TEP evidence" }
  ],
  image: [
    { path: "data/external/mvtec/<object>/test/<defect>/<image>.png", label: "Local MVTec image" }
  ]
};

function valueText(value: unknown): string {
  if (value === null || value === undefined || value === "") return "unknown";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(3);
  if (Array.isArray(value)) return value.length ? value.join(", ") : "none";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function shortId(value: string): string {
  return value.length > 42 ? `${value.slice(0, 39)}...` : value;
}

export function App() {
  const [state, dispatch] = useReducer(reducer, initialState);
  const uploadModes = state.bootstrap?.upload_modes ?? [];
  const selectedUploadMode = useMemo(
    () => uploadModes.find((mode) => mode.mode === state.upload.mode) ?? null,
    [state.upload.mode, uploadModes]
  );
  const selectedTarget = useMemo(
    () =>
      state.selectedRun?.review_targets.find(
        (item) => item.target_key === state.selectedTargetKey
      ),
    [state.selectedRun?.review_targets, state.selectedTargetKey]
  );
  const selectedKGTarget = useMemo(
    () =>
      state.kgStudio?.review_targets.find(
        (item) => item.target_key === state.selectedKGEdgeKey
      ),
    [state.kgStudio?.review_targets, state.selectedKGEdgeKey]
  );

  useEffect(() => {
    void loadBootstrap();
    void loadKGStudio();
  }, []);

  async function loadBootstrap() {
    dispatch({ type: "loading", value: true });
    try {
      const bootstrap = await api.bootstrap();
      dispatch({ type: "bootstrapLoaded", bootstrap });
    } catch (error) {
      dispatch({ type: "error", error: (error as Error).message });
    } finally {
      dispatch({ type: "loading", value: false });
    }
  }

  async function loadRuns() {
    dispatch({ type: "loading", value: true });
    try {
      const runs = await api.listRuns();
      dispatch({ type: "runsLoaded", runs });
    } catch (error) {
      dispatch({ type: "error", error: (error as Error).message });
    } finally {
      dispatch({ type: "loading", value: false });
    }
  }

  async function loadKGStudio() {
    try {
      const kgStudio = await api.kgStudio();
      dispatch({ type: "kgStudioLoaded", kgStudio });
    } catch (error) {
      dispatch({ type: "error", error: (error as Error).message });
    }
  }

  async function loadRun(runId: string) {
    dispatch({ type: "loading", value: true });
    try {
      const run = await api.getRun(runId);
      dispatch({ type: "runLoaded", run });
    } catch (error) {
      dispatch({ type: "error", error: (error as Error).message });
    } finally {
      dispatch({ type: "loading", value: false });
    }
  }

  async function submitUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
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
        source: "rootlens-dashboard",
        metadata: {
          run_label: state.selectedRun.run.label,
          target_key: selectedTarget.target_key
        }
      });
      dispatch({
        type: "reviewRecorded",
        status: `${response.status} for ${selectedTarget.target_key}`
      });
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
        target_type: "edge",
        target_id: selectedKGTarget.target_id,
        action,
        note: state.kgReviewNote || undefined,
        source: "rootlens-kg-studio",
        metadata: {
          target_key: selectedKGTarget.target_key,
          candidate_dir: state.kgStudio?.candidate_dir,
          source_registry_path: state.kgStudio?.source_registry_path
        }
      });
      dispatch({
        type: "kgReviewRecorded",
        status: `${response.status} for ${selectedKGTarget.target_key}`
      });
    } catch (error) {
      dispatch({ type: "error", error: (error as Error).message });
    } finally {
      dispatch({ type: "loading", value: false });
    }
  }

  async function submitKGDraft() {
    if (!selectedKGTarget) return;
    const confidenceText = state.kgDraftConfidence.trim();
    const proposedConfidence = confidenceText ? Number(confidenceText) : undefined;
    if (proposedConfidence !== undefined && Number.isNaN(proposedConfidence)) {
      dispatch({ type: "error", error: "Draft confidence must be a number between 0 and 1." });
      return;
    }
    dispatch({ type: "loading", value: true });
    try {
      const response = await api.submitKGDraft({
        target_type: "edge",
        target_id: selectedKGTarget.target_id,
        target_key: selectedKGTarget.target_key,
        draft_action: state.kgDraftAction,
        proposed_relation: state.kgDraftRelation || undefined,
        proposed_evidence: state.kgDraftEvidence || undefined,
        proposed_confidence: proposedConfidence,
        note: state.kgReviewNote || undefined,
        source: "rootlens-kg-studio",
        metadata: {
          candidate_dir: state.kgStudio?.candidate_dir,
          source_registry_path: state.kgStudio?.source_registry_path
        }
      });
      dispatch({
        type: "kgDraftRecorded",
        status: `${response.status} for ${selectedKGTarget.target_key}`
      });
    } catch (error) {
      dispatch({ type: "error", error: (error as Error).message });
    } finally {
      dispatch({ type: "loading", value: false });
    }
  }

  async function generateSourceDraft() {
    const confidence = Number(state.sourceDraftConfidence);
    if (Number.isNaN(confidence)) {
      dispatch({ type: "error", error: "Source draft confidence must be numeric." });
      return;
    }
    dispatch({ type: "loading", value: true });
    try {
      const result = await api.generateKGSourceDraft({
        source_id: state.sourceDraftSourceId || "dashboard_source",
        source_text: state.sourceDraftText,
        provider: "heuristic",
        default_scenario: state.sourceDraftScenario || "shared",
        confidence
      });
      dispatch({ type: "sourceDraftGenerated", result });
    } catch (error) {
      dispatch({ type: "error", error: (error as Error).message });
    } finally {
      dispatch({ type: "loading", value: false });
    }
  }

  const presets = state.bootstrap?.mvtec_model_presets.presets ?? [];
  const apiConnected = state.bootstrap?.status === "ok";

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">RootLens</p>
          <h1>Evidence Analysis Workspace</h1>
        </div>
        <div className="topbar-actions">
          <span className={`connection-pill ${apiConnected ? "connected" : "disconnected"}`}>
            <Circle size={10} fill="currentColor" />
            {apiConnected ? `API ${state.bootstrap?.api_version}` : "API connecting"}
          </span>
          <button className="icon-button" onClick={() => void loadBootstrap()} title="Refresh">
            <RefreshCw className={state.loading ? "spin" : ""} size={18} />
          </button>
        </div>
      </header>

      {state.loading && (
        <div className="status status-info" aria-live="polite">
          <RefreshCw className="spin" size={16} />
          <span>Working with the local RootLens API...</span>
        </div>
      )}

      {state.error && (
        <div className="status status-error" aria-live="assertive">
          <AlertTriangle size={16} />
          <span>{state.error}</span>
        </div>
      )}

      <section className="workspace-grid">
        <aside className="panel upload-panel">
          <div className="panel-heading">
            <FileUp size={18} />
            <h2>Upload</h2>
          </div>
          <form onSubmit={(event) => void submitUpload(event)} className="stack">
            <label>
              Mode
              <select
                value={state.upload.mode}
                onChange={(event) =>
                  dispatch({
                    type: "uploadChanged",
                    patch: { mode: event.target.value as UploadMode }
                  })
                }
              >
                {uploadModes.length === 0 && <option value={state.upload.mode}>Loading modes...</option>}
                {uploadModes.map((mode) => (
                  <option key={mode.mode} value={mode.mode}>
                    {mode.label}
                  </option>
                ))}
              </select>
            </label>
            <UploadModeGuidance mode={selectedUploadMode} uploadMode={state.upload.mode} />
            <label>
              File
              <input
                type="file"
                accept={selectedUploadMode?.accepted_extensions.join(",")}
                onChange={(event: ChangeEvent<HTMLInputElement>) =>
                  dispatch({
                    type: "uploadChanged",
                    patch: { file: event.target.files?.[0] ?? null }
                  })
                }
              />
              <span className="field-hint">
                {state.upload.file
                  ? `${state.upload.file.name} selected`
                  : "Choose a local example file from the paths above."}
              </span>
            </label>
            <div className="inline-fields">
              <label>
                Dataset
                <select
                  value={state.upload.dataset}
                  onChange={(event) =>
                    dispatch({ type: "uploadChanged", patch: { dataset: event.target.value } })
                  }
                >
                  <option value="">auto</option>
                  {state.bootstrap?.supported_datasets.map((dataset) => (
                    <option key={dataset} value={dataset}>
                      {dataset}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Top K
                <input
                  type="number"
                  min={1}
                  max={20}
                  value={state.upload.topK}
                  onChange={(event) =>
                    dispatch({
                      type: "uploadChanged",
                      patch: { topK: Number(event.target.value) }
                    })
                  }
                />
              </label>
            </div>
            {state.upload.mode === "image" && (
              <>
                <label>
                  Object
                  <input
                    value={state.upload.objectName}
                    onChange={(event) =>
                      dispatch({
                        type: "uploadChanged",
                        patch: { objectName: event.target.value }
                      })
                    }
                  />
                </label>
                <div className="inline-fields">
                  <label>
                    Preset
                    <select
                      value={state.upload.modelPreset}
                      onChange={(event) =>
                        dispatch({
                          type: "uploadChanged",
                          patch: { modelPreset: event.target.value }
                        })
                      }
                    >
                      <option value="auto">auto</option>
                      {presets.map((preset) => (
                        <option key={String(preset.preset)} value={String(preset.preset)}>
                          {String(preset.preset)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Defect
                    <input
                      value={state.upload.defectType}
                      onChange={(event) =>
                        dispatch({
                          type: "uploadChanged",
                          patch: { defectType: event.target.value }
                        })
                      }
                    />
                  </label>
                </div>
              </>
            )}
            <button className="primary-button" disabled={state.loading}>
              <Send size={16} />
              {state.loading ? "Analyzing" : "Analyze"}
            </button>
            {state.uploadStatus && (
              <div className="inline-status status-success" aria-live="polite">
                <Check size={16} />
                <span>{state.uploadStatus}</span>
              </div>
            )}
          </form>
        </aside>

        <aside className="panel history-panel">
          <div className="panel-heading">
            <History size={18} />
            <h2>Run History</h2>
            <button className="ghost-button" onClick={() => void loadRuns()}>
              Refresh
            </button>
          </div>
          <div className="run-list">
            {state.runs.length > 0 ? (
              state.runs.map((run) => (
                <button
                  key={run.run_id}
                  className={`run-row ${
                    state.selectedRun?.run.run_id === run.run_id ? "selected" : ""
                  }`}
                  onClick={() => void loadRun(run.run_id)}
                >
                  <span className="run-title">{run.label}</span>
                  <span className="run-meta">
                    {run.mode} · {run.dataset ?? "auto"} · {run.case_count} cases
                  </span>
                  <span className="run-meta">{new Date(run.created_at).toLocaleString()}</span>
                </button>
              ))
            ) : (
              <EmptyMessage
                title="No runs yet"
                body="Upload producer records or evidence JSON to create a local review run."
              />
            )}
          </div>
        </aside>

        <section className="detail-region">
          {state.selectedRun ? (
            <RunDetailView
              run={state.selectedRun}
              selectedTarget={selectedTarget}
              selectedTargetKey={state.selectedTargetKey}
              reviewNote={state.reviewNote}
              reviewStatus={state.reviewStatus}
              onTargetSelected={(targetKey) =>
                dispatch({ type: "targetSelected", targetKey })
              }
              onReviewNoteChanged={(note) =>
                dispatch({ type: "reviewNoteChanged", note })
              }
              onSubmitReview={(action) => void submitReview(action)}
            />
          ) : (
            <div className="empty-state">
              <GitBranch size={28} />
              <div>
                <strong>No run selected</strong>
                <p>Select a history item or upload an example record file to inspect candidate paths, provenance, and review targets.</p>
              </div>
            </div>
          )}
        </section>

        <section className="kg-studio-region">
          <KGStudioPanel
            payload={state.kgStudio}
            selectedTarget={selectedKGTarget}
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
            onRefresh={() => void loadKGStudio()}
            onTargetSelected={(targetKey) =>
              dispatch({ type: "kgEdgeSelected", targetKey })
            }
            onReviewNoteChanged={(note) =>
              dispatch({ type: "kgReviewNoteChanged", note })
            }
            onSubmitReview={(action) => void submitKGReview(action)}
            onDraftChanged={(patch) =>
              dispatch({ type: "kgDraftChanged", patch })
            }
            onSubmitDraft={() => void submitKGDraft()}
            onSourceDraftChanged={(patch) =>
              dispatch({ type: "sourceDraftChanged", patch })
            }
            onGenerateSourceDraft={() => void generateSourceDraft()}
          />
        </section>
      </section>
    </main>
  );
}

function KGStudioPanel({
  payload,
  selectedTarget,
  selectedTargetKey,
  reviewNote,
  reviewStatus,
  draftAction,
  draftRelation,
  draftEvidence,
  draftConfidence,
  draftStatus,
  sourceDraftText,
  sourceDraftSourceId,
  sourceDraftScenario,
  sourceDraftConfidence,
  sourceDraftResult,
  onRefresh,
  onTargetSelected,
  onReviewNoteChanged,
  onSubmitReview,
  onDraftChanged,
  onSubmitDraft,
  onSourceDraftChanged,
  onGenerateSourceDraft
}: {
  payload: KGStudioPayload | null;
  selectedTarget: KGStudioReviewTarget | undefined;
  selectedTargetKey: string;
  reviewNote: string;
  reviewStatus: string | null;
  draftAction: KGDraftAction;
  draftRelation: string;
  draftEvidence: string;
  draftConfidence: string;
  draftStatus: string | null;
  sourceDraftText: string;
  sourceDraftSourceId: string;
  sourceDraftScenario: string;
  sourceDraftConfidence: string;
  sourceDraftResult: KGSourceDraftResponse | null;
  onRefresh: () => void;
  onTargetSelected: (targetKey: string) => void;
  onReviewNoteChanged: (note: string) => void;
  onSubmitReview: (action: ReviewAction) => void;
  onDraftChanged: (
    patch: Partial<{
      kgDraftAction: KGDraftAction;
      kgDraftRelation: string;
      kgDraftEvidence: string;
      kgDraftConfidence: string;
    }>
  ) => void;
  onSubmitDraft: () => void;
  onSourceDraftChanged: (
    patch: Partial<{
      sourceDraftText: string;
      sourceDraftSourceId: string;
      sourceDraftScenario: string;
      sourceDraftConfidence: string;
    }>
  ) => void;
  onGenerateSourceDraft: () => void;
}) {
  const selectedEdge = payload?.graph_edges.find(
    (edge) => edge.target_key === selectedTargetKey
  );
  return (
    <section className="panel kg-studio-panel">
      <div className="panel-heading">
        <Database size={18} />
        <h2>KG Studio</h2>
        <button className="ghost-button" onClick={onRefresh}>
          Refresh
        </button>
      </div>
      {payload ? (
        <>
          <p className="claim-boundary">{payload.note}</p>
          <div className="kg-metrics">
            <Metric label="status" value={payload.status} />
            <Metric label="nodes" value={payload.node_count} />
            <Metric label="edges" value={payload.edge_count} />
            <Metric
              label="validation"
              value={payload.validation_summary?.passed ?? "unknown"}
            />
            <Metric
              label="mean confidence"
              value={payload.confidence_summary.mean ?? "unknown"}
            />
          </div>
          <div className="kg-studio-grid">
            <section>
              <h3>Sources</h3>
              <SourceToKGDraftForm
                sourceText={sourceDraftText}
                sourceId={sourceDraftSourceId}
                scenario={sourceDraftScenario}
                confidence={sourceDraftConfidence}
                result={sourceDraftResult}
                onChanged={onSourceDraftChanged}
                onGenerate={onGenerateSourceDraft}
              />
              <KGSourceList sources={payload.sources} />
              <h3>Documents</h3>
              <KGSourceDocumentList documents={payload.source_documents} />
            </section>
            <section>
              <h3>Candidate Edge Graph</h3>
              <KGForceGraph
                nodes={payload.graph_nodes}
                edges={payload.graph_edges}
                selectedTargetKey={selectedTargetKey}
                onTargetSelected={onTargetSelected}
              />
              <KGEdgePreview
                edges={payload.graph_edges}
                selectedTargetKey={selectedTargetKey}
                onTargetSelected={onTargetSelected}
              />
            </section>
            <section>
              <h3>Edge Provenance</h3>
              <KGEdgeInspector edge={selectedEdge} />
              <KGDraftForm
                selectedTarget={selectedTarget}
                draftAction={draftAction}
                draftRelation={draftRelation}
                draftEvidence={draftEvidence}
                draftConfidence={draftConfidence}
                draftStatus={draftStatus}
                onDraftChanged={onDraftChanged}
                onSubmitDraft={onSubmitDraft}
              />
              <div className="kg-review-box">
                <select
                  value={selectedTargetKey}
                  onChange={(event) => onTargetSelected(event.target.value)}
                  disabled={!payload.review_targets.length}
                >
                  {payload.review_targets.length > 0 ? (
                    payload.review_targets.slice(0, 80).map((target) => (
                      <option key={target.target_key} value={target.target_key}>
                        {shortId(target.label)}
                      </option>
                    ))
                  ) : (
                    <option value="">No KG edge targets</option>
                  )}
                </select>
                <input
                  value={reviewNote}
                  onChange={(event) => onReviewNoteChanged(event.target.value)}
                  placeholder="optional KG edge review note"
                  disabled={!selectedTarget}
                />
                <div className="kg-review-actions">
                  <button onClick={() => onSubmitReview("accept")} disabled={!selectedTarget}>
                    <Check size={16} />
                    Accept
                  </button>
                  <button onClick={() => onSubmitReview("reject")} disabled={!selectedTarget}>
                    <X size={16} />
                    Reject
                  </button>
                  <button
                    onClick={() => onSubmitReview("needs_review")}
                    disabled={!selectedTarget}
                  >
                    Needs review
                  </button>
                </div>
                {reviewStatus && <p className="muted">Feedback {reviewStatus}.</p>}
              </div>
            </section>
          </div>
        </>
      ) : (
        <EmptyMessage
          title="KG Studio loading"
          body="Reading source registry and candidate KG artifacts from local project paths."
        />
      )}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: unknown }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{valueText(value)}</strong>
    </div>
  );
}

function KGSourceList({ sources }: { sources: KGStudioSource[] }) {
  if (!sources.length) return <p className="muted">No source registry rows found.</p>;
  return (
    <ul className="compact-list">
      {sources.slice(0, 10).map((source) => (
        <li key={source.source_id}>
          <strong>{source.source_id}</strong>
          <span>{source.used_for}</span>
          <span>{source.path_or_url}</span>
        </li>
      ))}
    </ul>
  );
}

function SourceToKGDraftForm({
  sourceText,
  sourceId,
  scenario,
  confidence,
  result,
  onChanged,
  onGenerate
}: {
  sourceText: string;
  sourceId: string;
  scenario: string;
  confidence: string;
  result: KGSourceDraftResponse | null;
  onChanged: (
    patch: Partial<{
      sourceDraftText: string;
      sourceDraftSourceId: string;
      sourceDraftScenario: string;
      sourceDraftConfidence: string;
    }>
  ) => void;
  onGenerate: () => void;
}) {
  return (
    <div className="source-draft-box">
      <strong>Source-to-KG Draft</strong>
      <div className="source-draft-fields">
        <input
          value={sourceId}
          onChange={(event) => onChanged({ sourceDraftSourceId: event.target.value })}
          placeholder="source id"
        />
        <input
          value={scenario}
          onChange={(event) => onChanged({ sourceDraftScenario: event.target.value })}
          placeholder="scenario"
        />
        <input
          value={confidence}
          onChange={(event) => onChanged({ sourceDraftConfidence: event.target.value })}
          placeholder="confidence"
        />
      </div>
      <textarea
        value={sourceText}
        onChange={(event) => onChanged({ sourceDraftText: event.target.value })}
        placeholder="head,relation,tail,scenario,evidence"
      />
      <button onClick={onGenerate}>Generate candidates</button>
      {result && (
        <div className="source-draft-results">
          <span>{result.candidate_edges.length} candidate edge(s)</span>
          {result.candidate_edges.slice(0, 4).map((edge) => (
            <code key={edge.edge_id}>{edge.edge_id}</code>
          ))}
        </div>
      )}
    </div>
  );
}

function KGSourceDocumentList({ documents }: { documents: KGStudioSourceDocument[] }) {
  if (!documents.length) return <p className="muted">No source documents found.</p>;
  return (
    <ul className="compact-list">
      {documents.slice(0, 8).map((document) => (
        <li key={document.path}>
          <strong>{document.title}</strong>
          <span>{document.path}</span>
        </li>
      ))}
    </ul>
  );
}

interface ForceNode extends SimulationNodeDatum {
  id: string;
  label: string;
  nodeType: string;
  scenario: string;
}

interface ForceLink extends SimulationLinkDatum<ForceNode> {
  edge: KGStudioGraphEdge;
}

function KGForceGraph({
  nodes,
  edges,
  selectedTargetKey,
  onTargetSelected
}: {
  nodes: KGStudioGraphNode[];
  edges: KGStudioGraphEdge[];
  selectedTargetKey: string;
  onTargetSelected: (targetKey: string) => void;
}) {
  const layout = useMemo(() => buildForceLayout(nodes, edges), [nodes, edges]);
  if (!layout.nodes.length || !layout.links.length) {
    return null;
  }
  const nodeById = new Map(layout.nodes.map((node) => [node.id, node]));
  return (
    <svg className="kg-force-graph" viewBox="0 0 760 360" role="img" aria-label="Candidate KG force graph">
      <g>
        {layout.links.map((link) => {
          const source = forceNode(link.source, nodeById);
          const target = forceNode(link.target, nodeById);
          if (!source || !target) return null;
          const selected = selectedTargetKey === link.edge.target_key;
          return (
            <g key={link.edge.edge_id}>
              <line
                className={selected ? "selected" : ""}
                x1={source.x}
                y1={source.y}
                x2={target.x}
                y2={target.y}
              />
              <circle
                className="svg-edge-hit"
                cx={((source.x ?? 0) + (target.x ?? 0)) / 2}
                cy={((source.y ?? 0) + (target.y ?? 0)) / 2}
                r={selected ? 8 : 5}
                onClick={() => onTargetSelected(link.edge.target_key)}
              />
            </g>
          );
        })}
      </g>
      <g>
        {layout.nodes.map((node) => (
          <g key={node.id} transform={`translate(${node.x ?? 0}, ${node.y ?? 0})`}>
            <circle
              className={`kg-node-dot ${node.nodeType}`}
              r={node.nodeType === "RootCause" ? 16 : 13}
            />
            <text y={-20}>{shortId(node.label)}</text>
          </g>
        ))}
      </g>
    </svg>
  );
}

function buildForceLayout(
  graphNodes: KGStudioGraphNode[],
  graphEdges: KGStudioGraphEdge[]
): { nodes: ForceNode[]; links: ForceLink[] } {
  const edgeSlice = graphEdges.slice(0, 60);
  const nodeRows = new Map(graphNodes.map((node) => [node.node_id, node]));
  for (const edge of edgeSlice) {
    if (!nodeRows.has(edge.head)) {
      nodeRows.set(edge.head, {
        node_id: edge.head,
        label: edge.head,
        node_type: "Unknown",
        scenario: edge.scenario,
        description: ""
      });
    }
    if (!nodeRows.has(edge.tail)) {
      nodeRows.set(edge.tail, {
        node_id: edge.tail,
        label: edge.tail,
        node_type: "Unknown",
        scenario: edge.scenario,
        description: ""
      });
    }
  }
  const nodes: ForceNode[] = Array.from(nodeRows.values())
    .slice(0, 80)
    .map((node) => ({
      id: node.node_id,
      label: node.label,
      nodeType: node.node_type,
      scenario: node.scenario
    }));
  const available = new Set(nodes.map((node) => node.id));
  const links: ForceLink[] = edgeSlice
    .filter((edge) => available.has(edge.head) && available.has(edge.tail))
    .map((edge) => ({
      source: edge.head,
      target: edge.tail,
      edge
    }));
  forceSimulation(nodes)
    .force(
      "link",
      forceLink<ForceNode, ForceLink>(links)
        .id((node) => node.id)
        .distance(96)
        .strength(0.45)
    )
    .force("charge", forceManyBody().strength(-210))
    .force("collide", forceCollide<ForceNode>().radius(35))
    .force("center", forceCenter(380, 180))
    .stop()
    .tick(140);
  for (const node of nodes) {
    node.x = Math.min(725, Math.max(35, node.x ?? 380));
    node.y = Math.min(330, Math.max(35, node.y ?? 180));
  }
  return { nodes, links };
}

function forceNode(
  value: string | number | ForceNode | undefined,
  nodes: Map<string, ForceNode>
): ForceNode | undefined {
  if (typeof value === "object" && value !== null) return value;
  if (value === undefined) return undefined;
  return nodes.get(String(value));
}

function KGDraftForm({
  selectedTarget,
  draftAction,
  draftRelation,
  draftEvidence,
  draftConfidence,
  draftStatus,
  onDraftChanged,
  onSubmitDraft
}: {
  selectedTarget: KGStudioReviewTarget | undefined;
  draftAction: KGDraftAction;
  draftRelation: string;
  draftEvidence: string;
  draftConfidence: string;
  draftStatus: string | null;
  onDraftChanged: (
    patch: Partial<{
      kgDraftAction: KGDraftAction;
      kgDraftRelation: string;
      kgDraftEvidence: string;
      kgDraftConfidence: string;
    }>
  ) => void;
  onSubmitDraft: () => void;
}) {
  return (
    <div className="kg-draft-form">
      <strong>Draft Adjustment</strong>
      <select
        value={draftAction}
        onChange={(event) =>
          onDraftChanged({ kgDraftAction: event.target.value as KGDraftAction })
        }
        disabled={!selectedTarget}
      >
        <option value="revise">revise</option>
        <option value="keep">keep</option>
        <option value="reject">reject</option>
        <option value="promote_later">promote later</option>
      </select>
      <input
        value={draftRelation}
        onChange={(event) => onDraftChanged({ kgDraftRelation: event.target.value })}
        placeholder="proposed relation"
        disabled={!selectedTarget}
      />
      <input
        value={draftConfidence}
        onChange={(event) => onDraftChanged({ kgDraftConfidence: event.target.value })}
        placeholder="proposed confidence 0-1"
        disabled={!selectedTarget}
      />
      <textarea
        value={draftEvidence}
        onChange={(event) => onDraftChanged({ kgDraftEvidence: event.target.value })}
        placeholder="proposed evidence or adjustment rationale"
        disabled={!selectedTarget}
      />
      <button onClick={onSubmitDraft} disabled={!selectedTarget}>
        Save draft
      </button>
      {draftStatus && <p className="muted">Draft {draftStatus}.</p>}
    </div>
  );
}

function KGEdgePreview({
  edges,
  selectedTargetKey,
  onTargetSelected
}: {
  edges: KGStudioGraphEdge[];
  selectedTargetKey: string;
  onTargetSelected: (targetKey: string) => void;
}) {
  if (!edges.length) {
    return (
      <EmptyMessage
        title="No candidate edges"
        body="Generate candidate KG artifacts first, then refresh this panel."
      />
    );
  }
  return (
    <div className="kg-edge-list">
      {edges.slice(0, 40).map((edge) => (
        <button
          key={edge.edge_id}
          className={selectedTargetKey === edge.target_key ? "selected" : ""}
          onClick={() => onTargetSelected(edge.target_key)}
        >
          <span>{edge.head}</span>
          <strong>{edge.relation}</strong>
          <span>{edge.tail}</span>
          <small>
            {edge.scenario} · {edge.source} · {valueText(edge.confidence)}
          </small>
        </button>
      ))}
    </div>
  );
}

function KGEdgeInspector({ edge }: { edge: KGStudioGraphEdge | undefined }) {
  if (!edge) {
    return <p className="muted">Select a candidate KG edge to inspect provenance.</p>;
  }
  return (
    <dl className="kg-edge-inspector">
      <div>
        <dt>edge</dt>
        <dd>{shortId(edge.edge_id)}</dd>
      </div>
      <div>
        <dt>scenario</dt>
        <dd>{edge.scenario}</dd>
      </div>
      <div>
        <dt>source</dt>
        <dd>{edge.source}</dd>
      </div>
      <div>
        <dt>confidence</dt>
        <dd>{valueText(edge.confidence)}</dd>
      </div>
      <div>
        <dt>review status</dt>
        <dd>{edge.review_status}</dd>
      </div>
      <div className="kg-edge-evidence">
        <dt>evidence</dt>
        <dd>{edge.evidence}</dd>
      </div>
    </dl>
  );
}

interface RunDetailProps {
  run: RunDetail;
  selectedTarget: ReviewTarget | undefined;
  selectedTargetKey: string;
  reviewNote: string;
  reviewStatus: string | null;
  onTargetSelected: (targetId: string) => void;
  onReviewNoteChanged: (note: string) => void;
  onSubmitReview: (action: ReviewAction) => void;
}

function RunDetailView({
  run,
  selectedTarget,
  selectedTargetKey,
  reviewNote,
  reviewStatus,
  onTargetSelected,
  onReviewNoteChanged,
  onSubmitReview
}: RunDetailProps) {
  const evidence = run.evidence_summary ?? {};
  const pathGraph = run.path_graph ?? {
    paths: [],
    path_count: 0,
    node_count: 0,
    edge_count: 0
  };
  return (
    <div className="detail-grid">
      <section className="panel">
        <div className="panel-heading">
          <ChevronRight size={18} />
          <h2>{run.run.label}</h2>
        </div>
        <p className="claim-boundary">{run.claim_boundary}</p>
        <div className="kv-grid">
          {["case_id", "dataset", "object", "anomaly_type", "location", "morphology", "confidence"].map(
            (key) => (
              <div key={key}>
                <span>{key}</span>
                <strong>{valueText(evidence[key])}</strong>
              </div>
            )
          )}
        </div>
      </section>

      <section className="panel">
        <div className="panel-heading">
          <Check size={18} />
          <h2>Workflow</h2>
        </div>
        <ol className="steps">
          {run.workflow_steps.map((step) => (
            <li key={step.step_id}>
              <strong>{step.title}</strong>
              <span>{step.summary}</span>
            </li>
          ))}
        </ol>
      </section>

      <ReasoningWorkspace
        paths={pathGraph.paths}
        selectedTarget={selectedTarget}
        onTargetSelected={onTargetSelected}
      />

      <section className="panel">
        <h2>Linked Entities</h2>
        <CompactList items={run.linked_entities} idField="link_id" labelField="selected_entity_id" />
      </section>

      <section className="panel">
        <h2>Correction Candidates</h2>
        <CompactList
          items={run.correction_candidates}
          idField="candidate_id"
          labelField="suggested_value"
        />
      </section>

      <section className="panel wide review-panel">
        <h2>Review</h2>
        <ReviewQueue
          targets={run.review_targets}
          selectedTargetKey={selectedTargetKey}
          onTargetSelected={onTargetSelected}
        />
        <div className="review-controls">
          <select
            className="review-target-select"
            value={selectedTargetKey}
            onChange={(event) => onTargetSelected(event.target.value)}
            disabled={!run.review_targets.length}
          >
            {run.review_targets.length > 0 ? (
              run.review_targets.map((target) => (
                <option key={target.target_key} value={target.target_key}>
                  {target.target_type} · {shortId(target.label)}
                </option>
              ))
            ) : (
              <option value="">No review targets</option>
            )}
          </select>
          <input
            className="review-note"
            value={reviewNote}
            onChange={(event) => onReviewNoteChanged(event.target.value)}
            placeholder="optional review note"
            disabled={!selectedTarget}
          />
          <button onClick={() => onSubmitReview("accept")} disabled={!selectedTarget}>
            <Check size={16} />
            Accept
          </button>
          <button onClick={() => onSubmitReview("reject")} disabled={!selectedTarget}>
            <X size={16} />
            Reject
          </button>
          <button onClick={() => onSubmitReview("needs_review")} disabled={!selectedTarget}>
            Needs review
          </button>
        </div>
        {selectedTarget ? (
          <p className="muted">Stable target key: {selectedTarget.target_key}</p>
        ) : (
          <p className="muted">No feedback target is available for this run.</p>
        )}
        {reviewStatus && (
          <div className="inline-status status-success" aria-live="polite">
            <Check size={16} />
            <span>Feedback {reviewStatus}.</span>
          </div>
        )}
      </section>
    </div>
  );
}

function ReasoningWorkspace({
  paths,
  selectedTarget,
  onTargetSelected
}: {
  paths: PathGraphPath[];
  selectedTarget: ReviewTarget | undefined;
  onTargetSelected: (targetKey: string) => void;
}) {
  const selectedPath =
    paths.find((path) => path.target_key === selectedTarget?.target_key) ??
    paths.find((path) =>
      path.edges.some((edge) => edge.target_key === selectedTarget?.target_key)
    ) ??
    paths[0];
  const selectedEdge =
    selectedTarget?.target_type === "edge"
      ? selectedPath?.edges.find((edge) => edge.target_key === selectedTarget.target_key)
      : selectedPath?.edges[0];

  return (
    <section className="panel wide reasoning-workspace">
      <div className="panel-heading">
        <GitBranch size={18} />
        <h2>Path Graph</h2>
      </div>
      {paths.length > 0 && selectedPath ? (
        <div className="path-workspace-grid">
          <div className="path-picker" aria-label="Candidate path list">
            {paths.slice(0, 8).map((path, index) => (
              <button
                key={path.path_id}
                className={`path-card ${selectedPath.path_id === path.path_id ? "selected" : ""}`}
                onClick={() => onTargetSelected(path.target_key)}
              >
                <span className="path-card-rank">#{index + 1}</span>
                <span>
                  <strong>{valueText(path.target_entity_id)}</strong>
                  <small>
                    score {valueText(path.score)} · confidence {valueText(path.confidence)}
                  </small>
                </span>
              </button>
            ))}
          </div>
          <div className="path-graph-panel">
            <PathNodeChain
              path={selectedPath}
              selectedTargetKey={selectedTarget?.target_key ?? ""}
              onTargetSelected={onTargetSelected}
            />
            <div className="supporting-evidence">
              <strong>Supporting Evidence</strong>
              {selectedPath.supporting_evidence.length > 0 ? (
                <ul>
                  {selectedPath.supporting_evidence.slice(0, 4).map((item, index) => (
                    <li key={`${selectedPath.path_id}-support-${index}`}>{valueText(item)}</li>
                  ))}
                </ul>
              ) : (
                <p className="muted">No supporting evidence text attached to this path.</p>
              )}
            </div>
          </div>
          <ProvenanceCard edge={selectedEdge} />
        </div>
      ) : (
        <EmptyMessage
          title="No path graph available"
          body="This run returned no candidate reasoning paths. Linked entities and corrections can still be reviewed below."
        />
      )}
    </section>
  );
}

function PathNodeChain({
  path,
  selectedTargetKey,
  onTargetSelected
}: {
  path: PathGraphPath;
  selectedTargetKey: string;
  onTargetSelected: (targetKey: string) => void;
}) {
  return (
    <div className="node-chain" aria-label={`Selected path ${path.path_id}`}>
      {path.nodes.map((node, index) => {
        const edge = path.edges[index];
        return (
          <div className="node-chain-step" key={`${path.path_id}-${node.node_id}-${index}`}>
            <button className={`graph-node ${node.role}`}>
              <span>{node.label}</span>
              <small>{node.node_id}</small>
            </button>
            {edge && (
              <button
                className={`graph-edge ${selectedTargetKey === edge.target_key ? "selected" : ""}`}
                onClick={() => onTargetSelected(edge.target_key)}
                title={edge.evidence ?? edge.edge_id}
              >
                <span>{edge.relation}</span>
                <small>{valueText(edge.confidence)}</small>
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}

function ProvenanceCard({ edge }: { edge: PathGraphEdge | undefined }) {
  if (!edge) {
    return (
      <div className="provenance-card">
        <strong>Provenance</strong>
        <p className="muted">Select a path edge to inspect source evidence.</p>
      </div>
    );
  }
  return (
    <div className="provenance-card">
      <strong>Provenance</strong>
      <dl>
        <div>
          <dt>edge</dt>
          <dd>{shortId(edge.edge_id)}</dd>
        </div>
        <div>
          <dt>relation</dt>
          <dd>{edge.relation}</dd>
        </div>
        <div>
          <dt>source</dt>
          <dd>{valueText(edge.source)}</dd>
        </div>
        <div>
          <dt>confidence</dt>
          <dd>{valueText(edge.confidence)}</dd>
        </div>
        <div>
          <dt>review</dt>
          <dd>{valueText(edge.review_status)}</dd>
        </div>
        <div className="provenance-evidence">
          <dt>evidence</dt>
          <dd>{valueText(edge.evidence)}</dd>
        </div>
      </dl>
    </div>
  );
}

function ReviewQueue({
  targets,
  selectedTargetKey,
  onTargetSelected
}: {
  targets: ReviewTarget[];
  selectedTargetKey: string;
  onTargetSelected: (targetKey: string) => void;
}) {
  if (!targets.length) {
    return <p className="muted">No review targets are available for this run.</p>;
  }
  const groups = targets.reduce<Record<string, ReviewTarget[]>>((accumulator, target) => {
    accumulator[target.target_type] = accumulator[target.target_type] ?? [];
    accumulator[target.target_type].push(target);
    return accumulator;
  }, {});
  return (
    <div className="review-queue" aria-label="Review target queue">
      {Object.entries(groups).map(([targetType, group]) => (
        <div className="review-group" key={targetType}>
          <strong>{targetType}</strong>
          <div>
            {group.slice(0, 8).map((target) => (
              <button
                key={target.target_key}
                className={selectedTargetKey === target.target_key ? "selected" : ""}
                onClick={() => onTargetSelected(target.target_key)}
              >
                {shortId(target.label)}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function UploadModeGuidance({
  mode,
  uploadMode
}: {
  mode: UploadModeInfo | null;
  uploadMode: UploadMode;
}) {
  const examples = EXAMPLE_UPLOADS[uploadMode];
  return (
    <div className="mode-guidance">
      <div className="mode-guidance-heading">
        <Info size={16} />
        <strong>{mode?.label ?? "Upload mode"}</strong>
      </div>
      <p>{mode?.description ?? "Loading accepted file expectations from the API."}</p>
      {mode && (
        <p className="field-hint">
          Accepted: {mode.accepted_extensions.join(", ")}
          {mode.required_fields.length ? ` · Required fields: ${mode.required_fields.join(", ")}` : ""}
        </p>
      )}
      <ul className="example-list" aria-label="Example upload files">
        {examples.map((example) => (
          <li key={example.path}>
            <span>{example.label}</span>
            <code>{example.path}</code>
          </li>
        ))}
      </ul>
    </div>
  );
}

function EmptyMessage({ title, body }: { title: string; body: string }) {
  return (
    <div className="empty-message">
      <strong>{title}</strong>
      <span>{body}</span>
    </div>
  );
}

function CompactList({
  items,
  idField,
  labelField
}: {
  items: Array<Record<string, unknown>>;
  idField: string;
  labelField: string;
}) {
  if (!items.length) return <p className="muted">No items recorded.</p>;
  return (
    <ul className="compact-list">
      {items.slice(0, 8).map((item, index) => (
        <li key={String(item[idField] ?? index)}>
          <strong>{shortId(valueText(item[idField] ?? index))}</strong>
          <span>{valueText(item[labelField])}</span>
        </li>
      ))}
    </ul>
  );
}
