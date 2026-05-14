import { Button, Card, Empty, Space, Table, Tag, Typography } from "@arco-design/web-react";
import { IconBranch, IconHistory, IconLaunch } from "@arco-design/web-react/icon";

import type { DashboardBootstrap, KGStudioPayload, RunSummary } from "../../api/contracts";
import { shortId, valueText } from "../../api/format";
import { MetricCard } from "../../components/common/MetricCard";

const { Title, Paragraph } = Typography;

export function HomePage({
  bootstrap,
  kgStudio,
  runs,
  onOpenAnalysis,
  onOpenKGStudio,
  onOpenRun
}: {
  bootstrap: DashboardBootstrap | null;
  kgStudio: KGStudioPayload | null;
  runs: RunSummary[];
  onOpenAnalysis: () => void;
  onOpenKGStudio: () => void;
  onOpenRun: (runId: string) => void;
}) {
  return (
    <div className="page-stack">
      <section className="hero-panel">
        <div>
          <span className="eyebrow">Research Prototype</span>
          <Title heading={2}>Knowledge-enhanced RCA evidence workspace</Title>
          <Paragraph>
            Inspect anomaly evidence, KG linking, consistency checks, correction candidates, and
            ranked root-cause paths from one local workbench.
          </Paragraph>
        </div>
        <Space wrap>
          <Button type="primary" icon={<IconLaunch />} onClick={onOpenAnalysis}>
            Start analysis
          </Button>
          <Button icon={<IconBranch />} onClick={onOpenKGStudio}>
            Open KG Studio
          </Button>
        </Space>
      </section>

      <section className="metric-grid">
        <MetricCard
          label="API status"
          value={bootstrap?.status ?? "unknown"}
          hint={bootstrap?.api_version ?? "waiting for bootstrap"}
        />
        <MetricCard
          label="Supported datasets"
          value={bootstrap?.supported_datasets.length ?? 0}
          hint={bootstrap?.supported_datasets.join(", ") || "none"}
        />
        <MetricCard
          label="Candidate KG edges"
          value={kgStudio?.edge_count ?? 0}
          hint={`${kgStudio?.node_count ?? 0} nodes`}
        />
        <MetricCard label="Recent runs" value={runs.length} hint="local run registry" />
      </section>

      <section className="two-column">
        <Card title="Claim Boundary">
          <Tag color="orangered">source constrained</Tag>
          <p className="body-copy">{bootstrap?.claim_boundary ?? kgStudio?.claim_boundary ?? "Loading."}</p>
        </Card>
        <Card title="KG Coverage">
          {kgStudio ? (
            <div className="tag-cloud">
              {Object.entries(kgStudio.scenario_counts).map(([scenario, count]) => (
                <Tag key={scenario} color="arcoblue">
                  {scenario}: {count}
                </Tag>
              ))}
              {Object.entries(kgStudio.review_status_counts).map(([status, count]) => (
                <Tag key={status} color={status === "reviewed" ? "green" : "gray"}>
                  {status}: {count}
                </Tag>
              ))}
            </div>
          ) : (
            <Empty description="KG Studio payload has not loaded yet." />
          )}
        </Card>
      </section>

      <Card title={<Space><IconHistory />Recent Analyses</Space>}>
        <Table
          rowKey="run_id"
          data={runs.slice(0, 8)}
          pagination={false}
          noDataElement={<Empty description="No runs recorded yet." />}
          columns={[
            {
              title: "Run",
              dataIndex: "label",
              render: (_, row) => (
                <Button type="text" onClick={() => onOpenRun(row.run_id)}>
                  {shortId(row.label, 48)}
                </Button>
              )
            },
            { title: "Dataset", dataIndex: "dataset", render: valueText },
            { title: "Mode", dataIndex: "mode" },
            { title: "Cases", dataIndex: "case_count" },
            {
              title: "Status",
              dataIndex: "status",
              render: (status) => <Tag color={status === "completed" ? "green" : "red"}>{status}</Tag>
            }
          ]}
        />
      </Card>
    </div>
  );
}
