import {
  BarChart3,
  Database
} from "lucide-react";
import {
  Alert,
  Button,
  Card,
  ConfigProvider,
  Descriptions,
  Empty,
  Form,
  Input,
  InputNumber,
  Layout,
  List,
  Menu,
  Select,
  Space,
  Steps,
  Statistic,
  Table,
  Tag,
  Typography,
  Upload
} from "antd";
import type { MenuProps, TableColumnsType } from "antd";
import {
  ApiOutlined,
  BranchesOutlined,
  CheckOutlined,
  CloudUploadOutlined,
  DatabaseOutlined,
  HistoryOutlined,
  HomeOutlined,
  InfoCircleOutlined,
  CloseOutlined,
  ReloadOutlined,
  SendOutlined
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
import { useEffect, useMemo, useReducer, useState } from "react";
import type { ReactNode } from "react";
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams
} from "react-router-dom";

import { api } from "./api";
import { initialState, reducer } from "./state";
import type { AppState } from "./state";
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
  RunSummary,
  PathGraph,
  PathGraphEdge,
  PathGraphPath,
  UploadMode,
  UploadModeInfo,
  VisualEvidenceItem
} from "./types";

const { Header, Content } = Layout;
const { Text, Title, Paragraph } = Typography;

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
type AppRouteKey = "home" | "analysis" | "kg-studio" | "experiments";
type AnalysisRouteKey = "live" | "history" | "detail";

const TOP_LEVEL_MODULES: Array<{
  key: AppRouteKey;
  path: string;
  label: string;
  description: string;
}> = [
  { key: "home", path: "/", label: "Home", description: "Status and next actions" },
  {
    key: "analysis",
    path: "/analysis/live",
    label: "Analysis",
    description: "Live runs, history, and case detail"
  },
  { key: "kg-studio", path: "/kg-studio", label: "KG Studio", description: "Sources, graph, and drafts" },
  { key: "experiments", path: "/experiments", label: "Experiments", description: "Paper cases and exports" }
];

const ANALYSIS_VIEWS: Array<{
  key: AnalysisRouteKey;
  path: string;
  label: string;
  description: string;
}> = [
  { key: "live", path: "/analysis/live", label: "Live Analysis", description: "Upload and run new evidence" },
  { key: "history", path: "/analysis/history", label: "History", description: "Search previous runs" },
  { key: "detail", path: "/analysis/detail", label: "Detail", description: "Timeline investigation" }
];

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
  return (
    <BrowserRouter>
      <RootLensApp />
    </BrowserRouter>
  );
}

