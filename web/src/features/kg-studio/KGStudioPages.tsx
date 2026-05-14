import {
  Alert,
  Button,
  Card,
  Empty,
  Input,
  InputNumber,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography
} from "@arco-design/web-react";
import type { TableColumnProps } from "@arco-design/web-react";
import { IconCheckCircle, IconRefresh } from "@arco-design/web-react/icon";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { KG_STUDIO_TABS } from "../../app/routes";
import type {
  KGConstructionBuildResponse,
  KGConstructionSourceFormat,
  KGConstructionSourceType,
  KGDraftAction,
  KGSourceDraftResponse,
  KGStudioGraphEdge,
  KGStudioPayload,
  KGStudioReviewTarget,
  ReviewAction
} from "../../api/contracts";
import { shortId, valueText } from "../../api/format";
import { JsonBlock } from "../../components/common/JsonBlock";
import { MetricCard } from "../../components/common/MetricCard";
import {
  graphFromKGStudio,
  KnowledgeGraph
} from "../../components/graph/KnowledgeGraph";

const { Title, Paragraph } = Typography;

export type KGStudioView = "overview" | "sources" | "build" | "graph" | "review" | "drafts";

interface KGFilters {
  query: string;
  scenario: string;
  source: string;
  reviewStatus: string;
}

interface KGConstructionBuildForm {
  outputName: string;
  overwrite: boolean;
  sourceType: KGConstructionSourceType;
  sourceId: string;
  scenario: string;
  sourceFormat: KGConstructionSourceFormat;
  sourcePath: string;
  sourceText: string;
  semanticNodesPath: string;
  semanticEdgesPath: string;
}

const EMPTY_FILTERS: KGFilters = {
  query: "",
  scenario: "all",
  source: "all",
  reviewStatus: "all"
};

