import {
  Alert,
  Button,
  Card,
  Descriptions,
  Empty,
  Input,
  Menu,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Typography
} from "antd";
import type { MenuProps, TableColumnsType } from "antd";
import {
  BranchesOutlined,
  CheckOutlined,
  CloseOutlined,
  DatabaseOutlined,
  EditOutlined,
  FileSearchOutlined,
  ReloadOutlined
} from "@ant-design/icons";
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  type SimulationLinkDatum,
  type SimulationNodeDatum
} from "d3-force";
import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { shortId, valueText } from "./format";
import type {
  KGDraftAction,
  KGSourceDraftEdge,
  KGSourceDraftResponse,
  KGStudioGraphEdge,
  KGStudioGraphNode,
  KGStudioPayload,
  KGStudioReviewTarget,
  KGStudioSource,
  KGStudioSourceDocument,
  ReviewAction
} from "./types";

const { Text, Title, Paragraph } = Typography;

type KGStudioViewKey = "overview" | "sources" | "graph" | "review" | "drafts";

interface KGStudioFilters {
  query: string;
  scenario: string;
  source: string;
  reviewStatus: string;
}

const EMPTY_FILTERS: KGStudioFilters = {
  query: "",
  scenario: "all",
  source: "all",
  reviewStatus: "all"
};

const KG_STUDIO_VIEWS: Array<{
  key: KGStudioViewKey;
  path: string;
  label: string;
  description: string;
  icon: ReactNode;
}> = [
  {
    key: "overview",
    path: "/kg-studio/overview",
    label: "Overview",
    description: "Status and coverage",
    icon: <DatabaseOutlined />
  },
  {
    key: "sources",
    path: "/kg-studio/sources",
    label: "Sources",
    description: "Registry and extraction",
    icon: <FileSearchOutlined />
  },
  {
    key: "graph",
    path: "/kg-studio/graph",
    label: "Graph",
    description: "Candidate topology",
    icon: <BranchesOutlined />
  },
  {
    key: "review",
    path: "/kg-studio/review",
    label: "Review",
    description: "Edge decisions",
    icon: <CheckOutlined />
  },
  {
    key: "drafts",
    path: "/kg-studio/drafts",
    label: "Draft Lab",
    description: "Adjustments",
    icon: <EditOutlined />
  }
];