function RootLensApp() {
  const [state, dispatch] = useReducer(reducer, initialState);
  const location = useLocation();
  const navigate = useNavigate();
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
  const pageInfo = pageInfoForPath(location.pathname);
  const activeRoute = activeRouteForPath(location.pathname);

  return (
    <ConfigProvider
      theme={{
        token: {
          colorPrimary: "#0f5f78",
          borderRadius: 8,
          fontFamily:
            "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
        }
      }}
    >
      <Layout className="app-shell">
        <Header className="topbar">
          <div className="topbar-main">
            <div className="brand-block">
              <div className="brand-mark">RL</div>
              <div>
                <p className="eyebrow">RootLens</p>
                <strong>Traceability Studio</strong>
              </div>
            </div>
            <DashboardNav
              activeRoute={activeRoute}
              onRouteSelected={(path) => navigate(path)}
            />
            <div className="topbar-actions">
              <Tag
                className="connection-pill"
                color={apiConnected ? "success" : "default"}
                icon={<ApiOutlined />}
              >
                {apiConnected ? `API ${state.bootstrap?.api_version}` : "API connecting"}
              </Tag>
              <Button
                aria-label="Refresh RootLens API status"
                icon={<ReloadOutlined spin={state.loading} />}
                onClick={() => void loadBootstrap()}
              />
            </div>
          </div>
        </Header>

      {state.loading && (
        <Alert
          className="app-alert"
          message="Working with the local RootLens API..."
          type="info"
          showIcon
        />
      )}

      {state.error && (
        <Alert className="app-alert" message={state.error} type="error" showIcon />
      )}

        <Content className="app-content">
        <section className="page-heading">
          <div>
            <p className="eyebrow">Workspace</p>
            <h1>{pageInfo.label}</h1>
            <span className="page-description">{pageInfo.description}</span>
          </div>
        </section>
        <Routes>
          <Route
            path="/"
            element={
              <HomePage
                bootstrapStatus={state.bootstrap?.status ?? "connecting"}
                apiVersion={state.bootstrap?.api_version ?? "unknown"}
                recentRunCount={state.runs.length}
                selectedRunLabel={state.selectedRun?.run.label ?? "No run selected"}
                kgStatus={state.kgStudio?.status ?? "loading"}
                kgEdgeCount={state.kgStudio?.edge_count ?? 0}
                onNavigate={(path) => navigate(path)}
              />
            }
          />
          <Route path="/analysis" element={<Navigate to="/analysis/live" replace />} />
          <Route
            path="/analysis/live"
            element={
              <AnalysisLivePage
                uploadPanel={
                  <UploadPanel
                    state={state}
                    uploadModes={uploadModes}
                    selectedUploadMode={selectedUploadMode}
                    presets={presets}
                    onUploadChanged={(patch) =>
                      dispatch({ type: "uploadChanged", patch })
                    }
                    onRunUpload={() => void runUpload()}
                  />
                }
                recentRuns={state.runs}
                selectedRunId={state.selectedRun?.run.run_id ?? ""}
                onOpenRun={(runId) => void openRun(runId)}
                onOpenHistory={() => navigate("/analysis/history")}
              />
            }
          />
          <Route
            path="/analysis/history"
            element={
              <AnalysisHistoryPage
                runs={state.runs}
                selectedRunId={state.selectedRun?.run.run_id ?? ""}
                onRefresh={() => void loadRuns()}
                onOpenRun={(runId) => void openRun(runId)}
              />
            }
          />
          <Route
            path="/analysis/:runId"
            element={
              <AnalysisDetailRoute
                run={state.selectedRun}
                loading={state.loading}
                selectedTarget={selectedTarget}
                selectedTargetKey={state.selectedTargetKey}
                reviewNote={state.reviewNote}
                reviewStatus={state.reviewStatus}
                onLoadRun={(runId) => void loadRun(runId)}
                onTargetSelected={(targetKey) =>
                  dispatch({ type: "targetSelected", targetKey })
                }
                onReviewNoteChanged={(note) =>
                  dispatch({ type: "reviewNoteChanged", note })
                }
                onSubmitReview={(action) => void submitReview(action)}
                onOpenHistory={() => navigate("/analysis/history")}
              />
            }
          />
          <Route
            path="/kg-studio"
            element={
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
            }
          />
          <Route
            path="/experiments"
            element={
              <ExperimentsPage
                runCount={state.runs.length}
                kgEdgeCount={state.kgStudio?.edge_count ?? 0}
                onOpenAnalysis={() => navigate("/analysis/history")}
                onOpenKG={() => navigate("/kg-studio")}
              />
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </Content>
      </Layout>
    </ConfigProvider>
  );
}

function pageInfoForPath(pathname: string): { label: string; description: string } {
  if (pathname.startsWith("/analysis")) {
    if (pathname === "/analysis/history") {
      return { label: "Analysis History", description: "Search previous runs and reopen cases" };
    }
    if (pathname !== "/analysis" && pathname !== "/analysis/live") {
      return { label: "Analysis Detail", description: "Timeline-driven case investigation" };
    }
    return { label: "Live Analysis", description: "Upload evidence and run a new analysis" };
  }
  if (pathname.startsWith("/kg-studio")) {
    return { label: "KG Studio", description: "Sources, candidate graph, and review drafts" };
  }
  if (pathname.startsWith("/experiments")) {
    return { label: "Experiments", description: "Paper cases, coverage, and export preparation" };
  }
  return { label: "Home", description: "System status and next actions" };
}

function activeRouteForPath(pathname: string): AppRouteKey {
  if (pathname.startsWith("/analysis")) return "analysis";
  if (pathname.startsWith("/kg-studio")) return "kg-studio";
  if (pathname.startsWith("/experiments")) return "experiments";
  return "home";
}

function DashboardNav({
  activeRoute,
  onRouteSelected
}: {
  activeRoute: AppRouteKey;
  onRouteSelected: (path: string) => void;
}) {
  const menuIcons: Record<AppRouteKey, ReactNode> = {
    home: <HomeOutlined />,
    analysis: <BranchesOutlined />,
    "kg-studio": <DatabaseOutlined />,
    experiments: <BarChart3 size={15} />
  };
  const items: MenuProps["items"] = TOP_LEVEL_MODULES.map((item) => ({
    key: item.key,
    icon: menuIcons[item.key],
    label: (
      <div className="menu-label">
        <span>{item.label}</span>
        <small>{item.description}</small>
      </div>
    )
  }));
  return (
    <Menu
      className="dashboard-nav"
      mode="horizontal"
      theme="light"
      selectedKeys={[activeRoute]}
      items={items}
      onClick={({ key }) => {
        const route = TOP_LEVEL_MODULES.find((item) => item.key === key);
        if (route) onRouteSelected(route.path);
      }}
    />
  );
}

function HomePage({
  bootstrapStatus,
  apiVersion,
  recentRunCount,
  selectedRunLabel,
  kgStatus,
  kgEdgeCount,
  onNavigate
}: {
  bootstrapStatus: string;
  apiVersion: string;
  recentRunCount: number;
  selectedRunLabel: string;
  kgStatus: string;
  kgEdgeCount: number;
  onNavigate: (path: string) => void;
}) {
  return (
    <div className="overview-page">
      <Card className="overview-hero">
        <div>
          <p className="eyebrow">Dashboard</p>
          <Title level={2}>Traceable Industrial Anomaly Workspace</Title>
          <Paragraph>
            Upload evidence, inspect case reasoning, and manage candidate KG
            changes from separate focused pages.
          </Paragraph>
        </div>
        <div className="overview-actions">
          <Button type="primary" icon={<CloudUploadOutlined />} onClick={() => onNavigate("/analysis/live")}>
            New analysis
          </Button>
          <Button icon={<HistoryOutlined />} onClick={() => onNavigate("/analysis/history")}>
            Browse history
          </Button>
          <Button icon={<DatabaseOutlined />} onClick={() => onNavigate("/kg-studio")}>
            Open KG Studio
          </Button>
        </div>
      </Card>

      <section className="overview-metrics">
        <Card>
          <BarChart3 size={18} />
          <Statistic title="API" value={bootstrapStatus} />
          <Text type="secondary">{apiVersion}</Text>
        </Card>
        <Card>
          <HistoryOutlined />
          <Statistic title="Runs" value={recentRunCount} />
          <Text type="secondary">{selectedRunLabel}</Text>
        </Card>
        <Card>
          <Database size={18} />
          <Statistic title="Candidate KG" value={kgStatus} />
          <Text type="secondary">{kgEdgeCount} preview edges</Text>
        </Card>
      </section>

      <section className="overview-flow">
        {TOP_LEVEL_MODULES.filter((item) => item.key !== "home").map((item, index) => (
          <Card
            key={item.key}
            className="overview-flow-card"
            hoverable
            onClick={() => onNavigate(item.path)}
          >
            <span>{`0${index + 1}`}</span>
            <strong>{item.label}</strong>
            <small>{item.description}</small>
          </Card>
        ))}
      </section>
    </div>
  );
}

function AnalysisSubnav({ activeView }: { activeView: AnalysisRouteKey }) {
  const navigate = useNavigate();
  return (
    <Menu
      className="analysis-subnav"
      mode="horizontal"
      selectedKeys={[activeView]}
      items={ANALYSIS_VIEWS.filter((item) => item.key !== "detail").map((item) => ({
        key: item.key,
        label: (
          <div className="menu-label">
            <span>{item.label}</span>
            <small>{item.description}</small>
          </div>
        )
      }))}
      onClick={({ key }) => {
        const view = ANALYSIS_VIEWS.find((item) => item.key === key);
        if (view) navigate(view.path);
      }}
    />
  );
}

function AnalysisLivePage({
  uploadPanel,
  recentRuns,
  selectedRunId,
  onOpenRun,
  onOpenHistory
}: {
  uploadPanel: ReactNode;
  recentRuns: RunSummary[];
  selectedRunId: string;
  onOpenRun: (runId: string) => void;
  onOpenHistory: () => void;
}) {
  return (
    <div className="analysis-module">
      <AnalysisSubnav activeView="live" />
      <section className="analysis-command-strip">
        <div>
          <p className="eyebrow">Live Workspace</p>
          <strong>Run a new investigation from evidence or producer records.</strong>
          <span>
            The result becomes a history entry and opens as a timeline-driven detail view.
          </span>
        </div>
        <Space wrap>
          <Tag color="blue">{recentRuns.length} saved runs</Tag>
          <Button icon={<HistoryOutlined />} onClick={onOpenHistory}>
            Browse history
          </Button>
        </Space>
      </section>
      <section className="analysis-primary">{uploadPanel}</section>
      <Card
        className="analysis-recent-panel"
        title={
          <Space>
            <HistoryOutlined />
            Recent analyses
          </Space>
        }
        extra={
          <Button size="small" onClick={onOpenHistory}>
            View all
          </Button>
        }
      >
        <RunList
          runs={recentRuns.slice(0, 4)}
          selectedRunId={selectedRunId}
          onOpenRun={onOpenRun}
          emptyDescription="No analysis runs yet. Upload evidence to create the first run."
          compact
        />
      </Card>
    </div>
  );
}

function UploadPanel({
  state,
  uploadModes,
  selectedUploadMode,
  presets,
  onUploadChanged,
  onRunUpload
}: {
  state: AppState;
  uploadModes: UploadModeInfo[];
  selectedUploadMode: UploadModeInfo | null;
  presets: Array<Record<string, unknown>>;
  onUploadChanged: (patch: Partial<AppState["upload"]>) => void;
  onRunUpload: () => void;
}) {
  return (
    <Card
      className="upload-panel analysis-upload-panel"
      title={
        <Space>
          <CloudUploadOutlined />
          Live Analysis
        </Space>
      }
    >
      <Form layout="vertical" onFinish={onRunUpload} className="analysis-upload-form">
        <div className="analysis-upload-grid">
          <section className="analysis-upload-main">
            <Form.Item label="Mode">
              <Select
                value={state.upload.mode}
                onChange={(value) => onUploadChanged({ mode: value as UploadMode })}
                options={
                  uploadModes.length
                    ? uploadModes.map((mode) => ({ value: mode.mode, label: mode.label }))
                    : [{ value: state.upload.mode, label: "Loading modes..." }]
                }
              />
            </Form.Item>
            <UploadModeGuidance mode={selectedUploadMode} uploadMode={state.upload.mode} />
            <Form.Item label="File">
              <Upload
                accept={selectedUploadMode?.accepted_extensions.join(",")}
                maxCount={1}
                beforeUpload={(file) => {
                  onUploadChanged({ file });
                  return false;
                }}
                onRemove={() => {
                  onUploadChanged({ file: null });
                }}
              >
                <Button icon={<CloudUploadOutlined />}>Choose file</Button>
              </Upload>
              <Text type="secondary" className="field-hint">
                {state.upload.file
                  ? `${state.upload.file.name} selected`
                  : "Choose a local example file from the paths above."}
              </Text>
            </Form.Item>
          </section>
          <section className="analysis-upload-params">
            <Form.Item label="Dataset">
              <Select
                value={state.upload.dataset}
                onChange={(value) => onUploadChanged({ dataset: value })}
                options={[
                  { value: "", label: "auto" },
                  ...(state.bootstrap?.supported_datasets.map((dataset) => ({
                    value: dataset,
                    label: dataset
                  })) ?? [])
                ]}
              />
            </Form.Item>
            <Form.Item label="Top K">
              <InputNumber
                min={1}
                max={20}
                value={state.upload.topK}
                onChange={(value) => onUploadChanged({ topK: Number(value ?? 1) })}
              />
            </Form.Item>
            {state.upload.mode === "image" && (
              <>
                <Form.Item label="Object">
                  <Input
                    value={state.upload.objectName}
                    onChange={(event) => onUploadChanged({ objectName: event.target.value })}
                  />
                </Form.Item>
                <Form.Item label="Preset">
                  <Select
                    value={state.upload.modelPreset}
                    onChange={(value) => onUploadChanged({ modelPreset: value })}
                    options={[
                      { value: "auto", label: "auto" },
                      ...presets.map((preset) => ({
                        value: String(preset.preset),
                        label: String(preset.preset)
                      }))
                    ]}
                  />
                </Form.Item>
                <Form.Item label="Defect">
                  <Input
                    value={state.upload.defectType}
                    onChange={(event) => onUploadChanged({ defectType: event.target.value })}
                  />
                </Form.Item>
              </>
            )}
            <Button type="primary" htmlType="submit" icon={<SendOutlined />} loading={state.loading} block>
              {state.loading ? "Analyzing" : "Analyze"}
            </Button>
            {state.uploadStatus && <Alert message={state.uploadStatus} type="success" showIcon />}
          </section>
        </div>
      </Form>
    </Card>
  );
}

function AnalysisHistoryPage({
  runs,
  selectedRunId,
  onRefresh,
  onOpenRun
}: {
  runs: RunSummary[];
  selectedRunId: string;
  onRefresh: () => void;
  onOpenRun: (runId: string) => void;
}) {
  const [searchText, setSearchText] = useState("");
  const [datasetFilter, setDatasetFilter] = useState("all");
  const datasetOptions = Array.from(new Set(runs.map((run) => run.dataset ?? "unknown"))).sort();
  const filteredRuns = runs.filter((run) => {
    const dataset = run.dataset ?? "unknown";
    const matchesDataset = datasetFilter === "all" || dataset === datasetFilter;
    const haystack = [
      run.label,
      run.run_id,
      run.source_filename,
      run.mode,
      dataset,
      run.status,
      run.model_backend,
      run.model_preset
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return matchesDataset && haystack.includes(searchText.toLowerCase());
  });
  const columns: TableColumnsType<RunSummary> = [
    {
      title: "Run",
      dataIndex: "label",
      key: "label",
      render: (label: string, run) => (
        <Button type="link" onClick={() => onOpenRun(run.run_id)}>
          {label}
        </Button>
      )
    },
    { title: "Dataset", dataIndex: "dataset", key: "dataset", render: valueText },
    { title: "Mode", dataIndex: "mode", key: "mode" },
    { title: "Cases", dataIndex: "case_count", key: "case_count" },
    { title: "Evidence", dataIndex: "evidence_count", key: "evidence_count" },
    {
      title: "Created",
      dataIndex: "created_at",
      key: "created_at",
      render: (value: string) => new Date(value).toLocaleString()
    },
    {
      title: "Status",
      dataIndex: "status",
      key: "status",
      render: (value: string) => <Tag color={value === "completed" ? "success" : "error"}>{value}</Tag>
    }
  ];
  return (
    <div className="analysis-module">
      <AnalysisSubnav activeView="history" />
      <section className="analysis-command-strip">
        <div>
          <p className="eyebrow">Run Lookup</p>
          <strong>{filteredRuns.length} visible analyses</strong>
          <span>Search and reopen previous RootLens runs for timeline inspection.</span>
        </div>
        <Space wrap className="history-toolbar">
          <Input.Search
            allowClear
            placeholder="Search run, file, dataset, backend"
            value={searchText}
            onChange={(event) => setSearchText(event.target.value)}
          />
          <Select
            value={datasetFilter}
            onChange={setDatasetFilter}
            options={[
              { value: "all", label: "All datasets" },
              ...datasetOptions.map((dataset) => ({ value: dataset, label: dataset }))
            ]}
          />
          <Button icon={<ReloadOutlined />} onClick={onRefresh}>
            Refresh
          </Button>
        </Space>
      </section>
      <Card
        title={
          <Space>
            <HistoryOutlined />
            Analysis History
          </Space>
        }
      >
        <Table
          rowKey="run_id"
          columns={columns}
          dataSource={filteredRuns}
          pagination={{ pageSize: 8 }}
          rowClassName={(run) => (run.run_id === selectedRunId ? "selected-table-row" : "")}
        />
      </Card>
    </div>
  );
}

function RunList({
  runs,
  selectedRunId,
  onOpenRun,
  emptyDescription,
  compact = false
}: {
  runs: RunSummary[];
  selectedRunId: string;
  onOpenRun: (runId: string) => void;
  emptyDescription: string;
  compact?: boolean;
}) {
  if (!runs.length) return <Empty description={emptyDescription} />;
  return (
    <List
      className={`run-list ${compact ? "compact-run-list" : ""}`}
      dataSource={runs}
      renderItem={(run) => (
        <List.Item
          className={`run-row ${selectedRunId === run.run_id ? "selected" : ""}`}
          onClick={() => onOpenRun(run.run_id)}
        >
          <List.Item.Meta
            title={<span className="run-list-title">{run.label}</span>}
            description={
              <div className="run-list-meta">
                <Text type="secondary" className="run-list-line">
                  {run.mode} · {run.dataset ?? "auto"} · {run.case_count} cases
                </Text>
                <Text type="secondary" className="run-list-line">
                  {new Date(run.created_at).toLocaleString()}
                </Text>
              </div>
            }
          />
        </List.Item>
      )}
    />
  );
}

function AnalysisDetailRoute({
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
  selectedTarget: ReviewTarget | undefined;
  selectedTargetKey: string;
  reviewNote: string;
  reviewStatus: string | null;
  loading: boolean;
  onLoadRun: (runId: string) => void;
  onTargetSelected: (targetId: string) => void;
  onReviewNoteChanged: (note: string) => void;
  onSubmitReview: (action: ReviewAction) => void;
  onOpenHistory: () => void;
}) {
  const { runId } = useParams();
  useEffect(() => {
    if (runId && run?.run.run_id !== runId) {
      onLoadRun(runId);
    }
  }, [onLoadRun, run?.run.run_id, runId]);

  if (!run && loading) {
    return (
      <Card className="empty-state">
        <Empty description="Loading analysis detail..." />
      </Card>
    );
  }
  if (!run) {
    return (
      <Card className="empty-state">
        <Empty
          description="Select a history item or upload an example record file to inspect candidate paths."
        />
        <Button onClick={onOpenHistory}>Open history</Button>
      </Card>
    );
  }
  return (
    <RunDetailView
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

function ExperimentsPage({
  runCount,
  kgEdgeCount,
  onOpenAnalysis,
  onOpenKG
}: {
  runCount: number;
  kgEdgeCount: number;
  onOpenAnalysis: () => void;
  onOpenKG: () => void;
}) {
  return (
    <div className="experiments-page">
      <Card className="overview-hero">
        <div>
          <p className="eyebrow">Paper Mode</p>
          <Title level={2}>Experiment and Case Study Workspace</Title>
          <Paragraph>
            This module is reserved for paper cases, coverage summaries,
            before/after KG hardening tables, and export-ready artifacts.
          </Paragraph>
        </div>
        <div className="overview-actions">
          <Button type="primary" icon={<HistoryOutlined />} onClick={onOpenAnalysis}>
            Open analysis history
          </Button>
          <Button icon={<DatabaseOutlined />} onClick={onOpenKG}>
            Inspect KG coverage
          </Button>
        </div>
      </Card>
      <section className="overview-metrics">
        <Card>
          <Statistic title="analysis runs" value={runCount} />
          <Text type="secondary">local RootLens sessions</Text>
        </Card>
        <Card>
          <Statistic title="candidate KG edges" value={kgEdgeCount} />
          <Text type="secondary">available to paper case reasoning</Text>
        </Card>
        <Card>
          <Statistic title="exports" value="planned" />
          <Text type="secondary">tables, markdown, and figures</Text>
        </Card>
      </section>
    </div>
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
    <Card
      className="kg-studio-panel"
      title={
        <Space>
          <DatabaseOutlined />
          KG Studio
        </Space>
      }
      extra={
        <Button icon={<ReloadOutlined />} onClick={onRefresh}>
          Refresh
        </Button>
      }
    >
      {payload ? (
        <>
          <Alert className="claim-boundary" message={payload.note} type="warning" showIcon />
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
                <Select
                  value={selectedTargetKey}
                  onChange={(value) => onTargetSelected(value)}
                  disabled={!payload.review_targets.length}
                  options={
                    payload.review_targets.length > 0
                      ? payload.review_targets.slice(0, 80).map((target) => ({
                          value: target.target_key,
                          label: shortId(target.label)
                        }))
                      : [{ value: "", label: "No KG edge targets" }]
                  }
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
                  <Button
                    onClick={() => onSubmitReview("needs_review")}
                    disabled={!selectedTarget}
                  >
                    Needs review
                  </Button>
                </div>
                {reviewStatus && <Alert message={`Feedback ${reviewStatus}.`} type="success" showIcon />}
              </div>
            </section>
          </div>
        </>
      ) : (
        <Empty description="Reading source registry and candidate KG artifacts from local project paths." />
      )}
    </Card>
  );
}

function Metric({ label, value }: { label: string; value: unknown }) {
  return (
    <Card size="small">
      <Statistic title={label} value={valueText(value)} />
    </Card>
  );
}

function KGSourceList({ sources }: { sources: KGStudioSource[] }) {
  if (!sources.length) return <Empty description="No source registry rows found." />;
  return (
    <List
      className="compact-list"
      size="small"
      dataSource={sources.slice(0, 10)}
      renderItem={(source) => (
        <List.Item>
          <List.Item.Meta
            title={source.source_id}
            description={
              <Space direction="vertical" size={0}>
                <Text type="secondary">{source.used_for}</Text>
                <Text type="secondary">{source.path_or_url}</Text>
              </Space>
            }
          />
        </List.Item>
      )}
    />
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
      />
      <Button type="primary" onClick={onGenerate}>
        Generate candidates
      </Button>
      {result && (
        <div className="source-draft-results">
          <Tag color="processing">{result.candidate_edges.length} candidate edge(s)</Tag>
          {result.candidate_edges.slice(0, 4).map((edge) => (
            <code key={edge.edge_id}>{edge.edge_id}</code>
          ))}
        </div>
      )}
    </div>
  );
}

function KGSourceDocumentList({ documents }: { documents: KGStudioSourceDocument[] }) {
  if (!documents.length) return <Empty description="No source documents found." />;
  return (
    <List
      className="compact-list"
      size="small"
      dataSource={documents.slice(0, 8)}
      renderItem={(document) => (
        <List.Item>
          <List.Item.Meta title={document.title} description={document.path} />
        </List.Item>
      )}
    />
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
      />
      <Button type="primary" onClick={onSubmitDraft} disabled={!selectedTarget}>
        Save draft
      </Button>
      {draftStatus && <Alert message={`Draft ${draftStatus}.`} type="success" showIcon />}
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
    return <Empty description="Generate candidate KG artifacts first, then refresh this panel." />;
  }
  return (
    <List
      className="kg-edge-list"
      size="small"
      dataSource={edges.slice(0, 40)}
      renderItem={(edge) => (
        <List.Item
          className={selectedTargetKey === edge.target_key ? "selected" : ""}
          onClick={() => onTargetSelected(edge.target_key)}
        >
          <List.Item.Meta
            title={
              <Space wrap>
                <Text>{edge.head}</Text>
                <Tag color="blue">{edge.relation}</Tag>
                <Text>{edge.tail}</Text>
              </Space>
            }
            description={`${edge.scenario} · ${edge.source} · ${valueText(edge.confidence)}`}
          />
        </List.Item>
      )}
    />
  );
}

function KGEdgeInspector({ edge }: { edge: KGStudioGraphEdge | undefined }) {
  if (!edge) {
    return <Empty description="Select a candidate KG edge to inspect provenance." />;
  }
  return (
    <Descriptions className="kg-edge-inspector" size="small" column={1} bordered>
      <Descriptions.Item label="edge">{shortId(edge.edge_id)}</Descriptions.Item>
      <Descriptions.Item label="scenario">{edge.scenario}</Descriptions.Item>
      <Descriptions.Item label="source">{edge.source}</Descriptions.Item>
      <Descriptions.Item label="confidence">{valueText(edge.confidence)}</Descriptions.Item>
      <Descriptions.Item label="review status">{edge.review_status}</Descriptions.Item>
      <Descriptions.Item label="evidence">{edge.evidence}</Descriptions.Item>
    </Descriptions>
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

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function asRecordList(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.map(asRecord).filter((item) => item !== null) : [];
}

function asReviewTargets(value: unknown): ReviewTarget[] {
  return Array.isArray(value) ? (value as ReviewTarget[]) : [];
}

function asPathGraph(value: unknown): PathGraph | null {
  const record = asRecord(value);
  if (!record || !Array.isArray(record.paths)) return null;
  return record as unknown as PathGraph;
}

function RunDetailView({
  run,
  selectedTargetKey,
  reviewNote,
  reviewStatus,
  onTargetSelected,
  onReviewNoteChanged,
  onSubmitReview
}: RunDetailProps) {
  const [activeStep, setActiveStep] = useState(0);
  const caseRows = run.cases ?? [];
  const [selectedCaseId, setSelectedCaseId] = useState("");
  useEffect(() => {
    setSelectedCaseId(caseRows.length > 0 ? valueText(caseRows[0].case_id) : "");
  }, [run.run.run_id, caseRows.length]);
  const selectedCase =
    caseRows.find((caseRow) => valueText(caseRow.case_id) === selectedCaseId) ?? caseRows[0];
  const selectedCaseKey = selectedCase ? valueText(selectedCase.case_id) : "";
  const evidence = asRecord(selectedCase?.generated_evidence) ?? run.evidence_summary ?? {};
  const linkedEntities = selectedCase
    ? asRecordList(selectedCase.linked_entities)
    : run.linked_entities;
  const correctionCandidates = selectedCase
    ? asRecordList(selectedCase.correction_candidates)
    : run.correction_candidates;
  const pathGraph = asPathGraph(selectedCase?.path_graph) ?? run.path_graph ?? {
    paths: [],
    path_count: 0,
    node_count: 0,
    edge_count: 0
  };
  const selectedCaseReviewTargets = asReviewTargets(selectedCase?.review_targets);
  const reviewTargets =
    selectedCaseReviewTargets.length > 0 ? selectedCaseReviewTargets : run.review_targets;
  const activeSelectedTarget = reviewTargets.find(
    (target) => target.target_key === selectedTargetKey
  );
  const visualEvidence = selectedCaseKey
    ? (run.visual_evidence ?? []).filter((item) => item.case_id === selectedCaseKey)
    : (run.visual_evidence ?? []);
  const stages: Array<{ title: string; description: string; content: ReactNode }> = [
    {
      title: "Input",
      description: "Run metadata and workflow",
      content: (
        <div className="analysis-stage-grid">
          <Card title="Run Summary">
            <Descriptions size="small" column={2} bordered>
              <Descriptions.Item label="run id">{run.run.run_id}</Descriptions.Item>
              <Descriptions.Item label="source">{run.run.source_filename}</Descriptions.Item>
              <Descriptions.Item label="dataset">{valueText(run.run.dataset)}</Descriptions.Item>
              <Descriptions.Item label="mode">{run.run.mode}</Descriptions.Item>
              <Descriptions.Item label="cases">{run.run.case_count}</Descriptions.Item>
              <Descriptions.Item label="evidence">{run.run.evidence_count}</Descriptions.Item>
              <Descriptions.Item label="created">
                {new Date(run.run.created_at).toLocaleString()}
              </Descriptions.Item>
              <Descriptions.Item label="status">{run.run.status}</Descriptions.Item>
            </Descriptions>
          </Card>
          <Card title={<Space><CheckOutlined />Workflow</Space>}>
            <List
              size="small"
              dataSource={run.workflow_steps}
              renderItem={(step) => (
                <List.Item>
                  <List.Item.Meta title={step.title} description={step.summary} />
                </List.Item>
              )}
            />
          </Card>
        </div>
      )
    },
    {
      title: "Model Evidence",
      description: "Observed anomaly fields",
      content: (
        <div className="analysis-stage-grid visual-evidence-layout">
          <Card className="visual-evidence-card" title="Visual Evidence">
            <VisualEvidencePanel items={visualEvidence} />
          </Card>
          <Card title="Evidence Summary">
            <Descriptions size="small" column={2} bordered>
              {[
                "case_id",
                "dataset",
                "object",
                "anomaly_type",
                "location",
                "morphology",
                "severity",
                "confidence"
              ].map((key) => (
                <Descriptions.Item key={key} label={key}>
                  {valueText(evidence[key])}
                </Descriptions.Item>
              ))}
            </Descriptions>
          </Card>
          <Card title="Artifacts">
            {Object.keys(run.artifacts).length ? (
              <List
                size="small"
                dataSource={Object.entries(run.artifacts)}
                renderItem={([key, value]) => (
                  <List.Item>
                    <List.Item.Meta title={key} description={value} />
                  </List.Item>
                )}
              />
            ) : (
              <Empty description="No artifact paths were recorded for this run." />
            )}
          </Card>
        </div>
      )
    },
    {
      title: "Normalized Evidence",
      description: "Adapter output and schema payload",
      content: (
        <div className="analysis-stage-grid single">
          <Card title="Evidence JSON">
            <JsonBlock value={run.evidence_with_analysis ?? run.evidence ?? run.summary} />
          </Card>
        </div>
      )
    },
    {
      title: "Entity Linking",
      description: "KG entity matches",
      content: (
        <div className="analysis-stage-grid single">
          <Card title="Linked Entities">
            <CompactList
              items={linkedEntities}
              idField="link_id"
              labelField="selected_entity_id"
            />
          </Card>
        </div>
      )
    },
    {
      title: "Consistency",
      description: "Corrections and ambiguity",
      content: (
        <div className="analysis-stage-grid">
          <Card title="Correction Candidates">
            <CompactList
              items={correctionCandidates}
              idField="candidate_id"
              labelField="suggested_value"
            />
          </Card>
          <Card title="Analysis Summary">
            <JsonBlock value={selectedCase ?? run.analysis ?? run.summary} />
          </Card>
        </div>
      )
    },
    {
      title: "Candidate Paths",
      description: "Ranked traceability paths",
      content: (
        <ReasoningWorkspace
          paths={pathGraph.paths}
          selectedTarget={activeSelectedTarget}
          onTargetSelected={onTargetSelected}
        />
      )
    },
    {
      title: "Review",
      description: "Provenance and feedback",
      content: (
        <Card className="review-panel" title="Review Targets">
          <Alert
            className="claim-boundary"
            message={run.claim_boundary}
            type="warning"
            showIcon
          />
          <ReviewQueue
            targets={reviewTargets}
            selectedTargetKey={selectedTargetKey}
            onTargetSelected={onTargetSelected}
          />
          <div className="review-controls">
            <Select
              className="review-target-select"
              value={selectedTargetKey}
              onChange={(value) => onTargetSelected(value)}
              disabled={!reviewTargets.length}
              options={
                reviewTargets.length > 0
                  ? reviewTargets.map((target) => ({
                      value: target.target_key,
                      label: `${target.target_type} · ${shortId(target.label)}`
                    }))
                  : [{ value: "", label: "No review targets" }]
              }
            />
            <Input
              className="review-note"
              value={reviewNote}
              onChange={(event) => onReviewNoteChanged(event.target.value)}
              placeholder="optional review note"
              disabled={!activeSelectedTarget}
            />
            <Button onClick={() => onSubmitReview("accept")} disabled={!activeSelectedTarget}>
              <CheckOutlined />
              Accept
            </Button>
            <Button onClick={() => onSubmitReview("reject")} disabled={!activeSelectedTarget}>
              <CloseOutlined />
              Reject
            </Button>
            <Button onClick={() => onSubmitReview("needs_review")} disabled={!activeSelectedTarget}>
              Needs review
            </Button>
          </div>
          {activeSelectedTarget ? (
            <p className="muted">Stable target key: {activeSelectedTarget.target_key}</p>
          ) : (
            <p className="muted">No feedback target is available for this run.</p>
          )}
          {reviewStatus && (
            <Alert message={`Feedback ${reviewStatus}.`} type="success" showIcon />
          )}
        </Card>
      )
    }
  ];

  return (
    <div className="analysis-detail-page">
      <Card className="analysis-case-header">
        <div>
          <p className="eyebrow">Analysis Detail</p>
          <Title level={2}>{run.run.label}</Title>
          <Text type="secondary">
            {valueText(evidence.dataset)} · {valueText(evidence.object)} ·{" "}
            {valueText(evidence.anomaly_type)}
          </Text>
        </div>
        <Space wrap>
          <Tag color="blue">{pathGraph.path_count} paths</Tag>
          <Tag color="processing">{linkedEntities.length} linked entities</Tag>
          <Tag color="warning">{correctionCandidates.length} corrections</Tag>
          {caseRows.length > 1 && (
            <Select
              className="case-selector"
              value={selectedCaseKey}
              onChange={setSelectedCaseId}
              options={caseRows.map((caseRow) => ({
                value: valueText(caseRow.case_id),
                label: valueText(caseRow.case_id)
              }))}
            />
          )}
        </Space>
      </Card>
      <Card className="analysis-timeline-card">
        <Steps
          current={activeStep}
          onChange={setActiveStep}
          responsive={false}
          size="small"
          type="navigation"
          items={stages.map((stage) => ({
            title: stage.title
          }))}
        />
      </Card>
      <section className="analysis-stage-canvas">{stages[activeStep]?.content}</section>
    </div>
  );
}

function VisualEvidencePanel({ items }: { items: VisualEvidenceItem[] }) {
  if (!items.length) {
    return <Empty description="No visual evidence artifacts were recorded for this run." />;
  }
  return (
    <div className="visual-evidence-grid">
      {items.map((item) => (
        <article className="visual-evidence-item" key={item.artifact_id}>
          <div className="visual-evidence-preview">
            {item.available && item.url ? (
              <img src={item.url} alt={`${item.title} for ${item.case_id}`} />
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Preview unavailable" />
            )}
          </div>
          <div className="visual-evidence-meta">
            <div>
              <strong>{item.title}</strong>
              <span>{item.case_id}</span>
            </div>
            <Space wrap>
              <Tag color={item.available ? "green" : "default"}>
                {item.available ? "available" : "missing"}
              </Tag>
              <Tag color="blue">{item.kind}</Tag>
              <Tag>{item.dataset}</Tag>
            </Space>
            <p>{item.note}</p>
            {item.source_path && (
              <code title={item.source_path}>
                {item.source_key}: {shortId(item.source_path)}
              </code>
            )}
          </div>
        </article>
      ))}
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
    <Card className="wide reasoning-workspace" title={<Space><BranchesOutlined />Path Graph</Space>}>
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
        <Empty description="This run returned no candidate reasoning paths. Linked entities and corrections can still be reviewed below." />
      )}
    </Card>
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
    return <Empty description="No review targets are available for this run." />;
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
          <Space wrap>
            {group.slice(0, 8).map((target) => (
              <Tag.CheckableTag
                key={target.target_key}
                checked={selectedTargetKey === target.target_key}
                onChange={() => onTargetSelected(target.target_key)}
              >
                {shortId(target.label)}
              </Tag.CheckableTag>
            ))}
          </Space>
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
        <InfoCircleOutlined />
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

function JsonBlock({ value }: { value: unknown }) {
  if (value === null || value === undefined) {
    return <Empty description="No structured payload recorded." />;
  }
  return <pre className="json-block">{JSON.stringify(value, null, 2)}</pre>;
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
  if (!items.length) return <Empty description="No items recorded." />;
  return (
    <List
      className="compact-list"
      size="small"
      dataSource={items.slice(0, 8)}
      renderItem={(item, index) => (
        <List.Item key={String(item[idField] ?? index)}>
          <List.Item.Meta
            title={shortId(valueText(item[idField] ?? index))}
            description={valueText(item[labelField])}
          />
        </List.Item>
      )}
    />
  );
}
