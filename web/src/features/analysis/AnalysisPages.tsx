import {
  Alert,
  Button,
  Card,
  Empty,
  Input,
  InputNumber,
  Select,
  Space,
  Table,
  Tag,
  Typography
} from "@arco-design/web-react";
import type { TableColumnProps } from "@arco-design/web-react";
import {
  IconCheckCircle,
  IconCloseCircle,
  IconHistory,
  IconLaunch,
  IconUpload
} from "@arco-design/web-react/icon";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import type {
  DashboardBootstrap,
  PathGraph,
  PathGraphEdge,
  PathGraphPath,
  ReviewAction,
  ReviewTarget,
  RunDetail,
  RunSummary,
  UploadModeInfo
} from "../../api/contracts";
import { isRecord, recordList, shortId, valueText } from "../../api/format";
import { FieldGrid } from "../../components/common/FieldGrid";
import { JsonBlock } from "../../components/common/JsonBlock";
import { MetricCard } from "../../components/common/MetricCard";
import {
  graphFromPath,
  KnowledgeGraph
} from "../../components/graph/KnowledgeGraph";
import type { UploadFormState } from "../../state/app-state";

const { Title, Paragraph } = Typography;

const EXAMPLE_UPLOADS: Record<string, Array<{ path: string; label: string }>> = {
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

export function AnalysisLivePage({
  bootstrap,
  upload,
  loading,
  uploadStatus,
  onUploadChanged,
  onRunUpload
}: {
  bootstrap: DashboardBootstrap | null;
  upload: UploadFormState;
  loading: boolean;
  uploadStatus: string | null;
  onUploadChanged: (patch: Partial<UploadFormState>) => void;
  onRunUpload: () => void;
}) {
  const selectedMode = bootstrap?.upload_modes.find((mode) => mode.mode === upload.mode) ?? null;
  const presets = bootstrap?.mvtec_model_presets.presets ?? [];

  return (
    <div className="page-stack">
      <section className="hero-panel compact">
        <div>
          <span className="eyebrow">Live Analysis</span>
          <Title heading={2}>Run evidence through the KG pipeline</Title>
          <Paragraph>
            Upload producer records, evidence JSON, or a local image input while keeping model
            output and KG reasoning auditable.
          </Paragraph>
        </div>
      </section>

      <section className="analysis-live-grid">
        <Card title="Upload">
          <div className="form-grid">
            <label className="form-field">
              <span>Mode</span>
              <Select
                value={upload.mode}
                onChange={(value) => onUploadChanged({ mode: value as UploadFormState["mode"] })}
                options={(bootstrap?.upload_modes ?? []).map((mode) => ({
                  label: mode.label,
                  value: mode.mode
                }))}
              />
            </label>
            <label className="form-field">
              <span>Dataset</span>
              <Select
                value={upload.dataset}
                onChange={(value) => onUploadChanged({ dataset: String(value) })}
                options={[
                  { label: "auto", value: "" },
                  ...(bootstrap?.supported_datasets ?? []).map((dataset) => ({
                    label: dataset,
                    value: dataset
                  }))
                ]}
              />
            </label>
            <label className="form-field">
              <span>Top K</span>
              <InputNumber
                min={1}
                max={20}
                value={upload.topK}
                onChange={(value) => onUploadChanged({ topK: Number(value ?? 1) })}
              />
            </label>
            {upload.mode === "image" && (
              <>
                <label className="form-field">
                  <span>Object</span>
                  <Input
                    value={upload.objectName}
                    onChange={(value) => onUploadChanged({ objectName: value })}
                  />
                </label>
                <label className="form-field">
                  <span>Model preset</span>
                  <Select
                    value={upload.modelPreset}
                    onChange={(value) => onUploadChanged({ modelPreset: String(value) })}
                    options={[
                      { label: "auto", value: "auto" },
                      ...presets.map((preset) => ({
                        label: valueText(preset.preset),
                        value: String(preset.preset)
                      }))
                    ]}
                  />
                </label>
                <label className="form-field">
                  <span>Defect hint</span>
                  <Input
                    value={upload.defectType}
                    onChange={(value) => onUploadChanged({ defectType: value })}
                  />
                </label>
              </>
            )}
          </div>
          <div className="file-drop">
            <input
              type="file"
              onChange={(event) =>
                onUploadChanged({ file: event.currentTarget.files?.[0] ?? null })
              }
            />
            <IconUpload />
            <strong>{upload.file?.name ?? "Choose a local file"}</strong>
          </div>
          <Button type="primary" icon={<IconLaunch />} loading={loading} onClick={onRunUpload} long>
            Analyze
          </Button>
          {uploadStatus && <Alert type="success" title={uploadStatus} />}
        </Card>

        <ModeGuidance mode={selectedMode} uploadMode={upload.mode} />
      </section>
    </div>
  );
}

function ModeGuidance({
  mode,
  uploadMode
}: {
  mode: UploadModeInfo | null;
  uploadMode: UploadFormState["mode"];
}) {
  return (
    <Card title="Accepted Inputs">
      <p className="body-copy">{mode?.description ?? "Loading accepted file expectations."}</p>
      {mode && (
        <div className="tag-cloud">
          {mode.accepted_extensions.map((item) => (
            <Tag key={item}>{item}</Tag>
          ))}
          {mode.required_fields.map((item) => (
            <Tag key={item} color="arcoblue">
              {item}
            </Tag>
          ))}
        </div>
      )}
      <div className="example-list">
        {(EXAMPLE_UPLOADS[uploadMode] ?? []).map((item) => (
          <div key={item.path}>
            <strong>{item.label}</strong>
            <code>{item.path}</code>
          </div>
        ))}
      </div>
    </Card>
  );
}

export function AnalysisHistoryPage({
  runs,
  selectedRunId,
  onRefresh,
  onOpenRun
}: {
  runs: RunSummary[];
  selectedRunId: string | null;
  onRefresh: () => void;
  onOpenRun: (runId: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [dataset, setDataset] = useState("all");
  const datasets = Array.from(new Set(runs.map((run) => run.dataset ?? "unknown"))).sort();
  const visibleRuns = runs.filter((run) => {
    const datasetMatch = dataset === "all" || (run.dataset ?? "unknown") === dataset;
    const haystack = [
      run.label,
      run.run_id,
      run.source_filename,
      run.mode,
      run.dataset,
      run.status,
      run.model_backend,
      run.model_preset
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return datasetMatch && haystack.includes(query.toLowerCase());
  });
  const columns: TableColumnProps<RunSummary>[] = [
    {
      title: "Run",
      dataIndex: "label",
      render: (_, row) => (
        <Button type="text" onClick={() => onOpenRun(row.run_id)}>
          {shortId(row.label, 52)}
        </Button>
      )
    },
    { title: "Dataset", dataIndex: "dataset", render: valueText },
    { title: "Mode", dataIndex: "mode" },
    { title: "Cases", dataIndex: "case_count" },
    { title: "Evidence", dataIndex: "evidence_count" },
    {
      title: "Created",
      dataIndex: "created_at",
      render: (value) => new Date(String(value)).toLocaleString()
    },
    {
      title: "Status",
      dataIndex: "status",
      render: (value) => <Tag color={value === "completed" ? "green" : "red"}>{value}</Tag>
    }
  ];

  return (
    <div className="page-stack">
      <section className="toolbar-panel">
        <div>
          <span className="eyebrow">Run Lookup</span>
          <strong>{visibleRuns.length} visible analyses</strong>
        </div>
        <Space wrap>
          <Input.Search
            allowClear
            value={query}
            onChange={setQuery}
            placeholder="Search run, file, dataset, backend"
          />
          <Select
            value={dataset}
            onChange={(value) => setDataset(String(value))}
            options={[
              { label: "All datasets", value: "all" },
              ...datasets.map((item) => ({ label: item, value: item }))
            ]}
          />
          <Button icon={<IconHistory />} onClick={onRefresh}>
            Refresh
          </Button>
        </Space>
      </section>
      <Card title="Analysis History">
        <Table
          rowKey="run_id"
          columns={columns}
          data={visibleRuns}
          rowClassName={(record) => (record.run_id === selectedRunId ? "selected-table-row" : "")}
          pagination={{ pageSize: 8 }}
        />
      </Card>
    </div>
  );
}

export function AnalysisDetailPage({
  run,
  loading,
  selectedTarget,
  selectedTargetKey,
  reviewNote,
  reviewStatus,
  onLoadRun,
  onTargetSelected,
  onReviewNoteChanged,
  onSubmitReview,
  onOpenHistory
}: {
  run: RunDetail | null;
  loading: boolean;
  selectedTarget: ReviewTarget | undefined;
  selectedTargetKey: string;
  reviewNote: string;
  reviewStatus: string | null;
  onLoadRun: (runId: string) => void;
  onTargetSelected: (targetKey: string) => void;
  onReviewNoteChanged: (note: string) => void;
  onSubmitReview: (action: ReviewAction) => void;
  onOpenHistory: () => void;
}) {
  const { runId } = useParams();
  useEffect(() => {
    if (runId && run?.run.run_id !== runId) onLoadRun(runId);
  }, [onLoadRun, run?.run.run_id, runId]);

  if (!run && loading) {
    return <Card><Empty description="Loading analysis detail..." /></Card>;
  }
  if (!run) {
    return (
      <Card>
        <Empty description="Select a history item or upload evidence to inspect candidate paths." />
        <Button onClick={onOpenHistory}>Open history</Button>
      </Card>
    );
  }

  return (
    <RunDetailWorkspace
      run={run}
      selectedTarget={selectedTarget}
      selectedTargetKey={selectedTargetKey}
      reviewNote={reviewNote}
      reviewStatus={reviewStatus}
      onTargetSelected={onTargetSelected}
      onReviewNoteChanged={onReviewNoteChanged}
      onSubmitReview={onSubmitReview}
    />
  );
}

function RunDetailWorkspace({
  run,
  selectedTarget,
  selectedTargetKey,
  reviewNote,
  reviewStatus,
  onTargetSelected,
  onReviewNoteChanged,
  onSubmitReview
}: {
  run: RunDetail;
  selectedTarget: ReviewTarget | undefined;
  selectedTargetKey: string;
  reviewNote: string;
  reviewStatus: string | null;
  onTargetSelected: (targetKey: string) => void;
  onReviewNoteChanged: (note: string) => void;
  onSubmitReview: (action: ReviewAction) => void;
}) {
  const cases = run.cases ?? [];
  const [caseId, setCaseId] = useState("");
  useEffect(() => {
    setCaseId(cases.length > 0 ? valueText(cases[0].case_id) : "");
  }, [cases.length, run.run.run_id]);

  const selectedCase = cases.find((item) => valueText(item.case_id) === caseId) ?? cases[0];
  const evidence = asRecord(selectedCase?.generated_evidence) ?? run.evidence_summary ?? {};
  const linkedEntities = selectedCase ? recordList(selectedCase.linked_entities) : run.linked_entities;
  const corrections = selectedCase
    ? recordList(selectedCase.correction_candidates)
    : run.correction_candidates;
  const pathGraph = asPathGraph(selectedCase?.path_graph) ?? run.path_graph;
  const visualEvidence = selectedCase
    ? run.visual_evidence.filter((item) => item.case_id === valueText(selectedCase.case_id))
    : run.visual_evidence;
  const reviewTargets = selectedCase ? recordList(selectedCase.review_targets) : run.review_targets;

  return (
    <div className="page-stack">
      <section className="case-header">
        <div>
          <span className="eyebrow">Analysis Detail</span>
          <Title heading={2}>{run.run.label}</Title>
          <Paragraph>
            {run.run.source_filename} · {new Date(run.run.created_at).toLocaleString()}
          </Paragraph>
        </div>
        {cases.length > 1 && (
          <Select
            className="case-selector"
            value={valueText(selectedCase?.case_id)}
            onChange={(value) => setCaseId(String(value))}
            options={cases.map((item) => ({
              label: valueText(item.case_id),
              value: valueText(item.case_id)
            }))}
          />
        )}
      </section>

      <section className="metric-grid dense">
        <MetricCard label="dataset" value={valueText(evidence.dataset ?? run.run.dataset)} />
        <MetricCard label="object" value={valueText(evidence.object)} />
        <MetricCard label="anomaly" value={valueText(evidence.anomaly_type)} />
        <MetricCard label="linked" value={linkedEntities.length} />
        <MetricCard label="corrections" value={corrections.length} />
        <MetricCard label="paths" value={pathGraph.path_count || pathGraph.paths.length} />
      </section>

      <Alert type="warning" title={run.claim_boundary} />

      <section className="analysis-stage-grid">
        <EvidencePanel evidence={evidence} visualEvidence={visualEvidence} artifacts={run.artifacts} />
        <ListPanel title="Linked Entities" rows={linkedEntities} idField="link_id" labelField="selected_entity_id" />
        <ListPanel title="Correction Candidates" rows={corrections} idField="candidate_id" labelField="suggested_value" />
      </section>

      <ReasoningWorkspace
        paths={pathGraph.paths}
        selectedTarget={selectedTarget}
        selectedTargetKey={selectedTargetKey}
        onTargetSelected={onTargetSelected}
      />

      <section className="two-column">
        <Card title="Workflow">
          <div className="workflow-list">
            {run.workflow_steps.map((step) => (
              <div key={step.step_id} className="workflow-step">
                {step.status === "completed" ? <IconCheckCircle /> : <IconCloseCircle />}
                <div>
                  <strong>{step.title}</strong>
                  <span>{step.summary}</span>
                </div>
              </div>
            ))}
          </div>
        </Card>
        <ReviewPanel
          targets={run.review_targets}
          selectedTargetKey={selectedTargetKey}
          selectedTarget={selectedTarget}
          note={reviewNote}
          status={reviewStatus}
          onTargetSelected={onTargetSelected}
          onNoteChanged={onReviewNoteChanged}
          onSubmit={onSubmitReview}
        />
      </section>

      <Card title="Normalized Evidence">
        <JsonBlock value={run.evidence_with_analysis ?? run.evidence ?? run.summary} />
      </Card>
      {reviewTargets.length > 0 && <span className="visually-hidden">{reviewTargets.length}</span>}
    </div>
  );
}

function EvidencePanel({
  evidence,
  visualEvidence,
  artifacts
}: {
  evidence: Record<string, unknown>;
  visualEvidence: RunDetail["visual_evidence"];
  artifacts: Record<string, string>;
}) {
  return (
    <Card title="Observed Evidence">
      <FieldGrid
        record={evidence}
        fields={[
          "case_id",
          "dataset",
          "source",
          "object",
          "anomaly_type",
          "location",
          "morphology",
          "confidence"
        ]}
      />
      <div className="visual-strip">
        {visualEvidence.slice(0, 4).map((item) => (
          <article key={item.artifact_id}>
            <div className="visual-preview">
              {item.available && item.url ? (
                <img src={item.url} alt={`${item.title} for ${item.case_id}`} />
              ) : (
                <span>preview unavailable</span>
              )}
            </div>
            <strong>{item.title}</strong>
            <small>{item.kind}</small>
          </article>
        ))}
      </div>
      <div className="artifact-list">
        {Object.entries(artifacts).map(([key, value]) => (
          <code key={key}>{key}: {shortId(value, 54)}</code>
        ))}
      </div>
    </Card>
  );
}

function ListPanel({
  title,
  rows,
  idField,
  labelField
}: {
  title: string;
  rows: Array<Record<string, unknown>>;
  idField: string;
  labelField: string;
}) {
  return (
    <Card title={title}>
      {rows.length ? (
        <div className="compact-list">
          {rows.slice(0, 8).map((row, index) => (
            <div key={valueText(row[idField] ?? index)}>
              <strong>{shortId(valueText(row[labelField] ?? row[idField] ?? index), 48)}</strong>
              <span>{shortId(valueText(row[idField] ?? index), 60)}</span>
            </div>
          ))}
        </div>
      ) : (
        <Empty description="No items recorded." />
      )}
    </Card>
  );
}

function ReasoningWorkspace({
  paths,
  selectedTarget,
  selectedTargetKey,
  onTargetSelected
}: {
  paths: PathGraphPath[];
  selectedTarget: ReviewTarget | undefined;
  selectedTargetKey: string;
  onTargetSelected: (targetKey: string) => void;
}) {
  const activeTargetKey = selectedTarget?.target_key ?? selectedTargetKey;
  const selectedPath =
    paths.find((path) => path.target_key === activeTargetKey) ??
    paths.find((path) => path.edges.some((edge) => edge.target_key === activeTargetKey)) ??
    paths[0];
  const selectedEdge =
    selectedTarget?.target_type === "edge" || activeTargetKey
      ? selectedPath?.edges.find((edge) => edge.target_key === activeTargetKey) ??
        selectedPath?.edges[0]
      : selectedPath?.edges[0];
  const graph = useMemo(() => graphFromPath(selectedPath), [selectedPath]);
  const highlightedNodeIds = useMemo(() => graph.nodes.map((node) => node.id), [graph.nodes]);
  const highlightedEdgeIds = useMemo(() => graph.edges.map((edge) => edge.id), [graph.edges]);

  return (
    <section className="rca-explorer">
      <div className="rca-explorer-header">
        <div>
          <span className="eyebrow">RCA Explorer</span>
          <strong>Candidate root-cause paths</strong>
        </div>
        <Tag color="arcoblue">{paths.length} ranked paths</Tag>
      </div>
      {paths.length > 0 && selectedPath ? (
        <div className="rca-explorer-grid">
          <div className="path-picker">
            {paths.slice(0, 8).map((path, index) => (
              <button
                key={path.path_id}
                className={selectedPath.path_id === path.path_id ? "selected" : ""}
                onClick={() => onTargetSelected(path.target_key)}
              >
                <span className="path-rank">#{index + 1}</span>
                <strong>{shortId(valueText(path.target_entity_id ?? "candidate"), 38)}</strong>
                <small>{pathHint(path)}</small>
                <span className="path-metrics">
                  <span>score {formatMetric(path.score)}</span>
                  <span>conf {formatMetric(path.confidence)}</span>
                </span>
              </button>
            ))}
          </div>
          <div className="graph-panel rca-graph-panel">
            <KnowledgeGraph
              nodes={graph.nodes}
              edges={graph.edges}
              selectedTargetKey={selectedEdge?.target_key}
              highlightedNodeIds={highlightedNodeIds}
              highlightedEdgeIds={highlightedEdgeIds}
              layoutMode="path"
              edgeLabelMode="highlighted"
              showLegend={false}
              height={560}
              onSelectEdge={(edge) => edge.targetKey && onTargetSelected(edge.targetKey)}
            />
          </div>
          <PathInspectorPanel path={selectedPath} edge={selectedEdge} />
        </div>
      ) : (
        <Empty description="This run returned no candidate reasoning paths." />
      )}
    </section>
  );
}

function PathInspectorPanel({
  path,
  edge
}: {
  path: PathGraphPath;
  edge: PathGraphEdge | undefined;
}) {
  return (
    <aside className="path-inspector-panel">
      <div>
        <span className="eyebrow">Selected Path</span>
        <strong>{shortId(valueText(path.target_entity_id ?? path.path_id), 44)}</strong>
        <small>{pathHint(path)}</small>
      </div>
      <div className="path-score-strip">
        <span>score <strong>{formatMetric(path.score)}</strong></span>
        <span>confidence <strong>{formatMetric(path.confidence)}</strong></span>
      </div>
      {edge ? (
        <div className="provenance-panel">
          <strong>Edge provenance</strong>
          <div className="provenance-list">
            <span>edge</span><strong>{shortId(edge.edge_id)}</strong>
            <span>relation</span><strong>{edge.relation}</strong>
            <span>source</span><strong>{valueText(edge.source)}</strong>
            <span>confidence</span><strong>{formatMetric(edge.confidence)}</strong>
            <span>review</span><strong>{valueText(edge.review_status)}</strong>
            <span>evidence</span><p>{valueText(edge.evidence)}</p>
          </div>
        </div>
      ) : (
        <Empty description="Select a path edge to inspect source evidence." />
      )}
      <div className="supporting-evidence-panel">
        <strong>Supporting evidence</strong>
        {path.supporting_evidence.length ? (
          <div className="supporting-evidence-list">
            {path.supporting_evidence.slice(0, 5).map((item, index) => (
              <EvidenceSnippet key={`${path.path_id}-evidence-${index}`} value={item} />
            ))}
          </div>
        ) : (
          <Empty description="No supporting evidence was attached to this path." />
        )}
      </div>
    </aside>
  );
}

function EvidenceSnippet({ value }: { value: unknown }) {
  if (isRecord(value)) {
    return (
      <div>
        {Object.entries(value)
          .slice(0, 4)
          .map(([key, item]) => (
            <p key={key}>
              <span>{key}</span>
              <strong>{shortId(valueText(item), 92)}</strong>
            </p>
          ))}
      </div>
    );
  }
  return (
    <div>
      <p>
        <span>evidence</span>
        <strong>{shortId(valueText(value), 120)}</strong>
      </p>
    </div>
  );
}

function pathHint(path: PathGraphPath): string {
  const firstNode = path.nodes[0];
  const lastNode = path.nodes[path.nodes.length - 1];
  const source = path.source_entity_id ?? firstNode?.label ?? firstNode?.node_id;
  const target = path.target_entity_id ?? lastNode?.label ?? lastNode?.node_id;
  if (source && target) return `${source} -> ${target}`;
  return shortId(path.path_id, 48);
}

function formatMetric(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(3) : valueText(value);
}

function ReviewPanel({
  targets,
  selectedTargetKey,
  selectedTarget,
  note,
  status,
  onTargetSelected,
  onNoteChanged,
  onSubmit
}: {
  targets: ReviewTarget[];
  selectedTargetKey: string;
  selectedTarget: ReviewTarget | undefined;
  note: string;
  status: string | null;
  onTargetSelected: (targetKey: string) => void;
  onNoteChanged: (note: string) => void;
  onSubmit: (action: ReviewAction) => void;
}) {
  return (
    <Card title="Review Targets">
      <Select
        value={selectedTargetKey}
        onChange={(value) => onTargetSelected(String(value))}
        options={targets.map((target) => ({
          label: `${target.target_type} · ${shortId(target.label, 44)}`,
          value: target.target_key
        }))}
      />
      <Input.TextArea
        value={note}
        onChange={onNoteChanged}
        placeholder="optional review note"
        disabled={!selectedTarget}
      />
      <Space wrap>
        <Button disabled={!selectedTarget} onClick={() => onSubmit("accept")}>
          Accept
        </Button>
        <Button disabled={!selectedTarget} onClick={() => onSubmit("reject")}>
          Reject
        </Button>
        <Button disabled={!selectedTarget} onClick={() => onSubmit("needs_review")}>
          Needs review
        </Button>
      </Space>
      {status && <Alert type="success" title={`Feedback ${status}.`} />}
    </Card>
  );
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return isRecord(value) ? value : null;
}

function asPathGraph(value: unknown): PathGraph | null {
  const record = asRecord(value);
  if (!record || !Array.isArray(record.paths)) return null;
  return record as unknown as PathGraph;
}
