import {
  Activity,
  Database,
  GitBranch,
  History,
  Layers3,
  ListChecks,
  MessageSquare,
  Play,
  RefreshCw,
  RotateCcw,
  Search,
  Send,
  SlidersHorizontal,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  UploadCloud,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  analyzeEvidence,
  listCases,
  listRuns,
  loadCase,
  loadRun,
  runWhatIf,
  sendFeedback,
  uploadRun,
} from "./lib/api";
import {
  casePathCount,
  fieldsFromEvidence,
  formatValue,
  messageOf,
  parseOptionalNumber,
  splitLines,
} from "./lib/workspace";
import {
  CaseQueue,
  CorrectionTable,
  EmptyState,
  InfoField,
  KeyValueList,
  LabeledInput,
  LabeledTextArea,
  LinkedEntitiesTable,
  LogLine,
  MetricBlock,
  MetricChip,
  PathRow,
  RunQueue,
  SectionHeader,
  Subsection,
  WorkflowSteps,
} from "./components/workspace";
import type {
  AnalysisResponse,
  CaseSummary,
  Evidence,
  PathResult,
  RunDetail,
  RunSummary,
} from "./types";

type LoadingState = "idle" | "loading" | "ready" | "error";
type QueueView = "cases" | "runs";
type InspectorView = "what-if" | "payload" | "feedback";

const DEFAULT_TOP_K = 3;

const EMPTY_WHAT_IF = {
  anomaly_type: "",
  location: "",
  morphology: "",
  variables: "",
  log_events: "",
  severity: "",
  confidence: "",
};

