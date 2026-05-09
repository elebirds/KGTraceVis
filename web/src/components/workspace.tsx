import {
  Activity,
  ArrowRight,
  CheckCircle2,
  FileJson,
  ThumbsDown,
  ThumbsUp,
  type LucideIcon,
} from "lucide-react";
import type { ReactNode } from "react";

import type { AnalysisResponse, CaseSummary, PathResult, RunStep, RunSummary } from "../types";
import { formatValue } from "../lib/workspace";

export function SectionHeader({
  icon: Icon,
  title,
  subtitle,
  actions,
}: {
  icon: LucideIcon;
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 border-b border-zinc-800 px-4 py-3">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <Icon className="h-4 w-4 text-cyan-300" />
          <div className="text-sm font-semibold text-zinc-100">{title}</div>
        </div>
        {subtitle ? <div className="mt-1 truncate text-xs text-zinc-400">{subtitle}</div> : null}
      </div>
      {actions ? <div className="shrink-0">{actions}</div> : null}
    </div>
  );
}

export function MetricChip({
  icon: Icon,
  label,
  value,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
}) {
  return (
    <div className="inline-flex items-center gap-2 rounded-md border border-zinc-800 bg-zinc-900 px-3 py-2 text-xs text-zinc-300">
      <Icon className="h-4 w-4 text-zinc-500" />
      <span className="uppercase tracking-wide text-zinc-500">{label}</span>
      <span className="font-medium text-zinc-100">{value}</span>
    </div>
  );
}

export function MetricBlock({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-zinc-800 bg-zinc-950/60 px-3 py-2">
      <div className="text-[11px] uppercase tracking-wide text-zinc-500">{label}</div>
      <div className="mt-1 text-lg font-semibold text-zinc-100">{value}</div>
    </div>
  );
}

export function CaseQueue({
  items,
  selectedCaseId,
  onSelect,
}: {
  items: CaseSummary[];
  selectedCaseId: string;
  onSelect: (caseId: string) => void;
}) {
  if (!items.length) {
    return <EmptyState title="No cases" body="No evidence cases match the current filter." />;
  }
  return (
    <div>
      {items.map((item) => (
        <button
          key={item.case_id}
          className={`queue-row ${item.case_id === selectedCaseId ? "queue-row-active" : ""}`}
          onClick={() => onSelect(item.case_id)}
          type="button"
        >
          <div className="min-w-0">
            <div className="truncate text-sm font-medium text-zinc-100">{item.case_id}</div>
            <div className="mt-1 truncate text-xs text-zinc-500">{item.label}</div>
          </div>
          <div className="flex shrink-0 flex-col items-end gap-1">
            <span className="badge">{item.dataset}</span>
            <span className={item.is_real_output ? "badge badge-accent" : "badge"}>{item.source_kind}</span>
          </div>
        </button>
      ))}
    </div>
  );
}

export function RunQueue({
  items,
  selectedRunId,
  onSelect,
}: {
  items: RunSummary[];
  selectedRunId: string;
  onSelect: (runId: string) => void;
}) {
  if (!items.length) {
    return <EmptyState title="No runs" body="Upload a file to create the first run session." />;
  }
  return (
    <div>
      {items.map((item) => (
        <button
          key={item.run_id}
          className={`queue-row ${item.run_id === selectedRunId ? "queue-row-active" : ""}`}
          onClick={() => onSelect(item.run_id)}
          type="button"
        >
          <div className="min-w-0">
            <div className="truncate text-sm font-medium text-zinc-100">{item.label}</div>
            <div className="mt-1 truncate text-xs text-zinc-500">{item.source_filename}</div>
            <div className="mt-2 flex flex-wrap gap-1">
              <span className="badge">{item.case_count} cases</span>
              <span className="badge">{item.evidence_count} evidence</span>
            </div>
          </div>
          <div className="flex shrink-0 flex-col items-end gap-1">
            <span className="badge">{item.mode}</span>
            <span className="badge">{item.dataset ?? "auto"}</span>
          </div>
        </button>
      ))}
    </div>
  );
}

export function Subsection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-md border border-zinc-800 bg-zinc-950/30">
      <div className="border-b border-zinc-800 px-3 py-2">
        <div className="panel-title">{title}</div>
      </div>
      <div className="p-3">{children}</div>
    </section>
  );
}

