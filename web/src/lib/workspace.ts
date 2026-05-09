import type { Evidence } from "../types";

export function casePathCount(item: Record<string, unknown>) {
  const paths = item.top_k_paths;
  return Array.isArray(paths) ? paths.length : null;
}

export function fieldsFromEvidence(evidence: Evidence) {
  return {
    anomaly_type: evidence.anomaly_type ?? "",
    location: evidence.location ?? "",
    morphology: evidence.morphology ?? "",
    variables: evidence.raw_evidence.variables.join("\n"),
    log_events: evidence.raw_evidence.log_events.join("\n"),
    severity: evidence.severity === null || evidence.severity === undefined ? "" : String(evidence.severity),
    confidence:
      evidence.confidence === null || evidence.confidence === undefined
        ? ""
        : String(evidence.confidence),
  };
}

export function splitLines(value: string) {
  return value
    .replaceAll(",", "\n")
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function parseOptionalNumber(value: string) {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
}

export function formatValue(value: unknown) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  if (typeof value === "number") {
    return Number.isInteger(value) ? value.toString() : value.toFixed(4);
  }
  return String(value);
}

export function messageOf(error: unknown) {
  return error instanceof Error ? error.message : "Unexpected error";
}