export function KGStudioWorkspace({
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
  const location = useLocation();
  const navigate = useNavigate();
  const [filters, setFilters] = useState<KGStudioFilters>(EMPTY_FILTERS);
  const [sourceQuery, setSourceQuery] = useState("");
  const activeView = kgStudioViewForPath(location.pathname);
  const filteredEdges = useMemo(
    () => filterGraphEdges(payload?.graph_edges ?? [], filters),
    [payload?.graph_edges, filters]
  );
  const filteredTargets = useMemo(
    () => reviewTargetsForEdges(payload?.review_targets ?? [], filteredEdges),
    [payload?.review_targets, filteredEdges]
  );
  const filterOptions = useMemo(
    () => edgeFilterOptions(payload?.graph_edges ?? []),
    [payload?.graph_edges]
  );
  const usesEdgeFilters = ["graph", "review", "drafts"].includes(activeView);
  const activeEdges = usesEdgeFilters ? filteredEdges : (payload?.graph_edges ?? []);
  const activeTargets = usesEdgeFilters ? filteredTargets : (payload?.review_targets ?? []);
  const selectedEdge = activeEdges.find((edge) => edge.target_key === selectedTargetKey);
  const activeSelectedTarget = activeTargets.find(
    (target) => target.target_key === selectedTargetKey
  );

  useEffect(() => {
    if (!usesEdgeFilters || !filteredEdges.length) return;
    if (filteredEdges.some((edge) => edge.target_key === selectedTargetKey)) return;
    onTargetSelected(filteredEdges[0].target_key);
  }, [filteredEdges, onTargetSelected, selectedTargetKey, usesEdgeFilters]);

  if (location.pathname === "/kg-studio" || location.pathname === "/kg-studio/") {
    return <Navigate to="/kg-studio/overview" replace />;
  }

  const menuItems: MenuProps["items"] = KG_STUDIO_VIEWS.map((view) => ({
    key: view.key,
    icon: view.icon,
    label: (
      <div className="menu-label">
        <span>{view.label}</span>
        <small>{view.description}</small>
      </div>
    )
  }));

  return (
    <div className="kg-workspace">
      <Card className="kg-workspace-header">
        <div>
          <p className="eyebrow">KG Studio</p>
          <Title level={2}>Source-Grounded Graph Management</Title>
          <Paragraph>
            Inspect provenance, generate candidate edges, and record reviewable
            graph changes without mutating the tracked KG.
          </Paragraph>
        </div>
        <Button icon={<ReloadOutlined />} onClick={onRefresh}>
          Refresh KG
        </Button>
      </Card>

      <Menu
        className="kg-studio-subnav"
        disabledOverflow
        mode="horizontal"
        selectedKeys={[activeView]}
        items={menuItems}
        onClick={({ key }) => {
          const view = KG_STUDIO_VIEWS.find((item) => item.key === key);
          if (view) navigate(view.path);
        }}
      />

      {!payload ? (
        <Card>
          <Empty description="Reading source registry and candidate KG artifacts from local project paths." />
        </Card>
      ) : (
        <>
          <Alert className="claim-boundary" title={payload.note} type="warning" showIcon />
          {activeView === "overview" && <KGStudioOverview payload={payload} />}
          {activeView === "sources" && (
            <KGStudioSourcesPage
              payload={payload}
              sourceQuery={sourceQuery}
              sourceDraftText={sourceDraftText}
              sourceDraftSourceId={sourceDraftSourceId}
              sourceDraftScenario={sourceDraftScenario}
              sourceDraftConfidence={sourceDraftConfidence}
              sourceDraftResult={sourceDraftResult}
              onSourceQueryChanged={setSourceQuery}
              onSourceDraftChanged={onSourceDraftChanged}
              onGenerateSourceDraft={onGenerateSourceDraft}
            />
          )}
          {activeView === "graph" && (
            <>
              <KGStudioFilterBar
                filters={filters}
                options={filterOptions}
                resultCount={filteredEdges.length}
                onChanged={(patch) => setFilters((current) => ({ ...current, ...patch }))}
                onReset={() => setFilters(EMPTY_FILTERS)}
              />
              <KGStudioGraphPage
                payload={payload}
                edges={filteredEdges}
                selectedEdge={selectedEdge}
                selectedTargetKey={selectedTargetKey}
                onTargetSelected={onTargetSelected}
              />
            </>
          )}
          {activeView === "review" && (
            <>
              <KGStudioFilterBar
                filters={filters}
                options={filterOptions}
                resultCount={filteredEdges.length}
                onChanged={(patch) => setFilters((current) => ({ ...current, ...patch }))}
                onReset={() => setFilters(EMPTY_FILTERS)}
              />
              <KGStudioReviewPage
                selectedEdge={selectedEdge}
                selectedTarget={activeSelectedTarget}
                selectedTargetKey={selectedTargetKey}
                reviewNote={reviewNote}
                reviewStatus={reviewStatus}
                targets={filteredTargets}
                onTargetSelected={onTargetSelected}
                onReviewNoteChanged={onReviewNoteChanged}
                onSubmitReview={onSubmitReview}
              />
            </>
          )}
          {activeView === "drafts" && (
            <>
              <KGStudioFilterBar
                filters={filters}
                options={filterOptions}
                resultCount={filteredEdges.length}
                onChanged={(patch) => setFilters((current) => ({ ...current, ...patch }))}
                onReset={() => setFilters(EMPTY_FILTERS)}
              />
              <KGStudioDraftsPage
                selectedEdge={selectedEdge}
                selectedTarget={activeSelectedTarget}
                selectedTargetKey={selectedTargetKey}
                draftAction={draftAction}
                draftRelation={draftRelation}
                draftEvidence={draftEvidence}
                draftConfidence={draftConfidence}
                draftStatus={draftStatus}
                targets={filteredTargets}
                onTargetSelected={onTargetSelected}
                onDraftChanged={onDraftChanged}
                onSubmitDraft={onSubmitDraft}
              />
            </>
          )}
        </>
      )}
    </div>
  );
}

function kgStudioViewForPath(pathname: string): KGStudioViewKey {
  const match = KG_STUDIO_VIEWS.find((view) => pathname.startsWith(view.path));
  return match?.key ?? "overview";
}

function KGStudioFilterBar({
  filters,
  options,
  resultCount,
  onChanged,
  onReset
}: {
  filters: KGStudioFilters;
  options: {
    scenarios: string[];
    sources: string[];
    reviewStatuses: string[];
  };
  resultCount: number;
  onChanged: (patch: Partial<KGStudioFilters>) => void;
  onReset: () => void;
}) {
  return (
    <Card className="kg-filter-card">
      <div className="kg-filter-bar">
        <Input.Search
          allowClear
          value={filters.query}
          onChange={(event) => onChanged({ query: event.target.value })}
          placeholder="Search edge, source, or evidence"
        />
        <Select
          value={filters.scenario}
          onChange={(value) => onChanged({ scenario: value })}
          options={selectOptions(options.scenarios, "All scenarios")}
        />
        <Select
          value={filters.source}
          onChange={(value) => onChanged({ source: value })}
          options={selectOptions(options.sources, "All sources")}
        />
        <Select
          value={filters.reviewStatus}
          onChange={(value) => onChanged({ reviewStatus: value })}
          options={selectOptions(options.reviewStatuses, "All review states")}
        />
        <Tag color="blue">{resultCount} edges</Tag>
        <Button onClick={onReset}>Reset</Button>
      </div>
    </Card>
  );
}

function KGStudioOverview({ payload }: { payload: KGStudioPayload }) {
  const statusRows = countRows(payload.review_status_counts);
  const scenarioRows = countRows(payload.scenario_counts);
  const sourceRows = countRows(payload.source_counts);
  return (
    <div className="kg-workspace-stack">
      <section className="kg-metrics">
        <Metric label="status" value={payload.status} />
        <Metric label="nodes" value={payload.node_count} />
        <Metric label="edges" value={payload.edge_count} />
        <Metric label="validation" value={payload.validation_summary?.passed ?? "unknown"} />
        <Metric label="mean confidence" value={payload.confidence_summary.mean ?? "unknown"} />
      </section>

      <section className="kg-overview-grid">
        <Card title="Review Status">
          <CountList rows={statusRows} emptyText="No review status counts available." />
        </Card>
        <Card title="Scenario Coverage">
          <CountList rows={scenarioRows} emptyText="No scenario counts available." />
        </Card>
        <Card title="Source Coverage">
          <CountList rows={sourceRows} emptyText="No source counts available." />
        </Card>
      </section>

      <Card title="Artifact Contracts">
        <Descriptions className="kg-edge-inspector" size="small" column={1} bordered>
          <Descriptions.Item label="candidate dir">
            <span className="breakable-value">{valueText(payload.candidate_dir)}</span>
          </Descriptions.Item>
          <Descriptions.Item label="nodes path">
            <span className="breakable-value">{valueText(payload.nodes_path)}</span>
          </Descriptions.Item>
          <Descriptions.Item label="edges path">
            <span className="breakable-value">{valueText(payload.edges_path)}</span>
          </Descriptions.Item>
          <Descriptions.Item label="source registry">
            <span className="breakable-value">{payload.source_registry_path}</span>
          </Descriptions.Item>
        </Descriptions>
      </Card>
    </div>
  );
}

function KGStudioSourcesPage({
  payload,
  sourceQuery,
  sourceDraftText,
  sourceDraftSourceId,
  sourceDraftScenario,
  sourceDraftConfidence,
  sourceDraftResult,
  onSourceQueryChanged,
  onSourceDraftChanged,
  onGenerateSourceDraft
}: {
  payload: KGStudioPayload;
  sourceQuery: string;
  sourceDraftText: string;
  sourceDraftSourceId: string;
  sourceDraftScenario: string;
  sourceDraftConfidence: string;
  sourceDraftResult: KGSourceDraftResponse | null;
  onSourceQueryChanged: (query: string) => void;
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
  const filteredSources = filterSources(payload.sources, sourceQuery);
  const filteredDocuments = filterSourceDocuments(payload.source_documents, sourceQuery);
  return (
    <div className="kg-workspace-stack">
      <Card title="Source-to-KG Draft Generator">
        <SourceToKGDraftForm
          sourceText={sourceDraftText}
          sourceId={sourceDraftSourceId}
          scenario={sourceDraftScenario}
          confidence={sourceDraftConfidence}
          result={sourceDraftResult}
          onChanged={onSourceDraftChanged}
          onGenerate={onGenerateSourceDraft}
        />
      </Card>
      <Card className="kg-filter-card">
        <Input.Search
          allowClear
          value={sourceQuery}
          onChange={(event) => onSourceQueryChanged(event.target.value)}
          placeholder="Search source registry and documents"
        />
      </Card>
      <section className="kg-two-column">
        <Card title="Source Registry">
          <KGSourceList sources={filteredSources} />
        </Card>
        <Card title="Source Documents">
          <KGSourceDocumentList documents={filteredDocuments} />
        </Card>
      </section>
    </div>
  );
}

function KGStudioGraphPage({
  payload,
  edges,
  selectedEdge,
  selectedTargetKey,
  onTargetSelected
}: {
  payload: KGStudioPayload;
  edges: KGStudioGraphEdge[];
  selectedEdge: KGStudioGraphEdge | undefined;
  selectedTargetKey: string;
  onTargetSelected: (targetKey: string) => void;
}) {
  return (
    <div className="kg-workspace-stack">
      <Card title="Candidate Edge Graph">
        <KGForceGraph
          nodes={payload.graph_nodes}
          edges={edges}
          selectedTargetKey={selectedTargetKey}
          onTargetSelected={onTargetSelected}
        />
      </Card>
      <section className="kg-two-column graph-browser-layout">
        <Card title="Edge Browser">
          <KGEdgeTable
            edges={edges}
            selectedTargetKey={selectedTargetKey}
            onTargetSelected={onTargetSelected}
          />
        </Card>
        <Card title="Selected Edge Provenance">
          <KGEdgeInspector edge={selectedEdge} />
        </Card>
      </section>
    </div>
  );
}

function KGStudioReviewPage({
  selectedEdge,
  selectedTarget,
  selectedTargetKey,
  reviewNote,
  reviewStatus,
  targets,
  onTargetSelected,
  onReviewNoteChanged,
  onSubmitReview
}: {
  selectedEdge: KGStudioGraphEdge | undefined;
  selectedTarget: KGStudioReviewTarget | undefined;
  selectedTargetKey: string;
  reviewNote: string;
  reviewStatus: string | null;
  targets: KGStudioReviewTarget[];
  onTargetSelected: (targetKey: string) => void;
  onReviewNoteChanged: (note: string) => void;
  onSubmitReview: (action: ReviewAction) => void;
}) {
  return (
    <section className="kg-two-column review-layout">
      <Card title="Review Queue">
        <KGReviewQueue
          targets={targets}
          selectedTargetKey={selectedTargetKey}
          onTargetSelected={onTargetSelected}
        />
      </Card>
      <Card title="Decision Panel">
        <KGEdgeInspector edge={selectedEdge} />
        <KGReviewBox
          targets={targets}
          selectedTarget={selectedTarget}
          selectedTargetKey={selectedTargetKey}
          reviewNote={reviewNote}
          reviewStatus={reviewStatus}
          onTargetSelected={onTargetSelected}
          onReviewNoteChanged={onReviewNoteChanged}
          onSubmitReview={onSubmitReview}
        />
      </Card>
    </section>
  );
}

function KGStudioDraftsPage({
  selectedEdge,
  selectedTarget,
  selectedTargetKey,
  draftAction,
  draftRelation,
  draftEvidence,
  draftConfidence,
  draftStatus,
  targets,
  onTargetSelected,
  onDraftChanged,
  onSubmitDraft
}: {
  selectedEdge: KGStudioGraphEdge | undefined;
  selectedTarget: KGStudioReviewTarget | undefined;
  selectedTargetKey: string;
  draftAction: KGDraftAction;
  draftRelation: string;
  draftEvidence: string;
  draftConfidence: string;
  draftStatus: string | null;
  targets: KGStudioReviewTarget[];
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
    <section className="kg-two-column draft-layout">
      <Card title="Draft Target">
        <EdgeSelectionControl
          targets={targets}
          selectedTargetKey={selectedTargetKey}
          onTargetSelected={onTargetSelected}
        />
        <KGEdgeInspector edge={selectedEdge} />
      </Card>
      <Card title="Draft Adjustment">
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
      </Card>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: unknown }) {
  return (
    <Card size="small">
      <Statistic title={label} value={valueText(value)} />
    </Card>
  );
}

function countRows(counts: Record<string, number>): Array<{ label: string; value: number }> {
  return Object.entries(counts)
    .sort((left, right) => right[1] - left[1])
    .map(([label, value]) => ({ label, value }));
}

function selectOptions(values: string[], allLabel: string): Array<{ value: string; label: string }> {
  return [
    { value: "all", label: allLabel },
    ...values.map((value) => ({ value, label: value || "unknown" }))
  ];
}

function edgeFilterOptions(edges: KGStudioGraphEdge[]): {
  scenarios: string[];
  sources: string[];
  reviewStatuses: string[];
} {
  return {
    scenarios: uniqueSorted(edges.map((edge) => edge.scenario)),
    sources: uniqueSorted(edges.map((edge) => edge.source)),
    reviewStatuses: uniqueSorted(edges.map((edge) => edge.review_status))
  };
}

function filterGraphEdges(
  edges: KGStudioGraphEdge[],
  filters: KGStudioFilters
): KGStudioGraphEdge[] {
  const query = filters.query.trim().toLowerCase();
  return edges.filter((edge) => {
    if (filters.scenario !== "all" && edge.scenario !== filters.scenario) return false;
    if (filters.source !== "all" && edge.source !== filters.source) return false;
    if (filters.reviewStatus !== "all" && edge.review_status !== filters.reviewStatus) {
      return false;
    }
    if (!query) return true;
    return [
      edge.edge_id,
      edge.head,
      edge.relation,
      edge.tail,
      edge.scenario,
      edge.source,
      edge.evidence,
      edge.review_status
    ]
      .join(" ")
      .toLowerCase()
      .includes(query);
  });
}

function reviewTargetsForEdges(
  targets: KGStudioReviewTarget[],
  edges: KGStudioGraphEdge[]
): KGStudioReviewTarget[] {
  const allowed = new Set(edges.map((edge) => edge.target_key));
  return targets.filter((target) => allowed.has(target.target_key));
}

function filterSources(sources: KGStudioSource[], query: string): KGStudioSource[] {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return sources;
  return sources.filter((source) =>
    [
      source.source_id,
      source.title,
      source.source_type,
      source.path_or_url,
      source.used_for,
      source.notes
    ]
      .join(" ")
      .toLowerCase()
      .includes(normalized)
  );
}

function filterSourceDocuments(
  documents: KGStudioSourceDocument[],
  query: string
): KGStudioSourceDocument[] {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return documents;
  return documents.filter((document) =>
    [document.title, document.path, String(document.line_count)]
      .join(" ")
      .toLowerCase()
      .includes(normalized)
  );
}

function uniqueSorted(values: string[]): string[] {
  return Array.from(new Set(values.filter(Boolean))).sort((left, right) =>
    left.localeCompare(right)
  );
}

function CountList({
  rows,
  emptyText
}: {
  rows: Array<{ label: string; value: number }>;
  emptyText: string;
}) {
  if (!rows.length) return <Empty description={emptyText} />;
  return (
    <div className="kg-count-list" role="list">
      {rows.map((row) => (
        <div className="kg-count-row" key={row.label} role="listitem">
          <span className="breakable-value">{row.label}</span>
          <Tag>{row.value}</Tag>
        </div>
      ))}
    </div>
  );
}

function KGSourceList({ sources }: { sources: KGStudioSource[] }) {
  if (!sources.length) return <Empty description="No source registry rows found." />;
  return (
    <div className="compact-list" role="list">
      {sources.map((source) => (
        <article className="compact-list-item" key={source.source_id} role="listitem">
          <strong className="breakable-value">{source.source_id}</strong>
          <Text>{source.title}</Text>
          <Text type="secondary">{source.used_for}</Text>
          <Text type="secondary" className="breakable-value">
            {source.path_or_url}
          </Text>
        </article>
      ))}
    </div>
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
      <div className="source-draft-fields">
        <Input
          value={sourceId}
          onChange={(event) => onChanged({ sourceDraftSourceId: event.target.value })}
          placeholder="source id"
        />
        <Input
          value={scenario}
          onChange={(event) => onChanged({ sourceDraftScenario: event.target.value })}
          placeholder="scenario"
        />
        <Input
          value={confidence}
          onChange={(event) => onChanged({ sourceDraftConfidence: event.target.value })}
          placeholder="confidence"
        />
      </div>
      <Input.TextArea
        value={sourceText}
        onChange={(event) => onChanged({ sourceDraftText: event.target.value })}
        placeholder="head,relation,tail,scenario,evidence"
        rows={7}
      />
      <Button type="primary" onClick={onGenerate}>
        Generate candidates
      </Button>
      {result && (
        <div className="source-draft-results">
          <Tag color="processing">{result.candidate_edges.length} candidate edge(s)</Tag>
          <Text type="secondary">{result.note}</Text>
          <SourceDraftResultTable result={result} />
        </div>
      )}
    </div>
  );
}

function SourceDraftResultTable({ result }: { result: KGSourceDraftResponse }) {
  const columns: TableColumnsType<KGSourceDraftEdge> = [
    {
      title: "Candidate Edge",
      key: "edge",
      render: (_, edge) => (
        <Space wrap>
          <Text>{edge.head}</Text>
          <Tag color="blue">{edge.relation}</Tag>
          <Text>{edge.tail}</Text>
        </Space>
      )
    },
    { title: "Scenario", dataIndex: "scenario", width: 110 },
    {
      title: "Confidence",
      dataIndex: "confidence",
      width: 120,
      render: (value) => valueText(value)
    },
    {
      title: "Evidence",
      dataIndex: "evidence",
      render: (value) => <span className="breakable-value">{valueText(value)}</span>
    }
  ];
  return (
    <Table
      className="source-draft-table"
      columns={columns}
      dataSource={result.candidate_edges}
      pagination={false}
      rowKey="edge_id"
      scroll={{ x: 760 }}
      size="small"
    />
  );
}

function KGSourceDocumentList({ documents }: { documents: KGStudioSourceDocument[] }) {
  if (!documents.length) return <Empty description="No source documents found." />;
  return (
    <div className="compact-list" role="list">
      {documents.map((document) => (
        <article className="compact-list-item" key={document.path} role="listitem">
          <strong className="breakable-value">{document.title}</strong>
          <Text type="secondary" className="breakable-value">
            {document.path}
          </Text>
          <Text type="secondary">{document.line_count} lines</Text>
        </article>
      ))}
    </div>
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
  const layout = useMemo(
    () => buildForceLayout(nodes, edges, selectedTargetKey),
    [nodes, edges, selectedTargetKey]
  );
  if (!layout.nodes.length || !layout.links.length) {
    return <Empty description="Generate candidate KG artifacts first, then refresh this graph." />;
  }
  const nodeById = new Map(layout.nodes.map((node) => [node.id, node]));
  const selectedEdge = edges.find((edge) => edge.target_key === selectedTargetKey);
  const labeledNodes = new Set(
    selectedEdge ? [selectedEdge.head, selectedEdge.tail] : layout.nodes.slice(0, 8).map((node) => node.id)
  );
  return (
    <svg className="kg-force-graph large" viewBox="0 0 920 430" role="img" aria-label="Candidate KG force graph">
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
            <title>{node.label}</title>
            <circle
              className={`kg-node-dot ${node.nodeType}`}
              r={node.nodeType === "RootCause" ? 16 : 13}
            />
            {labeledNodes.has(node.id) && <text y={-20}>{shortNodeLabel(node.label)}</text>}
          </g>
        ))}
      </g>
    </svg>
  );
}

