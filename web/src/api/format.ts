export function valueText(value: unknown): string {
  if (value === null || value === undefined || value === "") return "unknown";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(3);
  if (Array.isArray(value)) return value.length ? value.map(valueText).join(", ") : "none";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function shortId(value: string | null | undefined, maxLength = 42): string {
  if (!value) return "unknown";
  return value.length > maxLength ? `${value.slice(0, maxLength - 3)}...` : value;
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function recordList(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.filter(isRecord) : [];
}
