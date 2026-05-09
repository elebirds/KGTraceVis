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
  displayFeedbackDecision,
  displayFeedbackTarget,
  displayDataset,
  displayRunStatus,
  displaySourceKind,
  displayUploadMode,
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
type UploadMode = "evidence" | "records" | "image";

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
  const [uploadMode, setUploadMode] = useState<UploadMode>("records");
  const [uploadDataset, setUploadDataset] = useState("");
  const [uploadObjectName, setUploadObjectName] = useState("capsule");
  const [uploadDefectType, setUploadDefectType] = useState("crack");
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
      setActionMessage(`已加载样本 ${caseId}`);
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
      setRunMessage(`已加载运行 ${runId}`);
      setRunError("");
    } catch (error_) {
      setRunLoadingState("error");
      setRunError(messageOf(error_));
    }
  }

  async function uploadSampleRun() {
    if (!uploadFile) {
      setRunError("请先选择文件");
      return;
    }
    if (uploadMode === "image" && !uploadObjectName.trim()) {
      setRunError("图片模式需要填写 MVTec 对象类别");
      return;
    }
    try {
      setRunLoadingState("loading");
      const response = await uploadRun({
        file: uploadFile,
        mode: uploadMode,
        dataset: uploadMode === "image" ? "mvtec" : uploadDataset || null,
        object_name: uploadMode === "image" ? uploadObjectName : null,
        defect_type: uploadMode === "image" ? uploadDefectType : null,
        top_k: uploadTopK,
      });
      setRuns((current) => [response.run, ...current.filter((item) => item.run_id !== response.run.run_id)]);
      setSelectedRun(response);
      setSelectedRunId(response.run.run_id);
      setQueueView("runs");
      setRunMessage(`已按“${displayUploadMode(uploadMode)}”运行 ${uploadFile.name}`);
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
      setActionMessage(`已分析样本 ${draftEvidence.case_id}`);
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
      setActionMessage(`已更新样本 ${draftEvidence.case_id} 的假设分析`);
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
      setActionMessage(`反馈已保存到 ${response.feedback_path}`);
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
              <span className="badge badge-accent">生产作业台</span>
              <span className="badge">候选 RCA，非已验证标签</span>
            </div>
            <div className="mt-1 truncate text-sm text-zinc-400">
              上传样本，运行适配器和 KGTracePipeline，逐步查看输出，并记录审核反馈。
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <MetricChip icon={Database} label="样本" value={String(cases.length)} />
            <MetricChip icon={History} label="运行" value={String(runs.length)} />
            <MetricChip icon={Activity} label="状态" value={loadingState === "error" ? "需处理" : "就绪"} />
            <button className="button" onClick={() => void refreshWorkspace()}>
              <RefreshCw className="h-4 w-4" />
              刷新
            </button>
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-[1700px] gap-4 px-4 py-4 2xl:grid-cols-[330px_minmax(0,1fr)_380px]">
        <aside className="min-w-0 space-y-4">
          <section className="surface">
            <SectionHeader
              icon={UploadCloud}
              title="数据接入"
              subtitle="从 Evidence JSON 或原始记录包启动一次运行。"
            />
            <div className="space-y-3 p-4">
              <label className="block">
                <div className="field-label">样本文件</div>
                <input
                  key={uploadInputKey}
                  className="input mt-1"
                  type="file"
                  accept={
                    uploadMode === "image"
                      ? ".png,.jpg,.jpeg,.bmp,.tif,.tiff,image/*"
                      : ".json,.jsonl,.csv,application/json,text/csv"
                  }
                  onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)}
                />
              </label>
              <div>
                <div className="field-label">输入模式</div>
                <div className="mt-1 grid grid-cols-3 gap-2">
                  <button
                    className={uploadMode === "image" ? "segmented-active" : "segmented"}
                    onClick={() => {
                      setUploadMode("image");
                      setUploadDataset("mvtec");
                    }}
                    type="button"
                  >
                    图片模式
                  </button>
                  <button
                    className={uploadMode === "records" ? "segmented-active" : "segmented"}
                    onClick={() => setUploadMode("records")}
                    type="button"
                  >
                    记录包
                  </button>
                  <button
                    className={uploadMode === "evidence" ? "segmented-active" : "segmented"}
                    onClick={() => setUploadMode("evidence")}
                    type="button"
                  >
                    Evidence JSON
                  </button>
                </div>
              </div>
              {uploadMode === "image" ? (
                <div className="rounded-md border border-cyan-800/70 bg-cyan-950/30 p-3">
                  <div className="mb-3 text-xs leading-5 text-cyan-100">
                    图片模式会调用 MVTec producer 和当前 OpenVINO checkpoint，再进入 KGTracePipeline。
                    对象类别应与模型 checkpoint 匹配；当前内置 checkpoint 是 capsule。
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <label className="block">
                      <div className="field-label">对象类别</div>
                      <input
                        className="input mt-1"
                        value={uploadObjectName}
                        onChange={(event) => setUploadObjectName(event.target.value)}
                        placeholder="capsule"
                      />
                    </label>
                    <label className="block">
                      <div className="field-label">缺陷类型</div>
                      <input
                        className="input mt-1"
                        value={uploadDefectType}
                        onChange={(event) => setUploadDefectType(event.target.value)}
                        placeholder="crack / good / unknown"
                      />
                    </label>
                  </div>
                </div>
              ) : null}
              <div className="grid grid-cols-[minmax(0,1fr)_88px] gap-3">
                <label className="block">
                  <div className="field-label">数据集覆盖</div>
                  <select
                    className="input mt-1"
                    value={uploadDataset}
                    disabled={uploadMode === "image"}
                    onChange={(event) => setUploadDataset(event.target.value)}
                  >
                    <option value="">自动识别</option>
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
                  已选择：<span className="text-zinc-100">{uploadFile.name}</span>
                </div>
              ) : null}
              <div className="flex flex-wrap gap-2">
                <button className="button-primary" onClick={() => void uploadSampleRun()}>
                  <Play className="h-4 w-4" />
                  上传并运行
                </button>
                <button
                  className="button"
                  onClick={() => {
                    setUploadFile(null);
                    setUploadDataset("");
                    setUploadMode("records");
                    setUploadObjectName("capsule");
                    setUploadDefectType("crack");
                    setUploadInputKey((current) => current + 1);
                  }}
                >
                  <RotateCcw className="h-4 w-4" />
                  清空
                </button>
              </div>
            </div>
          </section>

          <section className="surface">
            <SectionHeader
              icon={ListChecks}
              title="工作队列"
              subtitle="选择一次运行会话，或查看可复用的 Evidence 样本。"
            />
            <div className="border-b border-zinc-800 p-3">
              <div className="grid grid-cols-2 gap-2">
                <button
                  className={queueView === "runs" ? "segmented-active" : "segmented"}
                  onClick={() => setQueueView("runs")}
                  type="button"
                >
                  运行
                </button>
                <button
                  className={queueView === "cases" ? "segmented-active" : "segmented"}
                  onClick={() => setQueueView("cases")}
                  type="button"
                >
                  样本
                </button>
              </div>
              <div className="relative mt-3">
                <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-zinc-500" />
                <input
                  className="input pl-9"
                  placeholder={queueView === "runs" ? "筛选运行、文件、数据集..." : "筛选样本、数据集、来源..."}
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

        <main className="min-w-0 space-y-4">
          <section className="surface">
            <SectionHeader
              icon={GitBranch}
              title="运行会话"
              subtitle={selectedRun ? selectedRun.run.label : "尚未选择运行"}
              actions={
                selectedRun ? (
                  <div className="flex flex-wrap gap-2">
                    <span className="badge">{displayUploadMode(selectedRun.run.mode)}</span>
                    <span className="badge">{displayRunStatus(selectedRun.run.status)}</span>
                    <span className="badge">{displayDataset(selectedRun.run.dataset)}</span>
                  </div>
                ) : null
              }
            />
            <div className="p-4">
              {selectedRun ? (
                <div className="space-y-4">
                  <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-4">
                    <InfoField label="来源文件" value={selectedRun.run.source_filename} />
                    <InfoField label="创建时间" value={selectedRun.run.created_at} />
                    <InfoField label="样本数" value={String(selectedRun.run.case_count)} />
                    <InfoField label="Evidence 数" value={String(selectedRun.run.evidence_count)} />
                  </div>
                  <WorkflowSteps steps={selectedRun.workflow_steps} />
                  {selectedRun.cases?.length ? (
                    <div>
                      <div className="panel-title">本次运行产出的样本</div>
                      <div className="table-shell mt-3">
                        <table className="min-w-full text-sm">
                          <thead>
                            <tr>
                              <th>样本</th>
                              <th>数据集</th>
                              <th>链接数</th>
                              <th>一致性</th>
                              <th>路径数</th>
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
                                  <td>{String(item.dataset ?? "未知")}</td>
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
                      产物和持久化路径
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
                  title="尚未选择运行"
                  body="上传文件或从队列中选择运行后，这里会展示执行轨迹。"
                />
              )}
            </div>
          </section>

          <section className="surface">
            <SectionHeader
              icon={Layers3}
              title="样本工作台"
              subtitle={selectedCaseSummary?.label ?? selectedCaseId ?? "尚未选择样本"}
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
                    运行分析
                  </button>
                </div>
              }
            />
            <div className="space-y-4 p-4">
              <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-5">
                <MetricBlock label="实体链接" value={String(linkedCount)} />
                <MetricBlock label="一致性" value={formatValue(analysis?.consistency_score)} />
                <MetricBlock label="不一致字段" value={String(analysis?.inconsistent_fields.length ?? 0)} />
                <MetricBlock label="修正候选" value={String(correctionCount)} />
                <MetricBlock label="候选路径" value={String(pathCount)} />
              </div>

              <div className="flex flex-wrap gap-2 text-xs">
                <span className="badge">{displayDataset(caseEvidence?.dataset)}</span>
                <span className="badge">{caseEvidence?.source ?? "-"}</span>
                {selectedCaseSummary?.source_kind ? (
                  <span className="badge badge-accent">{displaySourceKind(selectedCaseSummary.source_kind)}</span>
                ) : null}
                <span className="badge max-w-full whitespace-normal break-words">{activeClaim}</span>
              </div>

              <div className="grid min-w-0 gap-4 2xl:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]">
                <div className="min-w-0 space-y-4">
                  <Subsection title="观测 Evidence">
                    {caseEvidence ? (
                      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                        <InfoField label="对象" value={caseEvidence.object} />
                        <InfoField label="异常类型" value={caseEvidence.anomaly_type} />
                        <InfoField label="位置" value={caseEvidence.location ?? "-"} />
                        <InfoField label="形态" value={caseEvidence.morphology ?? "-"} />
                        <InfoField label="严重度" value={formatValue(caseEvidence.severity)} />
                        <InfoField label="置信度" value={formatValue(caseEvidence.confidence)} />
                      </div>
                    ) : (
                      <EmptyState title="尚未加载 Evidence" body="选择样本后可以查看归一化 Evidence。" />
                    )}
                  </Subsection>

                  <Subsection title="观测流">
                    <div className="table-shell max-h-80">
                      <table className="min-w-full text-sm">
                        <thead>
                          <tr>
                            <th>维度</th>
                            <th>名称</th>
                            <th>置信度</th>
                            <th>来源</th>
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

                <div className="min-w-0 space-y-4">
                  <Subsection title="KG 实体链接">
                    <LinkedEntitiesTable links={analysis?.linked_entities ?? []} />
                  </Subsection>

                  <Subsection title="修正候选">
                    <CorrectionTable candidates={analysis?.correction_candidates ?? []} />
                  </Subsection>

                  <Subsection title="候选解释路径">
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
                        <EmptyState title="暂无候选路径" body="运行分析后会生成排序后的候选解释路径。" />
                      )}
                    </div>
                  </Subsection>
                </div>
              </div>
            </div>
          </section>
        </main>

        <aside className="min-w-0 space-y-4">
          <section className="surface 2xl:sticky 2xl:top-[5.25rem]">
            <SectionHeader
              icon={SlidersHorizontal}
              title="检查器"
              subtitle="编辑字段、检查载荷，并提交人工审核意见。"
            />
            <div className="border-b border-zinc-800 p-3">
              <div className="grid grid-cols-3 gap-2">
                <button
                  className={inspectorView === "what-if" ? "segmented-active" : "segmented"}
                  onClick={() => setInspectorView("what-if")}
                  type="button"
                >
                  编辑
                </button>
                <button
                  className={inspectorView === "payload" ? "segmented-active" : "segmented"}
                  onClick={() => setInspectorView("payload")}
                  type="button"
                >
                  载荷
                </button>
                <button
                  className={inspectorView === "feedback" ? "segmented-active" : "segmented"}
                  onClick={() => setInspectorView("feedback")}
                  type="button"
                >
                  审核
                </button>
              </div>
            </div>

            {inspectorView === "what-if" ? (
              <div className="space-y-3 p-4">
                <div className="flex items-center gap-2 text-sm text-zinc-300">
                  <SlidersHorizontal className="h-4 w-4 text-cyan-300" />
                  假设编辑会作用于当前样本 Evidence。
                </div>
                <LabeledInput
                  label="异常类型"
                  value={whatIf.anomaly_type}
                  onChange={(value) => setWhatIf((current) => ({ ...current, anomaly_type: value }))}
                />
                <div className="grid grid-cols-2 gap-3">
                  <LabeledInput
                    label="位置"
                    value={whatIf.location}
                    onChange={(value) => setWhatIf((current) => ({ ...current, location: value }))}
                  />
                  <LabeledInput
                    label="形态"
                    value={whatIf.morphology}
                    onChange={(value) => setWhatIf((current) => ({ ...current, morphology: value }))}
                  />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <LabeledInput
                    label="严重度"
                    value={whatIf.severity}
                    onChange={(value) => setWhatIf((current) => ({ ...current, severity: value }))}
                  />
                  <LabeledInput
                    label="置信度"
                    value={whatIf.confidence}
                    onChange={(value) => setWhatIf((current) => ({ ...current, confidence: value }))}
                  />
                </div>
                <LabeledTextArea
                  label="变量"
                  value={whatIf.variables}
                  onChange={(value) => setWhatIf((current) => ({ ...current, variables: value }))}
                />
                <LabeledTextArea
                  label="日志事件"
                  value={whatIf.log_events}
                  onChange={(value) => setWhatIf((current) => ({ ...current, log_events: value }))}
                />
                <div className="flex flex-wrap gap-2">
                  <button className="button-primary" onClick={() => void rerunWhatIf()}>
                    <Send className="h-4 w-4" />
                    运行假设分析
                  </button>
                  <button
                    className="button"
                    onClick={() => draftEvidence && setWhatIf(fieldsFromEvidence(draftEvidence))}
                  >
                    <RotateCcw className="h-4 w-4" />
                    重置
                  </button>
                </div>
              </div>
            ) : null}

            {inspectorView === "payload" ? (
              <div className="space-y-4 p-4">
                <div>
                  <div className="panel-title">当前载荷</div>
                  <pre className="scrollbar-thin mt-3 max-h-[32rem] overflow-auto rounded-md border border-zinc-800 bg-zinc-950 p-3 text-xs text-zinc-300">
                    {JSON.stringify(activePayload, null, 2)}
                  </pre>
                </div>
                <div>
                  <div className="panel-title">执行步骤</div>
                  <WorkflowSteps steps={workflowSteps} compact />
                </div>
              </div>
            ) : null}

            {inspectorView === "feedback" ? (
              <div className="space-y-3 p-4">
                <div className="flex items-center gap-2 text-sm text-zinc-300">
                  <MessageSquare className="h-4 w-4 text-amber-300" />
                  反馈会作为审核记录保存，供后续更新 KG 和路径排序时使用。
                </div>
                <label className="block">
                  <div className="field-label">目标类型</div>
                  <select
                    className="input mt-1"
                    value={feedbackTargetType}
                    onChange={(event) =>
                      setFeedbackTargetType(
                        event.target.value as "case" | "link" | "correction" | "path",
                      )
                    }
                  >
                    <option value="path">{displayFeedbackTarget("path")}</option>
                    <option value="case">{displayFeedbackTarget("case")}</option>
                    <option value="link">{displayFeedbackTarget("link")}</option>
                    <option value="correction">{displayFeedbackTarget("correction")}</option>
                  </select>
                </label>
                <label className="block">
                  <div className="field-label">决定</div>
                  <select
                    className="input mt-1"
                    value={feedbackDecision}
                    onChange={(event) =>
                      setFeedbackDecision(event.target.value as "accept" | "reject" | "comment")
                    }
                  >
                    <option value="accept">{displayFeedbackDecision("accept")}</option>
                    <option value="reject">{displayFeedbackDecision("reject")}</option>
                    <option value="comment">{displayFeedbackDecision("comment")}</option>
                  </select>
                </label>
                <label className="block">
                  <div className="field-label">目标 ID</div>
                  <input
                    className="input mt-1"
                    value={feedbackPathId}
                    onChange={(event) => setFeedbackPathId(event.target.value)}
                    placeholder="case_id、path_id、link_id 等"
                  />
                </label>
                <label className="block">
                  <div className="field-label">备注</div>
                  <textarea
                    className="input mt-1 min-h-28"
                    value={feedbackNote}
                    onChange={(event) => setFeedbackNote(event.target.value)}
                    placeholder="可选备注"
                  />
                </label>
                <div className="flex flex-wrap gap-2">
                  <button
                    className="button-primary"
                    onClick={() => void submitFeedback(feedbackTargetType)}
                  >
                    <ThumbsUp className="h-4 w-4" />
                    保存反馈
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
                    样本备注
                  </button>
                </div>
              </div>
            ) : null}
          </section>

          <section className="surface">
            <SectionHeader icon={Activity} title="事件日志" subtitle="最近的界面和 API 状态。" />
            <div className="space-y-2 p-4 text-sm">
              {runMessage ? <LogLine tone="good" text={runMessage} /> : null}
              {actionMessage ? <LogLine tone="good" text={actionMessage} /> : null}
              {runError ? <LogLine tone="bad" text={runError} /> : null}
              {error ? <LogLine tone="bad" text={error} /> : null}
              {!runMessage && !actionMessage && !runError && !error ? (
                <div className="text-zinc-500">暂无近期事件。</div>
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
      setActionMessage(`反馈已保存到 ${response.feedback_path}`);
      setError("");
    } catch (error_) {
      setError(messageOf(error_));
    }
  }
}