function buildForceLayout(
  graphNodes: KGStudioGraphNode[],
  graphEdges: KGStudioGraphEdge[],
  selectedTargetKey: string
): { nodes: ForceNode[]; links: ForceLink[] } {
  const edgeSlice = graphEdgesForFocusedView(graphEdges, selectedTargetKey);
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
    .slice(0, 110)
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
        .distance(110)
        .strength(0.42)
    )
    .force("charge", forceManyBody().strength(-240))
    .force("collide", forceCollide<ForceNode>().radius(38))
    .force("center", forceCenter(460, 215))
    .stop()
    .tick(160);
  for (const node of nodes) {
    node.x = Math.min(875, Math.max(45, node.x ?? 460));
    node.y = Math.min(390, Math.max(40, node.y ?? 215));
  }
  return { nodes, links };
}

function graphEdgesForFocusedView(
  graphEdges: KGStudioGraphEdge[],
  selectedTargetKey: string
): KGStudioGraphEdge[] {
  const selected = graphEdges.find((edge) => edge.target_key === selectedTargetKey);
  if (!selected) return graphEdges.slice(0, 42);
  const focusNodes = new Set([selected.head, selected.tail]);
  const focused = graphEdges.filter(
    (edge) =>
      edge.target_key === selectedTargetKey ||
      focusNodes.has(edge.head) ||
      focusNodes.has(edge.tail)
  );
  const sameScenario = graphEdges.filter(
    (edge) => edge.scenario === selected.scenario && !focused.includes(edge)
  );
  return [...focused, ...sameScenario].slice(0, 28);
}