export default function App() {
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState<string>("");
  const [selectedCase, setSelectedCase] = useState<AnalysisResponse | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string>("");
  const [selectedRun, setSelectedRun] = useState<RunDetail | null>(null);
  const [draftEvidence, setDraftEvidence] = useState<Evidence | null>(null);
  const [topK, setTopK] = useState<number>(DEFAULT_TOP_K);
  const [uploadTopK, setUploadTopK] = useState<number>(DEFAULT_TOP_K);
  const [whatIf, setWhatIf] = useState(EMPTY_WHAT_IF);
  const [uploadMode, setUploadMode] = useState<"evidence" | "records">("records");
  const [uploadDataset, setUploadDataset] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadInputKey, setUploadInputKey] = useState(0);
  const [queueView, setQueueView] = useState<QueueView>("runs");
  const [inspectorView, setInspectorView] = useState<InspectorView>("what-if");
  const [search, setSearch] = useState("");
  const [runSearch, setRunSearch] = useState("");
  const [loadingState, setLoadingState] = useState<LoadingState>("loading");
  const [runLoadingState, setRunLoadingState] = useState<LoadingState>("idle");
  const [actionMessage, setActionMessage] = useState<string>("");
  const [runMessage, setRunMessage] = useState<string>("");
  const [error, setError] = useState<string>("");
  const [runError, setRunError] = useState<string>("");
  const [feedbackNote, setFeedbackNote] = useState("");
  const [feedbackPathId, setFeedbackPathId] = useState("");
  const [feedbackTargetType, setFeedbackTargetType] = useState<
    "case" | "link" | "correction" | "path"
  >("path");
  const [feedbackDecision, setFeedbackDecision] = useState<"accept" | "reject" | "comment">(
    "accept",
  );

  useEffect(() => {
    void loadCaseList();
    void loadRunList();
  }, []);

  useEffect(() => {
    if (!selectedCaseId && cases.length > 0) {
      setSelectedCaseId(cases[0].case_id);
    }
  }, [cases, selectedCaseId]);

  useEffect(() => {
    if (!selectedCaseId) {
      return;
    }
    void loadSelectedCase(selectedCaseId, topK);
  }, [selectedCaseId]);

  useEffect(() => {
    if (draftEvidence) {
      setWhatIf(fieldsFromEvidence(draftEvidence));
    }
  }, [draftEvidence]);

  const filteredCases = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) {
      return cases;
    }
    return cases.filter((item) => {
      return (
        item.case_id.toLowerCase().includes(query) ||
        item.dataset.toLowerCase().includes(query) ||
        item.source_kind.toLowerCase().includes(query)
      );
    });
  }, [cases, search]);

  const filteredRuns = useMemo(() => {
    const query = runSearch.trim().toLowerCase();
    if (!query) {
      return runs;
    }
    return runs.filter((item) => {
      return (
        item.run_id.toLowerCase().includes(query) ||
        item.source_filename.toLowerCase().includes(query) ||
        item.mode.toLowerCase().includes(query) ||
        (item.dataset ?? "").toLowerCase().includes(query)
      );
    });
  }, [runs, runSearch]);

  const selectedCaseSummary = selectedCase?.case ?? cases.find((item) => item.case_id === selectedCaseId);
  const caseEvidence = selectedCase?.evidence_with_analysis ?? selectedCase?.evidence ?? draftEvidence;
  const runEvidence = selectedRun?.evidence_with_analysis ?? selectedRun?.evidence ?? null;
  const activePayload = selectedCase?.evidence_with_analysis ?? runEvidence ?? draftEvidence;
  const analysis = selectedCase?.analysis ?? selectedRun?.analysis ?? null;
  const workflowSteps = selectedRun?.workflow_steps?.length
    ? selectedRun.workflow_steps
    : selectedCase?.workflow_steps ?? [];
  const linkedCount = analysis?.linked_entities.length ?? 0;
  const correctionCount = analysis?.correction_candidates.length ?? 0;
  const pathCount = analysis?.top_k_paths.length ?? 0;
  const activeClaim = selectedCase?.claim_boundary ?? selectedRun?.claim_boundary ?? "-";

  async function refreshWorkspace() {
    await Promise.all([loadCaseList(), loadRunList()]);
  }

  async function loadCaseList() {
    try {
      setLoadingState("loading");
      const response = await listCases();
      setCases(response);
      setLoadingState("ready");
      setError("");
    } catch (error_) {
      setLoadingState("error");
      setError(messageOf(error_));
    }
  }

  async function loadRunList() {
    try {
      setRunLoadingState("loading");
      const response = await listRuns();
      setRuns(response);
      setRunLoadingState("ready");
      setRunError("");
      if (!selectedRunId && response.length > 0) {
        void loadSelectedRun(response[0].run_id);
      }
    } catch (error_) {
      setRunLoadingState("error");
      setRunError(messageOf(error_));
    }
  }

  async function loadSelectedCase(caseId: string, desiredTopK = topK) {
    try {
      setLoadingState("loading");
      const response = await loadCase(caseId);
      setSelectedCase(response);
      setDraftEvidence(response.evidence);
      setTopK(desiredTopK);
      setLoadingState("ready");
      setError("");
      setActionMessage(`Loaded ${caseId}`);
      setFeedbackPathId("");
    } catch (error_) {
      setLoadingState("error");
      setError(messageOf(error_));
    }
  }

  async function loadSelectedRun(runId: string) {
    try {
      setRunLoadingState("loading");
      const response = await loadRun(runId);
      setSelectedRun(response);
      setSelectedRunId(runId);
      setRunLoadingState("ready");
      setRunMessage(`Loaded run ${runId}`);
      setRunError("");
    } catch (error_) {
      setRunLoadingState("error");
      setRunError(messageOf(error_));
    }
  }

  async function uploadSampleRun() {
    if (!uploadFile) {
      setRunError("Choose a file first");
      return;
    }
    try {
      setRunLoadingState("loading");
      const response = await uploadRun({
        file: uploadFile,
        mode: uploadMode,
        dataset: uploadDataset || null,
        top_k: uploadTopK,
      });
      setRuns((current) => [response.run, ...current.filter((item) => item.run_id !== response.run.run_id)]);
      setSelectedRun(response);
      setSelectedRunId(response.run.run_id);
      setQueueView("runs");
      setRunMessage(`Ran ${uploadFile.name} as ${uploadMode}`);
      setUploadFile(null);
      setUploadInputKey((current) => current + 1);
      setRunLoadingState("ready");
      setRunError("");
    } catch (error_) {
      setRunLoadingState("error");
      setRunError(messageOf(error_));
    }
  }

  async function rerunAnalysis() {
    if (!draftEvidence) {
      return;
    }
    try {
      setLoadingState("loading");
      const response = await analyzeEvidence(draftEvidence, topK);
      setSelectedCase(response);
      setDraftEvidence(response.evidence);
      setLoadingState("ready");
      setActionMessage(`Analyzed ${draftEvidence.case_id}`);
      setError("");
    } catch (error_) {
      setLoadingState("error");
      setError(messageOf(error_));
    }
  }

  async function rerunWhatIf() {
    if (!draftEvidence) {
      return;
    }
    try {
      setLoadingState("loading");
      const response = await runWhatIf({
        case_id: draftEvidence.case_id,
        anomaly_type: whatIf.anomaly_type,
        location: whatIf.location,
        morphology: whatIf.morphology,
        variables: splitLines(whatIf.variables),
        log_events: splitLines(whatIf.log_events),
        severity: parseOptionalNumber(whatIf.severity),
        confidence: parseOptionalNumber(whatIf.confidence),
        top_k: topK,
      });
      setSelectedCase(response);
      setDraftEvidence(response.evidence);
      setLoadingState("ready");
      setActionMessage(`What-if analysis updated for ${draftEvidence.case_id}`);
      setError("");
    } catch (error_) {
      setLoadingState("error");
      setError(messageOf(error_));
    }
  }

  async function submitFeedback(
    targetType: "case" | "link" | "correction" | "path",
    decision = feedbackDecision,
  ) {
    if (!draftEvidence) {
      return;
    }
    try {
      const response = await sendFeedback({
        case_id: draftEvidence.case_id,
        target_type: targetType,
        decision,
        target_id: feedbackPathId || undefined,
        comment: feedbackNote || undefined,
        metadata: {
          selected_case_id: selectedCaseId,
          selected_run_id: selectedRunId,
          top_k: topK,
        },
      });
      setActionMessage(`Feedback saved to ${response.feedback_path}`);
      setFeedbackNote("");
      setError("");
    } catch (error_) {
      setError(messageOf(error_));
    }
  }

  return (
    <div className="min-h-full bg-zinc-950 text-zinc-100">
      <header className="sticky top-0 z-20 border-b border-zinc-800 bg-zinc-950/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1700px] flex-wrap items-center justify-between gap-4 px-4 py-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-3">
              <div className="text-lg font-semibold tracking-tight">KGTraceVis</div>
              <span className="badge badge-accent">operations workspace</span>
              <span className="badge">candidate RCA, not verified labels</span>
            </div>
            <div className="mt-1 truncate text-sm text-zinc-400">
              Upload samples, run the adapter/pipeline path, inspect each step, and record review feedback.
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <MetricChip icon={Database} label="cases" value={String(cases.length)} />
            <MetricChip icon={History} label="runs" value={String(runs.length)} />
            <MetricChip icon={Activity} label="status" value={loadingState === "error" ? "attention" : "ready"} />
            <button className="button" onClick={() => void refreshWorkspace()}>
              <RefreshCw className="h-4 w-4" />
              Refresh
            </button>
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-[1700px] gap-4 px-4 py-4 xl:grid-cols-[330px_minmax(0,1fr)_380px]">
        <aside className="space-y-4">
          <section className="surface">
            <SectionHeader
              icon={UploadCloud}
              title="Ingest"
              subtitle="Start from an evidence JSON or a raw record bundle."
            />
            <div className="space-y-3 p-4">
              <label className="block">
                <div className="field-label">Sample file</div>
                <input
                  key={uploadInputKey}
                  className="input mt-1"
                  type="file"
                  onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)}
                />
              </label>
              <div>
                <div className="field-label">Input mode</div>
                <div className="mt-1 grid grid-cols-2 gap-2">
                  <button
                    className={uploadMode === "records" ? "segmented-active" : "segmented"}
                    onClick={() => setUploadMode("records")}
                    type="button"
                  >
                    Records
                  </button>
                  <button
                    className={uploadMode === "evidence" ? "segmented-active" : "segmented"}
                    onClick={() => setUploadMode("evidence")}
                    type="button"
                  >
                    Evidence
                  </button>
                </div>
              </div>
              <div className="grid grid-cols-[minmax(0,1fr)_88px] gap-3">
                <label className="block">
                  <div className="field-label">Dataset override</div>
                  <select
                    className="input mt-1"
                    value={uploadDataset}
                    onChange={(event) => setUploadDataset(event.target.value)}
                  >
                    <option value="">auto</option>
                    <option value="mvtec">mvtec</option>
                    <option value="tep">tep</option>
                    <option value="wafer">wafer</option>
                  </select>
                </label>
                <label className="block">
                  <div className="field-label">top_k</div>
                  <input
                    type="number"
                    min={1}
                    max={10}
                    className="input mt-1"
                    value={uploadTopK}
                    onChange={(event) => setUploadTopK(Number(event.target.value) || DEFAULT_TOP_K)}
                  />
                </label>
              </div>
              {uploadFile ? (
                <div className="rounded-md border border-zinc-800 bg-zinc-950/60 px-3 py-2 text-xs text-zinc-300">
                  Ready: <span className="text-zinc-100">{uploadFile.name}</span>
                </div>
              ) : null}
              <div className="flex flex-wrap gap-2">
                <button className="button-primary" onClick={() => void uploadSampleRun()}>
                  <Play className="h-4 w-4" />
                  Upload and run
                </button>
                <button
                  className="button"
                  onClick={() => {
                    setUploadFile(null);
                    setUploadDataset("");
                    setUploadMode("records");
                    setUploadInputKey((current) => current + 1);
                  }}
                >
                  <RotateCcw className="h-4 w-4" />
                  Clear
                </button>
              </div>
            </div>
          </section>

          <section className="surface">
            <SectionHeader
              icon={ListChecks}
              title="Work queue"
              subtitle="Pick a run session or inspect a reusable evidence case."
            />
            <div className="border-b border-zinc-800 p-3">
              <div className="grid grid-cols-2 gap-2">
                <button
                  className={queueView === "runs" ? "segmented-active" : "segmented"}
                  onClick={() => setQueueView("runs")}
                  type="button"
                >
                  Runs
                </button>
                <button
                  className={queueView === "cases" ? "segmented-active" : "segmented"}
                  onClick={() => setQueueView("cases")}
                  type="button"
                >
                  Cases
                </button>
              </div>
              <div className="relative mt-3">
                <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-zinc-500" />
                <input
                  className="input pl-9"
                  placeholder={queueView === "runs" ? "Filter run, file, dataset..." : "Filter case, dataset, source..."}
                  value={queueView === "runs" ? runSearch : search}
                  onChange={(event) =>
                    queueView === "runs" ? setRunSearch(event.target.value) : setSearch(event.target.value)
                  }
                />
              </div>
            </div>
            <div className="scrollbar-thin max-h-[52rem] overflow-y-auto">
              {queueView === "runs" ? (
                <RunQueue
                  items={filteredRuns}
                  selectedRunId={selectedRunId}
                  onSelect={(runId) => void loadSelectedRun(runId)}
                />
              ) : (
                <CaseQueue
                  items={filteredCases}
                  selectedCaseId={selectedCaseId}
                  onSelect={setSelectedCaseId}
                />
              )}
              {queueView === "runs" && runLoadingState === "error" ? (
                <div className="p-4 text-sm text-rose-300">{runError}</div>
              ) : null}
              {queueView === "cases" && loadingState === "error" ? (
                <div className="p-4 text-sm text-rose-300">{error}</div>
              ) : null}
            </div>
          </section>
        </aside>

        <main className="space-y-4">
          <section className="surface">
            <SectionHeader
              icon={GitBranch}
              title="Run session"
              subtitle={selectedRun ? selectedRun.run.label : "No run selected yet"}
              actions={
                selectedRun ? (
                  <div className="flex flex-wrap gap-2">
                    <span className="badge">{selectedRun.run.mode}</span>
                    <span className="badge">{selectedRun.run.status}</span>
                    <span className="badge">{selectedRun.run.dataset ?? "auto"}</span>
                  </div>
                ) : null
              }
            />
            <div className="p-4">
              {selectedRun ? (
                <div className="space-y-4">
                  <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-4">
                    <InfoField label="source file" value={selectedRun.run.source_filename} />
                    <InfoField label="created" value={selectedRun.run.created_at} />
                    <InfoField label="cases" value={String(selectedRun.run.case_count)} />
                    <InfoField label="evidence" value={String(selectedRun.run.evidence_count)} />
                  </div>
                  <WorkflowSteps steps={selectedRun.workflow_steps} />
                  {selectedRun.cases?.length ? (
                    <div>
                      <div className="panel-title">Cases produced by this run</div>
                      <div className="table-shell mt-3">
                        <table className="min-w-full text-sm">
                          <thead>
                            <tr>
                              <th>Case</th>
                              <th>Dataset</th>
                              <th>Linked</th>
                              <th>Consistency</th>
                              <th>Paths</th>
                            </tr>
                          </thead>
                          <tbody>
                            {selectedRun.cases.map((item, index) => {
                              const caseId = String(item.case_id ?? `case-${index + 1}`);
                              return (
                                <tr key={caseId}>
                                  <td>
                                    <button
                                      className="table-link"
                                      onClick={() => setSelectedCaseId(caseId)}
                                      type="button"
                                    >
                                      {caseId}
                                    </button>
                                  </td>
                                  <td>{String(item.dataset ?? "unknown")}</td>
                                  <td>{formatValue(item.linked_entity_count)}</td>
                                  <td>{formatValue(item.consistency_score)}</td>
                                  <td>{formatValue(casePathCount(item))}</td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  ) : null}
                  <details className="rounded-md border border-zinc-800 bg-zinc-950/40">
                    <summary className="cursor-pointer px-3 py-2 text-sm font-medium text-zinc-200">
                      Artifacts and persisted paths
                    </summary>
                    <div className="border-t border-zinc-800 p-3">
                      <KeyValueList
                        items={{
                          run_dir: selectedRun.run.run_dir,
                          ...selectedRun.artifacts,
                          claim_boundary: selectedRun.claim_boundary,
                        }}
                      />
                    </div>
                  </details>
                </div>
              ) : (
                <EmptyState
                  title="No run selected"
                  body="Upload a file or choose a run from the queue to see the execution trace."
                />
              )}
            </div>
          </section>

          <section className="surface">
            <SectionHeader
              icon={Layers3}
              title="Case workbench"
              subtitle={selectedCaseSummary?.label ?? selectedCaseId ?? "No case selected"}
              actions={
                <div className="flex flex-wrap items-center gap-2">
                  <label className="inline-flex items-center gap-2 rounded-md border border-zinc-700 px-3 py-2 text-sm text-zinc-300">
                    top_k
                    <input
                      type="number"
                      min={1}
                      max={10}
                      className="w-14 bg-transparent text-right outline-none"
                      value={topK}
                      onChange={(event) => setTopK(Number(event.target.value) || DEFAULT_TOP_K)}
                    />
                  </label>
                  <button className="button-primary" onClick={() => void rerunAnalysis()}>
                    <Sparkles className="h-4 w-4" />
                    Run analysis
                  </button>
                </div>
              }
            />
            <div className="space-y-4 p-4">
              <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-5">
                <MetricBlock label="linked entities" value={String(linkedCount)} />
                <MetricBlock label="consistency" value={formatValue(analysis?.consistency_score)} />
                <MetricBlock label="inconsistent fields" value={String(analysis?.inconsistent_fields.length ?? 0)} />
                <MetricBlock label="corrections" value={String(correctionCount)} />
                <MetricBlock label="paths" value={String(pathCount)} />
              </div>

              <div className="flex flex-wrap gap-2 text-xs">
                <span className="badge">{caseEvidence?.dataset ?? "-"}</span>
                <span className="badge">{caseEvidence?.source ?? "-"}</span>
                {selectedCaseSummary?.source_kind ? (
                  <span className="badge badge-accent">{selectedCaseSummary.source_kind}</span>
                ) : null}
                <span className="badge">{activeClaim}</span>
              </div>

              <div className="grid gap-4 2xl:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]">
                <div className="space-y-4">
                  <Subsection title="Observed evidence">
                    {caseEvidence ? (
                      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                        <InfoField label="object" value={caseEvidence.object} />
                        <InfoField label="anomaly_type" value={caseEvidence.anomaly_type} />
                        <InfoField label="location" value={caseEvidence.location ?? "-"} />
                        <InfoField label="morphology" value={caseEvidence.morphology ?? "-"} />
                        <InfoField label="severity" value={formatValue(caseEvidence.severity)} />
                        <InfoField label="confidence" value={formatValue(caseEvidence.confidence)} />
                      </div>
                    ) : (
                      <EmptyState title="No evidence loaded" body="Choose a case to inspect its normalized evidence." />
                    )}
                  </Subsection>

                  <Subsection title="Observation stream">
                    <div className="table-shell max-h-80">
                      <table className="min-w-full text-sm">
                        <thead>
                          <tr>
                            <th>Facet</th>
                            <th>Name</th>
                            <th>Confidence</th>
                            <th>Source</th>
                          </tr>
                        </thead>
                        <tbody>
                          {caseEvidence?.observations.map((item) => (
                            <tr key={item.obs_id}>
                              <td>{item.facet}</td>
                              <td>{item.display_name ?? item.name}</td>
                              <td>{formatValue(item.confidence)}</td>
                              <td>{item.source_ref ?? item.raw_ref ?? "-"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </Subsection>
                </div>

                <div className="space-y-4">
                  <Subsection title="Linked KG entities">
                    <LinkedEntitiesTable links={analysis?.linked_entities ?? []} />
                  </Subsection>

                  <Subsection title="Correction candidates">
                    <CorrectionTable candidates={analysis?.correction_candidates ?? []} />
                  </Subsection>

                  <Subsection title="Candidate explanation paths">
                    <div className="space-y-3">
                      {analysis?.top_k_paths.length ? (
                        analysis.top_k_paths.map((path) => (
                          <PathRow
                            key={path.path_id}
                            path={path}
                            onAccept={() => void submitPathFeedback(path, "accept")}
                            onReject={() => void submitPathFeedback(path, "reject")}
                            onSelect={() => {
                              setInspectorView("feedback");
                              setFeedbackTargetType("path");
                              setFeedbackPathId(path.path_id);
                              setFeedbackDecision("comment");
                            }}
                          />
                        ))
                      ) : (
                        <EmptyState title="No candidate paths" body="Run analysis to generate ranked candidate paths." />
                      )}
                    </div>
                  </Subsection>
                </div>
              </div>
            </div>
          </section>
        </main>

        <aside className="space-y-4">
          <section className="surface sticky top-[5.25rem]">
            <SectionHeader
              icon={SlidersHorizontal}
              title="Inspector"
              subtitle="Edit, inspect payloads, and submit review decisions."
            />
            <div className="border-b border-zinc-800 p-3">
              <div className="grid grid-cols-3 gap-2">
                <button
                  className={inspectorView === "what-if" ? "segmented-active" : "segmented"}
                  onClick={() => setInspectorView("what-if")}
                  type="button"
                >
                  Edit
                </button>
                <button
                  className={inspectorView === "payload" ? "segmented-active" : "segmented"}
                  onClick={() => setInspectorView("payload")}
                  type="button"
                >
                  Payload
                </button>
                <button
                  className={inspectorView === "feedback" ? "segmented-active" : "segmented"}
                  onClick={() => setInspectorView("feedback")}
                  type="button"
                >
                  Review
                </button>
              </div>
            </div>

            {inspectorView === "what-if" ? (
              <div className="space-y-3 p-4">
                <div className="flex items-center gap-2 text-sm text-zinc-300">
                  <SlidersHorizontal className="h-4 w-4 text-cyan-300" />
                  What-if edits apply to the active case evidence.
                </div>
                <LabeledInput
                  label="Anomaly type"
                  value={whatIf.anomaly_type}
                  onChange={(value) => setWhatIf((current) => ({ ...current, anomaly_type: value }))}
                />
                <div className="grid grid-cols-2 gap-3">
                  <LabeledInput
                    label="Location"
                    value={whatIf.location}
                    onChange={(value) => setWhatIf((current) => ({ ...current, location: value }))}
                  />
                  <LabeledInput
                    label="Morphology"
                    value={whatIf.morphology}
                    onChange={(value) => setWhatIf((current) => ({ ...current, morphology: value }))}
                  />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <LabeledInput
                    label="Severity"
                    value={whatIf.severity}
                    onChange={(value) => setWhatIf((current) => ({ ...current, severity: value }))}
                  />
                  <LabeledInput
                    label="Confidence"
                    value={whatIf.confidence}
                    onChange={(value) => setWhatIf((current) => ({ ...current, confidence: value }))}
                  />
                </div>
                <LabeledTextArea
                  label="Variables"
                  value={whatIf.variables}
                  onChange={(value) => setWhatIf((current) => ({ ...current, variables: value }))}
                />
                <LabeledTextArea
                  label="Log events"
                  value={whatIf.log_events}
                  onChange={(value) => setWhatIf((current) => ({ ...current, log_events: value }))}
                />
                <div className="flex flex-wrap gap-2">
                  <button className="button-primary" onClick={() => void rerunWhatIf()}>
                    <Send className="h-4 w-4" />
                    Run what-if
                  </button>
                  <button
                    className="button"
                    onClick={() => draftEvidence && setWhatIf(fieldsFromEvidence(draftEvidence))}
                  >
                    <RotateCcw className="h-4 w-4" />
                    Reset
                  </button>
                </div>
              </div>
            ) : null}

            {inspectorView === "payload" ? (
              <div className="space-y-4 p-4">
                <div>
                  <div className="panel-title">Active payload</div>
                  <pre className="scrollbar-thin mt-3 max-h-[32rem] overflow-auto rounded-md border border-zinc-800 bg-zinc-950 p-3 text-xs text-zinc-300">
                    {JSON.stringify(activePayload, null, 2)}
                  </pre>
                </div>
                <div>
                  <div className="panel-title">Workflow steps</div>
                  <WorkflowSteps steps={workflowSteps} compact />
                </div>
              </div>
            ) : null}

            {inspectorView === "feedback" ? (
              <div className="space-y-3 p-4">
                <div className="flex items-center gap-2 text-sm text-zinc-300">
                  <MessageSquare className="h-4 w-4 text-amber-300" />
                  Feedback is stored as a review record for later KG and path updates.
                </div>
                <label className="block">
                  <div className="field-label">Target type</div>
                  <select
                    className="input mt-1"
                    value={feedbackTargetType}
                    onChange={(event) =>
                      setFeedbackTargetType(
                        event.target.value as "case" | "link" | "correction" | "path",
                      )
                    }
                  >
                    <option value="path">path</option>
                    <option value="case">case</option>
                    <option value="link">link</option>
                    <option value="correction">correction</option>
                  </select>
                </label>
                <label className="block">
                  <div className="field-label">Decision</div>
                  <select
                    className="input mt-1"
                    value={feedbackDecision}
                    onChange={(event) =>
                      setFeedbackDecision(event.target.value as "accept" | "reject" | "comment")
                    }
                  >
                    <option value="accept">accept</option>
                    <option value="reject">reject</option>
                    <option value="comment">comment</option>
                  </select>
                </label>
                <label className="block">
                  <div className="field-label">Target id</div>
                  <input
                    className="input mt-1"
                    value={feedbackPathId}
                    onChange={(event) => setFeedbackPathId(event.target.value)}
                    placeholder="case_id, path_id, link_id, ..."
                  />
                </label>
                <label className="block">
                  <div className="field-label">Comment</div>
                  <textarea
                    className="input mt-1 min-h-28"
                    value={feedbackNote}
                    onChange={(event) => setFeedbackNote(event.target.value)}
                    placeholder="Optional note"
                  />
                </label>
                <div className="flex flex-wrap gap-2">
                  <button
                    className="button-primary"
                    onClick={() => void submitFeedback(feedbackTargetType)}
                  >
                    <ThumbsUp className="h-4 w-4" />
                    Save feedback
                  </button>
                  <button
                    className="button"
                    onClick={() => {
                      setFeedbackTargetType("case");
                      setFeedbackDecision("comment");
                      void submitFeedback("case", "comment");
                    }}
                  >
                    <ThumbsDown className="h-4 w-4" />
                    Case note
                  </button>
                </div>
              </div>
            ) : null}
          </section>

          <section className="surface">
            <SectionHeader icon={Activity} title="Event log" subtitle="Recent UI and API state." />
            <div className="space-y-2 p-4 text-sm">
              {runMessage ? <LogLine tone="good" text={runMessage} /> : null}
              {actionMessage ? <LogLine tone="good" text={actionMessage} /> : null}
              {runError ? <LogLine tone="bad" text={runError} /> : null}
              {error ? <LogLine tone="bad" text={error} /> : null}
              {!runMessage && !actionMessage && !runError && !error ? (
                <div className="text-zinc-500">No recent events.</div>
              ) : null}
            </div>
          </section>
        </aside>
      </div>
    </div>
  );

  async function submitPathFeedback(path: PathResult, decision: "accept" | "reject") {
    if (!draftEvidence) {
      return;
    }
    try {
      const response = await sendFeedback({
        case_id: draftEvidence.case_id,
        target_type: "path",
        target_id: path.path_id,
        decision,
        comment: `Selected target: ${path.target_entity_id}`,
        metadata: {
          source_entity_id: path.source_entity_id,
          score: path.score,
        },
      });
      setActionMessage(`Feedback saved to ${response.feedback_path}`);
      setError("");
    } catch (error_) {
      setError(messageOf(error_));
    }
  }
}
