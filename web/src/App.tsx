import { RefreshCw, Send, Sparkles, ThumbsDown, ThumbsUp } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  analyzeEvidence,
  listCases,
  listRuns,
  loadCase,
  loadRun,
  uploadRun,
  runWhatIf,
  sendFeedback,
} from "./lib/api";
import type {
  AnalysisResponse,
  CaseSummary,
  Evidence,
  PathResult,
  RunDetail,
  RunStep,
  RunSummary,
} from "./types";

type LoadingState = "idle" | "loading" | "ready" | "error";

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
  }, []);

  useEffect(() => {
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

  const analysis = selectedCase?.analysis;
  const evidence = draftEvidence;
  const runSteps = selectedRun?.workflow_steps ?? [];
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

  return (
    <div className="min-h-full bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 bg-slate-950/95">
        <div className="mx-auto flex max-w-[1600px] items-center justify-between px-4 py-4">
          <div>
            <div className="text-xl font-semibold tracking-tight">KGTraceVis</div>
            <div className="text-sm text-slate-400">
              Evidence review, consistency scoring, and candidate explanation paths
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button className="button" onClick={() => void loadCaseList()}>
              <RefreshCw className="h-4 w-4" />
              Refresh
            </button>
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-[1600px] grid-cols-[320px_minmax(0,1fr)] gap-4 p-4">
        <aside className="panel flex min-h-[calc(100vh-7rem)] flex-col">
          <div className="border-b border-slate-800 p-4">
            <div className="panel-title">Cases</div>
            <input
              className="input mt-3"
              placeholder="Filter by case, dataset, source..."
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
          <div className="scrollbar-thin flex-1 overflow-y-auto p-2">
            {filteredCases.map((item) => (
              <button
                key={item.case_id}
                className={`mb-2 w-full rounded-md border px-3 py-3 text-left transition ${
                  item.case_id === selectedCaseId
                    ? "border-teal-600 bg-teal-500/10"
                    : "border-slate-800 bg-slate-950/30 hover:border-slate-600 hover:bg-slate-900"
                }`}
                onClick={() => setSelectedCaseId(item.case_id)}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="text-sm font-medium text-slate-100">{item.case_id}</div>
                  <span className="badge">{item.dataset}</span>
                </div>
                <div className="mt-1 text-xs text-slate-400">{item.label}</div>
                <div className="mt-2 flex flex-wrap gap-2">
                  <span className="badge">{item.source_kind}</span>
                  {item.is_real_output ? (
                    <span className="badge badge-accent">real</span>
                  ) : (
                    <span className="badge">example</span>
                  )}
                </div>
              </button>
            ))}
            {loadingState === "error" ? (
              <div className="p-4 text-sm text-rose-300">{error}</div>
            ) : null}
          </div>

          <div className="border-t border-slate-800 p-4">
            <div className="panel-title">Run history</div>
            <input
              className="input mt-3"
              placeholder="Filter by run, file, dataset..."
              value={runSearch}
              onChange={(event) => setRunSearch(event.target.value)}
            />
            <div className="mt-3 max-h-96 overflow-y-auto pr-1">
              {filteredRuns.map((item) => (
                <button
                  key={item.run_id}
                  className={`mb-2 w-full rounded-md border px-3 py-3 text-left transition ${
                    item.run_id === selectedRunId
                      ? "border-teal-600 bg-teal-500/10"
                      : "border-slate-800 bg-slate-950/30 hover:border-slate-600 hover:bg-slate-900"
                  }`}
                  onClick={() => void loadSelectedRun(item.run_id)}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-sm font-medium text-slate-100">{item.label}</div>
                    <span className="badge">{item.mode}</span>
                  </div>
                  <div className="mt-1 text-xs text-slate-400">{item.source_filename}</div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <span className="badge">{item.case_count} cases</span>
                    <span className="badge">{item.dataset ?? "auto"}</span>
                  </div>
                </button>
              ))}
              {runLoadingState === "error" ? (
                <div className="p-4 text-sm text-rose-300">{runError}</div>
              ) : null}
            </div>
          </div>
        </aside>

        <main className="space-y-4">
          <section className="panel p-4">
            <div className="panel-title">Upload and run</div>
            <div className="mt-3 grid gap-3 lg:grid-cols-[1.2fr_0.8fr_0.8fr_0.5fr]">
              <label className="block">
                <div className="field-label">Sample file</div>
                <input
                  key={uploadInputKey}
                  className="input mt-1"
                  type="file"
                  onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)}
                />
              </label>
              <label className="block">
                <div className="field-label">Input mode</div>
                <select
                  className="input mt-1"
                  value={uploadMode}
                  onChange={(event) => setUploadMode(event.target.value as "evidence" | "records")}
                >
                  <option value="records">records</option>
                  <option value="evidence">evidence</option>
                </select>
              </label>
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
            <div className="mt-4 flex flex-wrap gap-2">
              <button className="button-primary" onClick={() => void uploadSampleRun()}>
                <Sparkles className="h-4 w-4" />
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
                Reset upload
              </button>
            </div>
            {runMessage ? <div className="mt-3 text-sm text-teal-300">{runMessage}</div> : null}
            {runError ? <div className="mt-3 text-sm text-rose-300">{runError}</div> : null}
          </section>

          {selectedRun ? (
            <section className="panel p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="panel-title">Selected run</div>
                  <h2 className="mt-1 text-2xl font-semibold tracking-tight">
                    {selectedRun.run.label}
                  </h2>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <span className="badge">{selectedRun.run.mode}</span>
                    <span className="badge">{selectedRun.run.source_filename}</span>
                    <span className="badge">{selectedRun.run.case_count} cases</span>
                  </div>
                </div>
                <div className="text-right text-xs text-slate-500">
                  <div>{selectedRun.run.created_at}</div>
                  <div>{selectedRun.run.run_id}</div>
                </div>
              </div>
              <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                <InfoField label="run dir" value={selectedRun.run.run_dir} />
                <InfoField label="dataset" value={selectedRun.run.dataset ?? "auto"} />
                <InfoField label="evidence count" value={String(selectedRun.run.evidence_count)} />
                <InfoField label="claim boundary" value={selectedRun.claim_boundary} />
              </div>
              <div className="mt-4">
                <WorkflowSteps steps={runSteps} />
              </div>
              {selectedRun.summary ? (
                <div className="mt-4">
                  <div className="panel-title">Run summary</div>
                  <pre className="scrollbar-thin mt-3 max-h-80 overflow-auto rounded-md border border-slate-800 bg-slate-950 p-4 text-xs text-slate-300">
                    {JSON.stringify(selectedRun.summary, null, 2)}
                  </pre>
                </div>
              ) : null}
              {selectedRun.cases?.length ? (
                <div className="mt-4">
                  <div className="panel-title">Cases in run</div>
                  <div className="mt-3 grid gap-3 lg:grid-cols-2">
                    {selectedRun.cases.map((item, index) => (
                      <div
                        key={`${String(item.case_id ?? index)}`}
                        className="rounded-md border border-slate-800 bg-slate-950/60 p-3"
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="text-sm font-medium text-slate-100">
                            {String(item.case_id ?? `case-${index + 1}`)}
                          </div>
                          <span className="badge">{String(item.dataset ?? "unknown")}</span>
                        </div>
                        <div className="mt-2 grid gap-2 md:grid-cols-3">
                          <InfoField
                            label="linked entities"
                            value={formatValue(item.linked_entity_count)}
                          />
                          <InfoField
                            label="consistency"
                            value={formatValue(item.consistency_score)}
                          />
                          <InfoField
                            label="candidate paths"
                            value={formatValue(casePathCount(item))}
                          />
                        </div>
                        <div className="mt-2 text-xs text-slate-500">
                          {String(item.claim_boundary ?? "")}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </section>
          ) : null}

          <section className="panel p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="panel-title">Selected case</div>
                <h1 className="mt-1 text-2xl font-semibold tracking-tight">
                  {selectedCase?.case?.case_id ?? draftEvidence?.case_id ?? "No case selected"}
                </h1>
                <div className="mt-2 flex flex-wrap gap-2">
                  <span className="badge">{draftEvidence?.dataset ?? "-"}</span>
                  <span className="badge">{draftEvidence?.source ?? "-"}</span>
                  {selectedCase?.case?.source_kind ? (
                    <span className="badge badge-accent">{selectedCase.case.source_kind}</span>
                  ) : null}
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                <label className="flex items-center gap-2 rounded-md border border-slate-700 px-3 py-2 text-sm text-slate-300">
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
            </div>
            {actionMessage ? <div className="mt-3 text-sm text-teal-300">{actionMessage}</div> : null}
            {error ? <div className="mt-3 text-sm text-rose-300">{error}</div> : null}
          </section>

          <section className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
            <div className="space-y-4">
              <div className="panel p-4">
                <div className="panel-title">What-if editor</div>
                <div className="mt-3 grid gap-3 md:grid-cols-2">
                  <LabeledInput
                    label="Anomaly type"
                    value={whatIf.anomaly_type}
                    onChange={(value) => setWhatIf((current) => ({ ...current, anomaly_type: value }))}
                  />
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
                  <div />
                </div>
                <div className="mt-3 grid gap-3 md:grid-cols-2">
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
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  <button className="button-primary" onClick={() => void rerunWhatIf()}>
                    <Send className="h-4 w-4" />
                    Run what-if
                  </button>
                  <button
                    className="button"
                    onClick={() => draftEvidence && setWhatIf(fieldsFromEvidence(draftEvidence))}
                  >
                    Reset editor
                  </button>
                </div>
              </div>

              <div className="panel p-4">
                <div className="panel-title">Observed evidence</div>
                <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                  {draftEvidence ? (
                    <>
                      <InfoField label="object" value={draftEvidence.object} />
                      <InfoField label="anomaly_type" value={draftEvidence.anomaly_type} />
                      <InfoField label="location" value={draftEvidence.location ?? "-"} />
                      <InfoField label="morphology" value={draftEvidence.morphology ?? "-"} />
                      <InfoField label="severity" value={formatValue(draftEvidence.severity)} />
                      <InfoField label="confidence" value={formatValue(draftEvidence.confidence)} />
                    </>
                  ) : null}
                </div>
                <div className="mt-4">
                  <div className="text-sm font-medium text-slate-200">Observations</div>
                  <div className="mt-2 max-h-72 overflow-auto rounded-md border border-slate-800">
                    <table className="min-w-full text-sm">
                      <thead className="sticky top-0 bg-slate-950">
                        <tr className="text-left text-slate-400">
                          <th className="px-3 py-2">Facet</th>
                          <th className="px-3 py-2">Name</th>
                          <th className="px-3 py-2">Confidence</th>
                        </tr>
                      </thead>
                      <tbody>
                        {draftEvidence?.observations.map((item) => (
                          <tr key={item.obs_id} className="border-t border-slate-800">
                            <td className="px-3 py-2">{item.facet}</td>
                            <td className="px-3 py-2">{item.name}</td>
                            <td className="px-3 py-2 text-slate-400">
                              {formatValue(item.confidence)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            </div>

            <div className="space-y-4">
              <div className="panel p-4">
                <div className="panel-title">KG summary</div>
                <div className="mt-3 grid gap-3 md:grid-cols-2">
                  <InfoField
                    label="linked entities"
                    value={String(analysis?.linked_entities.length ?? 0)}
                  />
                  <InfoField
                    label="consistency score"
                    value={formatValue(analysis?.consistency_score)}
                  />
                  <InfoField
                    label="inconsistent fields"
                    value={(analysis?.inconsistent_fields ?? []).join(", ") || "-"}
                  />
                  <InfoField
                    label="correction candidates"
                    value={String(analysis?.correction_candidates.length ?? 0)}
                  />
                </div>
              </div>

              <div className="panel p-4">
                <div className="panel-title">Linked entities</div>
                <div className="mt-3 space-y-3">
                  {analysis?.linked_entities.map((link) => (
                    <div key={link.link_id} className="rounded-md border border-slate-800 p-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="text-sm font-medium text-slate-100">{link.field}</div>
                        <div className="flex flex-wrap gap-2">
                          <span className="badge">{link.match_type ?? "unmatched"}</span>
                          {link.ambiguous ? <span className="badge badge-accent">ambiguous</span> : null}
                        </div>
                      </div>
                      <div className="mt-1 text-sm text-slate-300">{link.mention}</div>
                      <div className="mt-2 text-xs text-slate-500">
                        selected: {link.selected_entity_id ?? "none"} · score:{" "}
                        {formatValue(link.score)}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="panel p-4">
                <div className="panel-title">Correction candidates</div>
                <div className="mt-3 space-y-3">
                  {analysis?.correction_candidates.map((candidate) => (
                    <div key={candidate.candidate_id} className="rounded-md border border-slate-800 p-3">
                      <div className="flex items-center justify-between gap-2">
                        <div className="text-sm font-medium text-slate-100">{candidate.field}</div>
                        <span className="badge">{formatValue(candidate.score)}</span>
                      </div>
                      <div className="mt-1 text-sm text-slate-300">
                        {candidate.suggested_value ?? candidate.suggested_entity_id ?? "-"}
                      </div>
                      <div className="mt-1 text-xs text-slate-500">{candidate.reason ?? ""}</div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="panel p-4">
                <div className="panel-title">Candidate paths</div>
                <div className="mt-3 space-y-3">
                  {analysis?.top_k_paths.map((path) => (
                    <PathCard
                      key={path.path_id}
                      path={path}
                      onAccept={() => void submitPathFeedback(path, "accept")}
                      onReject={() => void submitPathFeedback(path, "reject")}
                      onSelect={() => {
                        setFeedbackTargetType("path");
                        setFeedbackPathId(path.path_id);
                        setFeedbackDecision("comment");
                      }}
                    />
                  ))}
                </div>
              </div>
            </div>
          </section>

          <section className="grid gap-4 xl:grid-cols-[1.3fr_0.7fr]">
              <div className="panel p-4">
                <div className="panel-title">Evidence JSON</div>
                <pre className="scrollbar-thin mt-3 max-h-[28rem] overflow-auto rounded-md border border-slate-800 bg-slate-950 p-4 text-xs text-slate-300">
                  {JSON.stringify(selectedCase?.evidence_with_analysis ?? draftEvidence, null, 2)}
                </pre>
                {selectedCase?.workflow_steps?.length ? (
                  <div className="mt-4">
                    <WorkflowSteps steps={selectedCase.workflow_steps} />
                  </div>
                ) : null}
              </div>

            <div className="panel p-4">
              <div className="panel-title">Feedback</div>
              <div className="mt-3 space-y-3">
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
                      setFeedbackDecision(
                        event.target.value as "accept" | "reject" | "comment",
                      )
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
                    Case-level note
                  </button>
                </div>
              </div>
            </div>
          </section>
        </main>
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

function PathCard({
  path,
  onAccept,
  onReject,
  onSelect,
}: {
  path: PathResult;
  onAccept: () => void;
  onReject: () => void;
  onSelect: () => void;
}) {
  return (
    <div className="rounded-md border border-slate-800 p-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-sm font-medium text-slate-100">
            {path.node_names.join(" → ")}
          </div>
          <div className="mt-1 text-xs text-slate-500">
            {path.relations.join(" → ")} · {path.path_id}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="badge badge-accent">{formatValue(path.score)}</span>
          <button className="button-ghost" onClick={onSelect}>
            select
          </button>
        </div>
      </div>
      <div className="mt-2 text-sm text-slate-300">
        {path.supporting_evidence?.join("; ") || "No supporting evidence text"}
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <button className="button" onClick={onAccept}>
          <ThumbsUp className="h-4 w-4" />
          Accept
        </button>
        <button className="button" onClick={onReject}>
          <ThumbsDown className="h-4 w-4" />
          Reject
        </button>
      </div>
    </div>
  );
}

function LabeledInput({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="block">
      <div className="field-label">{label}</div>
      <input className="input mt-1" value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function LabeledTextArea({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="block">
      <div className="field-label">{label}</div>
      <textarea
        className="input mt-1 min-h-28"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

function InfoField({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/60 p-3">
      <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-1 text-sm text-slate-100">{value}</div>
    </div>
  );
}

function WorkflowSteps({ steps }: { steps: RunStep[] }) {
  return (
    <div className="space-y-3">
      <div className="panel-title">Workflow steps</div>
      <div className="space-y-3">
        {steps.map((step, index) => (
          <details key={step.step_id} className="rounded-md border border-slate-800 bg-slate-950/50 p-3">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-3">
              <div>
                <div className="text-sm font-medium text-slate-100">
                  {index + 1}. {step.title}
                </div>
                <div className="mt-1 text-xs text-slate-500">{step.summary}</div>
              </div>
              <span className="badge">{step.status}</span>
            </summary>
            <pre className="scrollbar-thin mt-3 max-h-72 overflow-auto rounded-md border border-slate-800 bg-slate-950 p-3 text-xs text-slate-300">
              {JSON.stringify(step.details, null, 2)}
            </pre>
          </details>
        ))}
      </div>
    </div>
  );
}

function casePathCount(item: Record<string, unknown>) {
  const paths = item.top_k_paths;
  return Array.isArray(paths) ? paths.length : null;
}

function fieldsFromEvidence(evidence: Evidence) {
  return {
    anomaly_type: evidence.anomaly_type ?? "",
    location: evidence.location ?? "",
    morphology: evidence.morphology ?? "",
    variables: evidence.raw_evidence.variables.join("\n"),
    log_events: evidence.raw_evidence.log_events.join("\n"),
    severity: evidence.severity === null || evidence.severity === undefined ? "" : String(evidence.severity),
    confidence:
      evidence.confidence === null || evidence.confidence === undefined
        ? ""
        : String(evidence.confidence),
  };
}

function splitLines(value: string) {
  return value
    .replaceAll(",", "\n")
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseOptionalNumber(value: string) {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatValue(value: unknown) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  if (typeof value === "number") {
    return Number.isInteger(value) ? value.toString() : value.toFixed(4);
  }
  return String(value);
}

function messageOf(error: unknown) {
  return error instanceof Error ? error.message : "Unexpected error";
}