function shortNodeLabel(value: string): string {
  return value.length > 24 ? `${value.slice(0, 21)}...` : value;
}

function forceNode(
  value: string | number | ForceNode | undefined,
  nodes: Map<string, ForceNode>
): ForceNode | undefined {
  if (typeof value === "object" && value !== null) return value;
  if (value === undefined) return undefined;
  return nodes.get(String(value));
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
  const columns: TableColumnsType<KGStudioGraphEdge> = [
    {
      title: "Edge",
      key: "edge",
      render: (_, edge) => (
        <Space wrap>
          <Text>{edge.head}</Text>
          <Tag color="blue">{edge.relation}</Tag>
          <Text>{edge.tail}</Text>
        </Space>
      )
    },
    { title: "Scenario", dataIndex: "scenario", width: 110 },
    { title: "Source", dataIndex: "source", width: 180 },
    {
      title: "Confidence",
      dataIndex: "confidence",
      width: 120,
      render: (value) => valueText(value)
    },
    { title: "Review", dataIndex: "review_status", width: 110 }
  ];
  return (
    <Table
      className="kg-edge-table"
      columns={columns}
      dataSource={edges}
      pagination={{ pageSize: 10, size: "small" }}
      rowKey="target_key"
      rowClassName={(edge) => (edge.target_key === selectedTargetKey ? "selected-table-row" : "")}
      size="small"
      onRow={(edge) => ({
        onClick: () => onTargetSelected(edge.target_key)
      })}
    />
  );
}