export function LinkedEntitiesTable({
  links,
}: {
  links: AnalysisResponse["analysis"]["linked_entities"];
}) {
  if (!links.length) {
    return <EmptyState title="No links" body="Entity links appear after pipeline analysis." />;
  }
  return (
    <div className="table-shell max-h-72">
      <table className="min-w-full text-sm">
        <thead>
          <tr>
            <th>Field</th>
            <th>Mention</th>
            <th>Entity</th>
            <th>Score</th>
          </tr>
        </thead>
        <tbody>
          {links.map((link) => (
            <tr key={link.link_id}>
              <td>{link.field}</td>
              <td>{link.mention}</td>
              <td>
                <div className="flex flex-wrap items-center gap-2">
                  <span>{link.selected_entity_id ?? "none"}</span>
                  {link.ambiguous ? <span className="badge badge-warn">ambiguous</span> : null}
                </div>
              </td>
              <td>{formatValue(link.score)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function CorrectionTable({
  candidates,
}: {
  candidates: AnalysisResponse["analysis"]["correction_candidates"];
}) {
  if (!candidates.length) {
    return <EmptyState title="No corrections" body="The checker did not propose corrections for this case." />;
  }
  return (
    <div className="table-shell max-h-72">
      <table className="min-w-full text-sm">
        <thead>
          <tr>
            <th>Field</th>
            <th>Suggestion</th>
            <th>Score</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
          {candidates.map((candidate) => (
            <tr key={candidate.candidate_id}>
              <td>{candidate.field}</td>
              <td>{candidate.suggested_value ?? candidate.suggested_entity_id ?? "-"}</td>
              <td>{formatValue(candidate.score)}</td>
              <td>{candidate.reason ?? "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function PathRow({
  path,
  onAccept,
  onReject,
  onSelect,
}: {
  path: PathResult;
  onAccept: () => void;
  onReject: () => void;
  onSelect: () => void;
}) {
  return (
    <div className="rounded-md border border-zinc-800 bg-zinc-950/50 p-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2 text-sm font-medium text-zinc-100">
            {path.node_names.map((node, index) => (
              <span key={`${path.path_id}-${node}-${index}`} className="inline-flex items-center gap-2">
                <span>{node}</span>
                {index < path.node_names.length - 1 ? <ArrowRight className="h-3 w-3 text-zinc-600" /> : null}
              </span>
            ))}
          </div>
          <div className="mt-1 truncate text-xs text-zinc-500">
            {path.relations.join(" / ")} · {path.path_id}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span className="badge badge-accent">{formatValue(path.score)}</span>
          <button className="button-ghost" onClick={onSelect} type="button">
            Select
          </button>
        </div>
      </div>
      <div className="mt-2 text-sm text-zinc-400">
        {path.supporting_evidence?.join("; ") || "No supporting evidence text"}
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <button className="button" onClick={onAccept} type="button">
          <ThumbsUp className="h-4 w-4" />
          Accept
        </button>
        <button className="button" onClick={onReject} type="button">
          <ThumbsDown className="h-4 w-4" />
          Reject
        </button>
      </div>
    </div>
  );
}

export function LabeledInput({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="block">
      <div className="field-label">{label}</div>
      <input className="input mt-1" value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

export function LabeledTextArea({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="block">
      <div className="field-label">{label}</div>
      <textarea
        className="input mt-1 min-h-24"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

export function InfoField({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-zinc-800 bg-zinc-950/60 p-3">
      <div className="text-[11px] uppercase tracking-wide text-zinc-500">{label}</div>
      <div className="mt-1 break-words text-sm text-zinc-100">{value}</div>
    </div>
  );
}

export function WorkflowSteps({ steps, compact = false }: { steps: RunStep[]; compact?: boolean }) {
  if (!steps.length) {
    return <EmptyState title="No workflow steps" body="No step trace is available for this item." />;
  }
  return (
    <div className="space-y-2">
      {!compact ? <div className="panel-title">Workflow steps</div> : null}
      <div className="overflow-hidden rounded-md border border-zinc-800">
        {steps.map((step, index) => (
          <details key={step.step_id} className="group border-b border-zinc-800 last:border-b-0">
            <summary className="flex cursor-pointer list-none items-start justify-between gap-3 bg-zinc-950/40 px-3 py-3 transition hover:bg-zinc-900/70">
              <div className="min-w-0">
                <div className="flex items-center gap-2 text-sm font-medium text-zinc-100">
                  <span className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-cyan-800 bg-cyan-950 text-[11px] text-cyan-200">
                    {index + 1}
                  </span>
                  <span className="truncate">{step.title}</span>
                </div>
                <div className="mt-1 text-xs text-zinc-500">{step.summary}</div>
              </div>
              <span className={step.status === "completed" ? "badge badge-good" : "badge badge-bad"}>
                {step.status}
              </span>
            </summary>
            <pre className="scrollbar-thin max-h-72 overflow-auto border-t border-zinc-800 bg-zinc-950 p-3 text-xs text-zinc-300">
              {JSON.stringify(step.details, null, 2)}
            </pre>
          </details>
        ))}
      </div>
    </div>
  );
}

export function KeyValueList({ items }: { items: Record<string, unknown> }) {
  return (
    <div className="space-y-2 text-sm">
      {Object.entries(items).map(([key, value]) => (
        <div key={key} className="grid grid-cols-[120px_minmax(0,1fr)] gap-3">
          <div className="text-xs uppercase tracking-wide text-zinc-500">{key}</div>
          <div className="break-words text-zinc-300">{formatValue(value)}</div>
        </div>
      ))}
    </div>
  );
}

export function LogLine({ tone, text }: { tone: "good" | "bad"; text: string }) {
  return (
    <div className="flex items-start gap-2 rounded-md border border-zinc-800 bg-zinc-950/60 px-3 py-2">
      {tone === "good" ? (
        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-300" />
      ) : (
        <Activity className="mt-0.5 h-4 w-4 shrink-0 text-rose-300" />
      )}
      <span className={tone === "good" ? "text-emerald-200" : "text-rose-200"}>{text}</span>
    </div>
  );
}

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="px-4 py-8 text-center">
      <FileJson className="mx-auto h-6 w-6 text-zinc-600" />
      <div className="mt-2 text-sm font-medium text-zinc-300">{title}</div>
      <div className="mt-1 text-xs text-zinc-500">{body}</div>
    </div>
  );
}
