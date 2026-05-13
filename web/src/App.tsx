import {
  AlertTriangle,
  Check,
  ChevronRight,
  FileUp,
  GitBranch,
  History,
  RefreshCw,
  Send,
  X
} from "lucide-react";
import { ChangeEvent, FormEvent, useEffect, useMemo, useReducer } from "react";

import { api } from "./api";
import { initialState, reducer } from "./state";
import type { ReviewAction, ReviewTarget, RunDetail, UploadMode } from "./types";

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
      dispatch({ type: "runLoaded", run });
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
        metadata: { run_label: state.selectedRun.run.label }
      });
      dispatch({ type: "reviewRecorded", status: response.status });
    } catch (error) {
      dispatch({ type: "error", error: (error as Error).message });
    } finally {
      dispatch({ type: "loading", value: false });
    }
  }

  const presets = state.bootstrap?.mvtec_model_presets.presets ?? [];

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">RootLens</p>
          <h1>Evidence Analysis Workspace</h1>
        </div>
        <button className="icon-button" onClick={() => void loadBootstrap()} title="Refresh">
          <RefreshCw size={18} />
        </button>
      </header>

      {state.error && (
        <div className="status status-error">
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
                {state.bootstrap?.upload_modes.map((mode) => (
                  <option key={mode.mode} value={mode.mode}>
                    {mode.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              File
              <input
                type="file"
                onChange={(event: ChangeEvent<HTMLInputElement>) =>
                  dispatch({
                    type: "uploadChanged",
                    patch: { file: event.target.files?.[0] ?? null }
                  })
                }
              />
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
              Analyze
            </button>
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
            {state.runs.map((run) => (
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
            ))}
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
              <p>Select a run or upload records/evidence to inspect candidate paths.</p>
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

      <section className="panel wide">
        <div className="panel-heading">
          <GitBranch size={18} />
          <h2>Candidate Paths</h2>
        </div>
        <div className="table-shell">
          <table>
            <thead>
              <tr>
                <th>Path</th>
                <th>Target</th>
                <th>Score</th>
                <th>Relations</th>
                <th>Edges</th>
              </tr>
            </thead>
            <tbody>
              {run.top_k_paths.map((path) => (
                <tr key={String(path.path_id)}>
                  <td>{shortId(String(path.path_id))}</td>
                  <td>{valueText(path.target_entity_id)}</td>
                  <td>{valueText(path.score)}</td>
                  <td>{valueText(path.relations)}</td>
                  <td>{valueText(path.source_edge_ids)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

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

      <section className="panel wide">
        <h2>Source Edge Provenance</h2>
        <CompactList items={run.source_edge_provenance} idField="edge_id" labelField="evidence" />
      </section>

      <section className="panel wide review-panel">
        <h2>Review</h2>
        <div className="review-controls">
          <select value={selectedTargetKey} onChange={(event) => onTargetSelected(event.target.value)}>
            {run.review_targets.map((target) => (
              <option key={target.target_key} value={target.target_key}>
                {target.target_type} · {shortId(target.label)}
              </option>
            ))}
          </select>
          <input
            value={reviewNote}
            onChange={(event) => onReviewNoteChanged(event.target.value)}
            placeholder="optional review note"
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
        {reviewStatus && <p className="muted">Feedback {reviewStatus}.</p>}
      </section>
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