function KGReviewQueue({
  targets,
  selectedTargetKey,
  onTargetSelected
}: {
  targets: KGStudioReviewTarget[];
  selectedTargetKey: string;
  onTargetSelected: (targetKey: string) => void;
}) {
  if (!targets.length) return <Empty description="No KG edge review targets are available." />;
  return (
    <div className="kg-review-queue-list" role="list">
      {targets.map((target) => (
        <button
          className={target.target_key === selectedTargetKey ? "selected" : ""}
          key={target.target_key}
          onClick={() => onTargetSelected(target.target_key)}
          type="button"
          role="listitem"
        >
          <strong className="breakable-value">{target.label}</strong>
          <span>
            <Tag>{target.review_status}</Tag>
            <Text type="secondary">{target.source}</Text>
            <Text type="secondary">{valueText(target.confidence)}</Text>
          </span>
        </button>
      ))}
    </div>
  );
}

function EdgeSelectionControl({
  targets,
  selectedTargetKey,
  onTargetSelected
}: {
  targets: KGStudioReviewTarget[];
  selectedTargetKey: string;
  onTargetSelected: (targetKey: string) => void;
}) {
  return (
    <Select
      className="kg-edge-select"
      value={selectedTargetKey}
      onChange={(value) => onTargetSelected(value)}
      disabled={!targets.length}
      options={
        targets.length > 0
          ? targets.slice(0, 120).map((target) => ({
              value: target.target_key,
              label: shortId(target.label)
            }))
          : [{ value: "", label: "No KG edge targets" }]
      }
    />
  );
}

