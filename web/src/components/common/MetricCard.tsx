import { Card, Statistic } from "@arco-design/web-react";

export function MetricCard({
  label,
  value,
  hint
}: {
  label: string;
  value: string | number;
  hint?: string;
}) {
  return (
    <Card className="metric-card">
      <Statistic title={label} value={value} />
      {hint && <span className="metric-hint">{hint}</span>}
    </Card>
  );
}
