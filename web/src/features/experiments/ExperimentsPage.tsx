import { Button, Card, Typography } from "@arco-design/web-react";
import { IconBranch, IconHistory } from "@arco-design/web-react/icon";

import { MetricCard } from "../../components/common/MetricCard";

const { Title, Paragraph } = Typography;

export function ExperimentsPage({
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
    <div className="page-stack">
      <section className="hero-panel compact">
        <div>
          <span className="eyebrow">Paper Mode</span>
          <Title heading={2}>Experiment and case-study staging</Title>
          <Paragraph>
            A compact landing area for reproducible paper cases, coverage summaries, and export
            readiness checks.
          </Paragraph>
        </div>
        <div className="button-row">
          <Button type="primary" icon={<IconHistory />} onClick={onOpenAnalysis}>
            Analysis history
          </Button>
          <Button icon={<IconBranch />} onClick={onOpenKG}>
            KG coverage
          </Button>
        </div>
      </section>
      <section className="metric-grid">
        <MetricCard label="analysis runs" value={runCount} hint="local RootLens sessions" />
        <MetricCard label="candidate KG edges" value={kgEdgeCount} hint="paper case reasoning" />
        <MetricCard label="exports" value="planned" hint="figures, markdown, tables" />
      </section>
      <Card>
        <p className="body-copy">
          Keep this page intentionally quiet until the experiment protocol settles. The primary
          proof points still live in Analysis detail and KG Studio provenance.
        </p>
      </Card>
    </div>
  );
}