function KGReviewBox({
  targets,
  selectedTarget,
  selectedTargetKey,
  reviewNote,
  reviewStatus,
  onTargetSelected,
  onReviewNoteChanged,
  onSubmitReview
}: {
  targets: KGStudioReviewTarget[];
  selectedTarget: KGStudioReviewTarget | undefined;
  selectedTargetKey: string;
  reviewNote: string;
  reviewStatus: string | null;
  onTargetSelected: (targetKey: string) => void;
  onReviewNoteChanged: (note: string) => void;
  onSubmitReview: (action: ReviewAction) => void;
}) {
  return (
    <div className="kg-review-box">
      <EdgeSelectionControl
        targets={targets}
        selectedTargetKey={selectedTargetKey}
        onTargetSelected={onTargetSelected}
      />
      <Input
        value={reviewNote}
        onChange={(event) => onReviewNoteChanged(event.target.value)}
        placeholder="optional KG edge review note"
        disabled={!selectedTarget}
      />
      <div className="kg-review-actions">
        <Button onClick={() => onSubmitReview("accept")} disabled={!selectedTarget}>
          <CheckOutlined />
          Accept
        </Button>
        <Button onClick={() => onSubmitReview("reject")} disabled={!selectedTarget}>
          <CloseOutlined />
          Reject
        </Button>
        <Button onClick={() => onSubmitReview("needs_review")} disabled={!selectedTarget}>
          Needs review
        </Button>
      </div>
      {reviewStatus && <Alert title={`Feedback ${reviewStatus}.`} type="success" showIcon />}
    </div>
  );
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
      <Select
        value={draftAction}
        onChange={(value) =>
          onDraftChanged({ kgDraftAction: value as KGDraftAction })
        }
        disabled={!selectedTarget}
        options={[
          { value: "revise", label: "revise" },
          { value: "keep", label: "keep" },
          { value: "reject", label: "reject" },
          { value: "promote_later", label: "promote later" }
        ]}
      />
      <Input
        value={draftRelation}
        onChange={(event) => onDraftChanged({ kgDraftRelation: event.target.value })}
        placeholder="proposed relation"
        disabled={!selectedTarget}
      />
      <Input
        value={draftConfidence}
        onChange={(event) => onDraftChanged({ kgDraftConfidence: event.target.value })}
        placeholder="proposed confidence 0-1"
        disabled={!selectedTarget}
      />
      <Input.TextArea
        value={draftEvidence}
        onChange={(event) => onDraftChanged({ kgDraftEvidence: event.target.value })}
        placeholder="proposed evidence or adjustment rationale"
        disabled={!selectedTarget}
        rows={8}
      />
      <Button type="primary" onClick={onSubmitDraft} disabled={!selectedTarget}>
        Save draft
      </Button>
      {draftStatus && <Alert title={`Draft ${draftStatus}.`} type="success" showIcon />}
    </div>
  );
}

function KGEdgeInspector({ edge }: { edge: KGStudioGraphEdge | undefined }) {
  if (!edge) {
    return <Empty description="Select a candidate KG edge to inspect provenance." />;
  }
  return (
    <Descriptions className="kg-edge-inspector" size="small" column={1} bordered>
      <Descriptions.Item label="edge">
        <span className="breakable-value">{edge.edge_id}</span>
      </Descriptions.Item>
      <Descriptions.Item label="scenario">{edge.scenario}</Descriptions.Item>
      <Descriptions.Item label="source">
        <span className="breakable-value">{edge.source}</span>
      </Descriptions.Item>
      <Descriptions.Item label="confidence">{valueText(edge.confidence)}</Descriptions.Item>
      <Descriptions.Item label="review status">{edge.review_status}</Descriptions.Item>
      <Descriptions.Item label="evidence">
        <span className="breakable-value">{edge.evidence}</span>
      </Descriptions.Item>
    </Descriptions>
  );
}
