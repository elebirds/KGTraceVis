import { Empty } from "@arco-design/web-react";

export function JsonBlock({ value }: { value: unknown }) {
  if (value === null || value === undefined) {
    return <Empty description="No structured payload recorded." />;
  }
  return <pre className="json-block">{JSON.stringify(value, null, 2)}</pre>;
}