export function KGStudioPage({
  view,
  payload,
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
  constructionBuild,
  constructionResult,
  constructionStatus,
  onRefresh,
  onTargetSelected,
  onReviewNoteChanged,
  onSubmitReview,
  onDraftChanged,
  onSubmitDraft,
  onSourceDraftChanged,
  onGenerateSourceDraft,
  onConstructionBuildChanged,
  onBuildKGConstruction
}: {
  view: KGStudioView;
  payload: KGStudioPayload | null;
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
  constructionBuild: KGConstructionBuildForm;
  constructionResult: KGConstructionBuildResponse | null;
  constructionStatus: string | null;
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
  onConstructionBuildChanged: (patch: Partial<KGConstructionBuildForm>) => void;
  onBuildKGConstruction: () => void;
}) {
  const navigate = useNavigate();
  const [filters, setFilters] = useState<KGFilters>(EMPTY_FILTERS);
  const [showGraphLabels, setShowGraphLabels] = useState(false);
  const filteredEdges = useMemo(
    () => filterGraphEdges(payload?.graph_edges ?? [], filters),
    [filters, payload?.graph_edges]
  );
  const selectedEdge = filteredEdges.find((edge) => edge.target_key === selectedTargetKey);
  const filteredTargets = useMemo(
    () => reviewTargetsForEdges(payload?.review_targets ?? [], filteredEdges),
    [filteredEdges, payload?.review_targets]
  );
  const selectedTarget = filteredTargets.find((target) => target.target_key === selectedTargetKey);
  const options = useMemo(() => edgeFilterOptions(payload?.graph_edges ?? []), [payload?.graph_edges]);

  return (
    <div className="page-stack">
      <section className="hero-panel compact">
        <div>
          <span className="eyebrow">KG Studio</span>
          <Title heading={2}>Source-grounded graph management</Title>
          <Paragraph>
            Inspect provenance, generate candidate edges, and record reviewable graph changes
            without mutating tracked KG files.
          </Paragraph>
        </div>
        <Button icon={<IconRefresh />} onClick={onRefresh}>
          Refresh KG
        </Button>
      </section>

      <nav className="subnav" aria-label="KG Studio sections">
        {KG_STUDIO_TABS.map((tab) => (
          <button
            key={tab.key}
            className={view === tab.key ? "active" : ""}
            onClick={() => navigate(tab.path)}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {!payload ? (
        <Card><Empty description="Reading source registry and candidate KG artifacts." /></Card>
      ) : (
        <>
          {view === "graph" ? (
            <KGGraphStatusStrip note={payload.note} totalEdges={payload.graph_edges.length} />
          ) : (
            <Alert type="warning" title={payload.note} />
          )}
          {["review", "drafts"].includes(view) && (
            <KGFilterBar
              filters={filters}
              options={options}
              onChange={(patch) => setFilters((current) => ({ ...current, ...patch }))}
            />
          )}
          {view === "overview" && <KGOverview payload={payload} />}
          {view === "sources" && (
            <KGSources
              payload={payload}
              sourceDraftText={sourceDraftText}
              sourceDraftSourceId={sourceDraftSourceId}
              sourceDraftScenario={sourceDraftScenario}
              sourceDraftConfidence={sourceDraftConfidence}
              sourceDraftResult={sourceDraftResult}
              onSourceDraftChanged={onSourceDraftChanged}
              onGenerateSourceDraft={onGenerateSourceDraft}
            />
          )}
          {view === "build" && (
            <KGConstructionBuild
              payload={payload}
              form={constructionBuild}
              result={constructionResult}
              status={constructionStatus}
              onChange={onConstructionBuildChanged}
              onBuild={onBuildKGConstruction}
              onOpenGraph={() => navigate("/kg-studio/graph")}
            />
          )}
          {view === "graph" && (
            <KGGraphBrowser
              payload={payload}
              edges={filteredEdges}
              filters={filters}
              options={options}
              selectedEdge={selectedEdge}
              selectedTargetKey={selectedTargetKey}
              showLabels={showGraphLabels}
              onFiltersChanged={(patch) => setFilters((current) => ({ ...current, ...patch }))}
              onShowLabelsChanged={setShowGraphLabels}
              onTargetSelected={onTargetSelected}
            />
          )}
          {view === "review" && (
            <KGReview
              edges={filteredEdges}
              targets={filteredTargets}
              selectedEdge={selectedEdge}
              selectedTarget={selectedTarget}
              selectedTargetKey={selectedTargetKey}
              reviewNote={reviewNote}
              reviewStatus={reviewStatus}
              onTargetSelected={onTargetSelected}
              onReviewNoteChanged={onReviewNoteChanged}
              onSubmitReview={onSubmitReview}
            />
          )}
          {view === "drafts" && (
            <KGDrafts
              targets={filteredTargets}
              selectedEdge={selectedEdge}
              selectedTargetKey={selectedTargetKey}
              draftAction={draftAction}
              draftRelation={draftRelation}
              draftEvidence={draftEvidence}
              draftConfidence={draftConfidence}
              draftStatus={draftStatus}
              onTargetSelected={onTargetSelected}
              onDraftChanged={onDraftChanged}
              onSubmitDraft={onSubmitDraft}
            />
          )}
        </>
      )}
    </div>
  );
}

function KGOverview({ payload }: { payload: KGStudioPayload }) {
  return (
    <>
      <section className="metric-grid">
        <MetricCard label="nodes" value={payload.node_count} hint={shortId(payload.nodes_path)} />
        <MetricCard label="edges" value={payload.edge_count} hint={shortId(payload.edges_path)} />
        <MetricCard
          label="sources"
          value={payload.sources.length}
          hint={shortId(payload.source_registry_path)}
        />
        <MetricCard
          label="avg confidence"
          value={valueText(payload.confidence_summary.mean)}
          hint="candidate edges"
        />
      </section>
      <section className="two-column">
        <Card title="Scenario Coverage">
          <div className="tag-cloud">
            {Object.entries(payload.scenario_counts).map(([scenario, count]) => (
              <Tag key={scenario} color="arcoblue">
                {scenario}: {count}
              </Tag>
            ))}
          </div>
        </Card>
        <Card title="Validation Summary">
          <JsonBlock value={payload.validation_summary ?? payload.confidence_summary} />
        </Card>
      </section>
    </>
  );
}

function KGSources({
  payload,
  sourceDraftText,
  sourceDraftSourceId,
  sourceDraftScenario,
  sourceDraftConfidence,
  sourceDraftResult,
  onSourceDraftChanged,
  onGenerateSourceDraft
}: {
  payload: KGStudioPayload;
  sourceDraftText: string;
  sourceDraftSourceId: string;
  sourceDraftScenario: string;
  sourceDraftConfidence: string;
  sourceDraftResult: KGSourceDraftResponse | null;
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
  return (
    <section className="two-column wide-left">
      <Card title="Source Registry">
        <Table
          rowKey="source_id"
          data={payload.sources}
          pagination={{ pageSize: 8 }}
          columns={[
            { title: "Source", dataIndex: "source_id", render: (value) => shortId(String(value), 32) },
            { title: "Title", dataIndex: "title" },
            { title: "Type", dataIndex: "source_type" },
            { title: "Used for", dataIndex: "used_for" }
          ]}
        />
      </Card>
      <Card title="Heuristic Source Draft">
        <div className="form-grid single">
          <label className="form-field">
            <span>Source ID</span>
            <Input value={sourceDraftSourceId} onChange={(value) => onSourceDraftChanged({ sourceDraftSourceId: value })} />
          </label>
          <label className="form-field">
            <span>Scenario</span>
            <Input value={sourceDraftScenario} onChange={(value) => onSourceDraftChanged({ sourceDraftScenario: value })} />
          </label>
          <label className="form-field">
            <span>Confidence</span>
            <InputNumber
              min={0}
              max={1}
              step={0.05}
              value={Number(sourceDraftConfidence)}
              onChange={(value) => onSourceDraftChanged({ sourceDraftConfidence: String(value ?? 0.55) })}
            />
          </label>
          <label className="form-field">
            <span>Source text or CSV row</span>
            <Input.TextArea
              value={sourceDraftText}
              onChange={(value) => onSourceDraftChanged({ sourceDraftText: value })}
              autoSize={{ minRows: 5, maxRows: 8 }}
            />
          </label>
        </div>
        <Button type="primary" onClick={onGenerateSourceDraft}>
          Generate candidate edge
        </Button>
        {sourceDraftResult && <JsonBlock value={sourceDraftResult} />}
      </Card>
    </section>
  );
}

function KGConstructionBuild({
  payload,
  form,
  result,
  status,
  onChange,
  onBuild,
  onOpenGraph
}: {
  payload: KGStudioPayload;
  form: KGConstructionBuildForm;
  result: KGConstructionBuildResponse | null;
  status: string | null;
  onChange: (patch: Partial<KGConstructionBuildForm>) => void;
  onBuild: () => void;
  onOpenGraph: () => void;
}) {
  const usesRecordSource =
    form.sourceType === "manual_table" || form.sourceType === "structured_records";
  const usesSemanticLift = form.sourceType === "tep_semantic_lift";
  const usesVariableMapping = form.sourceType === "tep_variable_mapping";
  const canBuild = constructionBuildReady(form);
  return (
    <section className="two-column wide-left">
      <Card title="Construction Run">
        <div className="form-grid">
          <label className="form-field">
            <span>Output name</span>
            <Input
              value={form.outputName}
              onChange={(value) => onChange({ outputName: value })}
            />
          </label>
          <label className="form-field">
            <span>Source type</span>
            <Select
              value={form.sourceType}
              onChange={(value) =>
                onChange({
                  sourceType: value as KGConstructionSourceType,
                  sourcePath: "",
                  sourceText:
                    value === "manual_table" || value === "structured_records"
                      ? form.sourceText
                      : ""
                })
              }
              options={[
                { label: "manual table", value: "manual_table" },
                { label: "structured records", value: "structured_records" },
                { label: "TEP semantic lift", value: "tep_semantic_lift" },
                { label: "TEP variable mapping", value: "tep_variable_mapping" }
              ]}
            />
          </label>
          <label className="form-field">
            <span>Scenario</span>
            <Input value={form.scenario} onChange={(value) => onChange({ scenario: value })} />
          </label>
          <label className="form-field">
            <span>Source ID</span>
            <Input value={form.sourceId} onChange={(value) => onChange({ sourceId: value })} />
          </label>
          <label className="form-field">
            <span>Source format</span>
            <Select
              value={form.sourceFormat}
              disabled={usesSemanticLift || usesVariableMapping}
              onChange={(value) => onChange({ sourceFormat: value as KGConstructionSourceFormat })}
              options={[
                { label: "csv", value: "csv" },
                { label: "jsonl", value: "jsonl" },
                { label: "json", value: "json" }
              ]}
            />
          </label>
          <label className="inline-switch build-overwrite">
            <Switch
              size="small"
              checked={form.overwrite}
              onChange={(value) => onChange({ overwrite: value })}
            />
            <span>overwrite existing output</span>
          </label>
        </div>

        {usesRecordSource && (
          <div className="form-grid single">
            <label className="form-field">
              <span>Source file path</span>
              <Input
                value={form.sourcePath}
                onChange={(value) => onChange({ sourcePath: value })}
                placeholder="optional local csv/json/jsonl path"
              />
            </label>
            <label className="form-field">
              <span>Inline source text</span>
              <Input.TextArea
                value={form.sourceText}
                onChange={(value) => onChange({ sourceText: value })}
                disabled={Boolean(form.sourcePath.trim())}
                autoSize={{ minRows: 5, maxRows: 9 }}
              />
            </label>
          </div>
        )}

        {usesSemanticLift && (
          <div className="form-grid single">
            <label className="form-field">
              <span>Semantic lift directory</span>
              <Input
                value={form.sourcePath}
                onChange={(value) => onChange({ sourcePath: value })}
                placeholder="optional directory with TEP semantic KG artifacts"
              />
            </label>
            <label className="form-field">
              <span>Semantic nodes path</span>
              <Input
                value={form.semanticNodesPath}
                onChange={(value) => onChange({ semanticNodesPath: value })}
                disabled={Boolean(form.sourcePath.trim())}
              />
            </label>
            <label className="form-field">
              <span>Semantic edges path</span>
              <Input
                value={form.semanticEdgesPath}
                onChange={(value) => onChange({ semanticEdgesPath: value })}
                disabled={Boolean(form.sourcePath.trim())}
              />
            </label>
          </div>
        )}

        {usesVariableMapping && (
          <div className="form-grid single">
            <label className="form-field">
              <span>Variable mapping path</span>
              <Input value={form.sourcePath} onChange={(value) => onChange({ sourcePath: value })} />
            </label>
          </div>
        )}

        <Space wrap>
          <Button type="primary" disabled={!canBuild} onClick={onBuild}>
            Build candidate KG
          </Button>
          <Button onClick={onOpenGraph}>Open graph</Button>
        </Space>
        {!canBuild && (
          <Alert
            type="warning"
            title="Complete the required source fields before running construction."
          />
        )}
        {status && <Alert type="success" title={status} />}
      </Card>

      <Card title="Build Output">
        {!result ? (
          <div className="compact-list">
            <div>
              <strong>current candidate layer</strong>
              <span>{payload.candidate_dir ? shortId(payload.candidate_dir, 72) : "none discovered"}</span>
            </div>
            <div>
              <strong>claim boundary</strong>
              <span>{payload.claim_boundary}</span>
            </div>
          </div>
        ) : (
          <div className="page-stack">
            <section className="metric-grid build-metrics">
              <MetricCard label="status" value={result.status} hint={shortId(result.run_id, 20)} />
              <MetricCard
                label="nodes"
                value={summaryMetric(result.summary, "node_count")}
                hint="candidate"
              />
              <MetricCard
                label="edges"
                value={summaryMetric(result.summary, "edge_count")}
                hint="candidate"
              />
              <MetricCard
                label="sources"
                value={summaryMetric(result.summary, "source_count")}
                hint="input"
              />
            </section>
            <div className="compact-list">
              {constructionArtifacts(result).map((item) => (
                <div key={item.label}>
                  <strong>{item.label}</strong>
                  <span>{item.value}</span>
                </div>
              ))}
            </div>
            <JsonBlock value={result.summary} />
            <Alert type="info" title={result.claim_boundary} />
          </div>
        )}
      </Card>
    </section>
  );
}

function constructionBuildReady(form: KGConstructionBuildForm): boolean {
  if (!form.outputName.trim() || !form.sourceId.trim() || !form.scenario.trim()) return false;
  if (form.sourceType === "manual_table" || form.sourceType === "structured_records") {
    return Boolean(form.sourcePath.trim() || form.sourceText.trim());
  }
  if (form.sourceType === "tep_semantic_lift") {
    return Boolean(
      form.sourcePath.trim() ||
        (form.semanticNodesPath.trim() && form.semanticEdgesPath.trim())
    );
  }
  return Boolean(form.sourcePath.trim());
}

function constructionArtifacts(result: KGConstructionBuildResponse) {
  return [
    { label: "output", value: result.output_dir },
    { label: "nodes", value: result.nodes_path },
    { label: "edges", value: result.edges_path },
    { label: "summary", value: result.summary_path },
    { label: "manifest", value: result.manifest_path }
  ];
}

function summaryMetric(summary: Record<string, unknown>, key: string): string {
  const direct = summary[key];
  if (direct !== undefined) return valueText(direct);
  const output = summary.output;
  if (typeof output === "object" && output !== null && key in output) {
    return valueText((output as Record<string, unknown>)[key]);
  }
  const counts = summary.counts;
  if (typeof counts === "object" && counts !== null && key in counts) {
    return valueText((counts as Record<string, unknown>)[key]);
  }
  return "unknown";
}

function KGGraphBrowser({
  payload,
  edges,
  filters,
  options,
  selectedEdge,
  selectedTargetKey,
  showLabels,
  onFiltersChanged,
  onShowLabelsChanged,
  onTargetSelected
}: {
  payload: KGStudioPayload;
  edges: KGStudioGraphEdge[];
  filters: KGFilters;
  options: { scenarios: string[]; sources: string[]; reviewStatuses: string[] };
  selectedEdge: KGStudioGraphEdge | undefined;
  selectedTargetKey: string;
  showLabels: boolean;
  onFiltersChanged: (patch: Partial<KGFilters>) => void;
  onShowLabelsChanged: (checked: boolean) => void;
  onTargetSelected: (targetKey: string) => void;
}) {
  const graph = useMemo(() => graphFromKGStudio(payload.graph_nodes, edges.slice(0, 160)), [edges, payload.graph_nodes]);
  return (
    <div className="page-stack">
      <section className="graph-workspace-panel">
        <div className="graph-toolbar">
          <div className="graph-toolbar-title">
            <strong>Candidate edge graph</strong>
            <span>{edges.length} filtered edges · rendering first {graph.edges.length}</span>
          </div>
          <KGGraphToolbar
            filters={filters}
            options={options}
            showLabels={showLabels}
            onFiltersChanged={onFiltersChanged}
            onShowLabelsChanged={onShowLabelsChanged}
          />
        </div>
        <div className="graph-panel graph-panel-primary">
          <KnowledgeGraph
            nodes={graph.nodes}
            edges={graph.edges}
            selectedTargetKey={selectedTargetKey}
            showLabels={showLabels}
            height={680}
            onSelectEdge={(edge) => edge.targetKey && onTargetSelected(edge.targetKey)}
          />
        </div>
      </section>
      <section className="two-column wide-left auxiliary-grid">
        <KGEdgeTable edges={edges} selectedTargetKey={selectedTargetKey} onTargetSelected={onTargetSelected} />
        <KGEdgeInspector edge={selectedEdge} />
      </section>
    </div>
  );
}

function KGGraphStatusStrip({ note, totalEdges }: { note: string; totalEdges: number }) {
  return (
    <section className="kg-status-strip" aria-label="KG graph status">
      <Tag color="orangered">source constrained</Tag>
      <Tag color="arcoblue">{totalEdges} candidate edges</Tag>
      <span>{note}</span>
    </section>
  );
}

function KGGraphToolbar({
  filters,
  options,
  showLabels,
  onFiltersChanged,
  onShowLabelsChanged
}: {
  filters: KGFilters;
  options: { scenarios: string[]; sources: string[]; reviewStatuses: string[] };
  showLabels: boolean;
  onFiltersChanged: (patch: Partial<KGFilters>) => void;
  onShowLabelsChanged: (checked: boolean) => void;
}) {
  return (
    <div className="kg-graph-toolbar-controls">
      <Input.Search
        allowClear
        value={filters.query}
        onChange={(value) => onFiltersChanged({ query: value })}
        placeholder="Search graph"
      />
      <Select
        value={filters.scenario}
        onChange={(value) => onFiltersChanged({ scenario: String(value) })}
        options={[{ label: "All scenarios", value: "all" }, ...options.scenarios.map((item) => ({ label: item, value: item }))]}
      />
      <Select
        value={filters.source}
        onChange={(value) => onFiltersChanged({ source: String(value) })}
        options={[{ label: "All sources", value: "all" }, ...options.sources.map((item) => ({ label: item, value: item }))]}
      />
      <Select
        value={filters.reviewStatus}
        onChange={(value) => onFiltersChanged({ reviewStatus: String(value) })}
        options={[{ label: "All review states", value: "all" }, ...options.reviewStatuses.map((item) => ({ label: item, value: item }))]}
      />
      <label className="inline-switch">
        <Switch size="small" checked={showLabels} onChange={onShowLabelsChanged} />
        <span>labels</span>
      </label>
    </div>
  );
}

function KGReview({
  edges,
  targets,
  selectedEdge,
  selectedTarget,
  selectedTargetKey,
  reviewNote,
  reviewStatus,
  onTargetSelected,
  onReviewNoteChanged,
  onSubmitReview
}: {
  edges: KGStudioGraphEdge[];
  targets: KGStudioReviewTarget[];
  selectedEdge: KGStudioGraphEdge | undefined;
  selectedTarget: KGStudioReviewTarget | undefined;
  selectedTargetKey: string;
  reviewNote: string;
  reviewStatus: string | null;
  onTargetSelected: (targetKey: string) => void;
  onReviewNoteChanged: (note: string) => void;
  onSubmitReview: (action: ReviewAction) => void;
}) {
  return (
    <section className="two-column">
      <Card title="Review Queue">
        <div className="review-queue">
          {targets.map((target) => (
            <button
              key={target.target_key}
              className={target.target_key === selectedTargetKey ? "selected" : ""}
              onClick={() => onTargetSelected(target.target_key)}
            >
              <strong>{shortId(target.label, 54)}</strong>
              <span>{target.review_status} · {valueText(target.confidence)}</span>
            </button>
          ))}
        </div>
        {!targets.length && <Empty description={`No review targets in ${edges.length} filtered edges.`} />}
      </Card>
      <Card title="Decision Panel">
        <KGEdgeInspectorContent edge={selectedEdge} />
        <Select
          value={selectedTargetKey}
          onChange={(value) => onTargetSelected(String(value))}
          options={targets.map((target) => ({
            label: shortId(target.label, 56),
            value: target.target_key
          }))}
        />
        <Input.TextArea
          value={reviewNote}
          onChange={onReviewNoteChanged}
          placeholder="optional KG edge review note"
          disabled={!selectedTarget}
        />
        <Space wrap>
          <Button disabled={!selectedTarget} onClick={() => onSubmitReview("accept")}>
            Accept
          </Button>
          <Button disabled={!selectedTarget} onClick={() => onSubmitReview("reject")}>
            Reject
          </Button>
          <Button disabled={!selectedTarget} onClick={() => onSubmitReview("needs_review")}>
            Needs review
          </Button>
        </Space>
        {reviewStatus && <Alert type="success" title={`KG feedback ${reviewStatus}.`} />}
      </Card>
    </section>
  );
}

function KGDrafts({
  targets,
  selectedEdge,
  selectedTargetKey,
  draftAction,
  draftRelation,
  draftEvidence,
  draftConfidence,
  draftStatus,
  onTargetSelected,
  onDraftChanged,
  onSubmitDraft
}: {
  targets: KGStudioReviewTarget[];
  selectedEdge: KGStudioGraphEdge | undefined;
  selectedTargetKey: string;
  draftAction: KGDraftAction;
  draftRelation: string;
  draftEvidence: string;
  draftConfidence: string;
  draftStatus: string | null;
  onTargetSelected: (targetKey: string) => void;
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
    <section className="two-column">
      <Card title="Draft Target">
        <Select
          value={selectedTargetKey}
          onChange={(value) => onTargetSelected(String(value))}
          options={targets.map((target) => ({
            label: shortId(target.label, 56),
            value: target.target_key
          }))}
        />
        <KGEdgeInspectorContent edge={selectedEdge} />
      </Card>
      <Card title="Draft Adjustment">
        <div className="form-grid single">
          <label className="form-field">
            <span>Action</span>
            <Select
              value={draftAction}
              onChange={(value) => onDraftChanged({ kgDraftAction: value as KGDraftAction })}
              options={[
                { label: "keep", value: "keep" },
                { label: "revise", value: "revise" },
                { label: "reject", value: "reject" },
                { label: "promote later", value: "promote_later" }
              ]}
            />
          </label>
          <label className="form-field">
            <span>Proposed relation</span>
            <Input value={draftRelation} onChange={(value) => onDraftChanged({ kgDraftRelation: value })} />
          </label>
          <label className="form-field">
            <span>Proposed confidence</span>
            <InputNumber
              min={0}
              max={1}
              step={0.05}
              value={draftConfidence ? Number(draftConfidence) : undefined}
              onChange={(value) => onDraftChanged({ kgDraftConfidence: value === undefined ? "" : String(value) })}
            />
          </label>
          <label className="form-field">
            <span>Evidence note</span>
            <Input.TextArea
              value={draftEvidence}
              onChange={(value) => onDraftChanged({ kgDraftEvidence: value })}
              autoSize={{ minRows: 4, maxRows: 8 }}
            />
          </label>
        </div>
        <Button type="primary" disabled={!selectedEdge} onClick={onSubmitDraft}>
          Record draft
        </Button>
        {draftStatus && <Alert type="success" title={`Draft ${draftStatus}.`} />}
      </Card>
    </section>
  );
}

function KGFilterBar({
  filters,
  options,
  onChange
}: {
  filters: KGFilters;
  options: { scenarios: string[]; sources: string[]; reviewStatuses: string[] };
  onChange: (patch: Partial<KGFilters>) => void;
}) {
  return (
    <section className="toolbar-panel">
      <Input.Search
        allowClear
        value={filters.query}
        onChange={(value) => onChange({ query: value })}
        placeholder="Search entity, relation, evidence"
      />
      <Select
        value={filters.scenario}
        onChange={(value) => onChange({ scenario: String(value) })}
        options={[{ label: "All scenarios", value: "all" }, ...options.scenarios.map((item) => ({ label: item, value: item }))]}
      />
      <Select
        value={filters.source}
        onChange={(value) => onChange({ source: String(value) })}
        options={[{ label: "All sources", value: "all" }, ...options.sources.map((item) => ({ label: item, value: item }))]}
      />
      <Select
        value={filters.reviewStatus}
        onChange={(value) => onChange({ reviewStatus: String(value) })}
        options={[{ label: "All review states", value: "all" }, ...options.reviewStatuses.map((item) => ({ label: item, value: item }))]}
      />
    </section>
  );
}

function KGEdgeTable({
  edges,
  selectedTargetKey,
  onTargetSelected
}: {
  edges: KGStudioGraphEdge[];
  selectedTargetKey: string;
  onTargetSelected: (targetKey: string) => void;
}) {
  const columns: TableColumnProps<KGStudioGraphEdge>[] = [
    {
      title: "Edge",
      dataIndex: "edge_id",
      render: (_, row) => (
        <Button type="text" onClick={() => onTargetSelected(row.target_key)}>
          {shortId(row.head, 22)} → {shortId(row.tail, 22)}
        </Button>
      )
    },
    { title: "Relation", dataIndex: "relation" },
    { title: "Scenario", dataIndex: "scenario" },
    { title: "Source", dataIndex: "source", render: (value) => shortId(String(value), 30) },
    { title: "Confidence", dataIndex: "confidence", render: valueText },
    {
      title: "Review",
      dataIndex: "review_status",
      render: (value) => <Tag color={value === "reviewed" ? "green" : "gray"}>{value}</Tag>
    }
  ];
  return (
    <Card title="Edge Browser">
      <Table
        rowKey="target_key"
        columns={columns}
        data={edges}
        pagination={{ pageSize: 8 }}
        rowClassName={(record) => (record.target_key === selectedTargetKey ? "selected-table-row" : "")}
      />
    </Card>
  );
}

function KGEdgeInspector({ edge }: { edge: KGStudioGraphEdge | undefined }) {
  return (
    <Card title="Selected Edge Provenance">
      <KGEdgeInspectorContent edge={edge} />
    </Card>
  );
}

function KGEdgeInspectorContent({ edge }: { edge: KGStudioGraphEdge | undefined }) {
  if (!edge) return <Empty description="Select an edge to inspect provenance." />;
  return (
    <div className="provenance-list">
      <span>head</span><strong>{edge.head}</strong>
      <span>relation</span><strong>{edge.relation}</strong>
      <span>tail</span><strong>{edge.tail}</strong>
      <span>scenario</span><strong>{edge.scenario}</strong>
      <span>source</span><strong>{edge.source}</strong>
      <span>confidence</span><strong>{valueText(edge.confidence)}</strong>
      <span>review</span><strong>{edge.review_status}</strong>
      <span>evidence</span><p>{edge.evidence}</p>
    </div>
  );
}

function edgeFilterOptions(edges: KGStudioGraphEdge[]) {
  return {
    scenarios: Array.from(new Set(edges.map((edge) => edge.scenario))).sort(),
    sources: Array.from(new Set(edges.map((edge) => edge.source))).sort(),
    reviewStatuses: Array.from(new Set(edges.map((edge) => edge.review_status))).sort()
  };
}

function filterGraphEdges(edges: KGStudioGraphEdge[], filters: KGFilters): KGStudioGraphEdge[] {
  const query = filters.query.trim().toLowerCase();
  return edges.filter((edge) => {
    const scenarioMatch = filters.scenario === "all" || edge.scenario === filters.scenario;
    const sourceMatch = filters.source === "all" || edge.source === filters.source;
    const statusMatch =
      filters.reviewStatus === "all" || edge.review_status === filters.reviewStatus;
    const haystack = [edge.head, edge.tail, edge.relation, edge.evidence, edge.source]
      .join(" ")
      .toLowerCase();
    return scenarioMatch && sourceMatch && statusMatch && (!query || haystack.includes(query));
  });
}

function reviewTargetsForEdges(targets: KGStudioReviewTarget[], edges: KGStudioGraphEdge[]) {
  const allowed = new Set(edges.map((edge) => edge.target_key));
  return targets.filter((target) => allowed.has(target.target_key));
}
