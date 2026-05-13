import {
  AlertTriangle,
  Check,
  ChevronRight,
  Circle,
  FileUp,
  GitBranch,
  History,
  Info,
  RefreshCw,
  Send,
  X
} from "lucide-react";
import { ChangeEvent, FormEvent, useEffect, useMemo, useReducer } from "react";

import { api } from "./api";
import { initialState, reducer } from "./state";
import type {
  ReviewAction,
  ReviewTarget,
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

  useEffect(() => {
    void loadBootstrap();
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
      </section>
    </main>
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
