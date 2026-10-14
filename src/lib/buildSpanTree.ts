import type { ExecutionEvent } from "../types";

/**
 * Pure transformation of a run's event stream (docs/CONTRACTS.md, C-2) into a span tree
 * plus a run-level summary. Never throws: unknown parents become orphan roots, and
 * malformed timestamps simply produce no duration.
 */

export type SpanState = "running" | "ok" | "error" | "cancelled";
export type RunState = "running" | "completed" | "error" | "cancelled" | "budget_exceeded" | "interrupted";

export interface SpanNode {
  id: string;
  parentId: string | null;
  kind: "agent" | "llm_call" | "tool_call";
  /** Human-friendly label (never empty). */
  label: string;
  /** Raw `name` from the event, if any. */
  name: string | null;
  status: SpanState;
  startedAt: string;
  endedAt: string | null;
  durationMs: number | null;
  startSeq: number;
  endSeq: number | null;
  /** `data` of span_started merged with `data` of span_ended (ended wins on conflicts). */
  data: Record<string, unknown>;
  children: SpanNode[];
  orphan?: boolean;
}

export interface RunTotals {
  llmCalls: number;
  toolCalls: number;
  inputTokens: number;
  outputTokens: number;
  costUsd: number | null;
}

export interface RunSummary {
  status: RunState;
  startedAt: string | null;
  endedAt: string | null;
  durationMs: number | null;
  finalOutput: string | null;
  error: string | null;
  totals: RunTotals;
  /** Count of spans (at any depth) that ended in `error`, for a "completed with N failed steps" hint. */
  failedSpans: number;
}

export interface SpanTree {
  roots: SpanNode[];
  run: RunSummary | null;
  spanCount: number;
}

const WELL_KNOWN_LLM_LABELS: Record<string, string> = {
  memory_extract: "Memory extraction",
  compaction: "Context compaction",
  trim_summary: "Context trimming",
  embed: "Embeddings",
};

const RUN_STATES: RunState[] = ["running", "completed", "error", "cancelled", "budget_exceeded", "interrupted"];

function asString(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function millisBetween(start: string | null | undefined, end: string | null | undefined): number | null {
  if (!start || !end) return null;
  const diff = Date.parse(end) - Date.parse(start);
  return Number.isFinite(diff) && diff >= 0 ? diff : null;
}

export function spanLabel(kind: SpanNode["kind"], name: string | null, data: Record<string, unknown>): string {
  if (kind === "llm_call") {
    if (name && WELL_KNOWN_LLM_LABELS[name]) return WELL_KNOWN_LLM_LABELS[name];
    return asString(data.model) ?? name ?? "Model call";
  }
  if (kind === "tool_call") return name ?? asString(data.tool_name) ?? "Tool call";
  return name ?? "Agent";
}

export function formatDuration(ms: number | null | undefined): string {
  if (ms == null) return "";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds < 10 ? seconds.toFixed(1) : Math.round(seconds)} s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${Math.round(seconds - minutes * 60)}s`;
}

export function formatCost(costUsd: number | null | undefined): string {
  if (costUsd == null) return "—";
  if (costUsd === 0) return "$0";
  return costUsd < 0.001 ? "<$0.001" : `$${costUsd.toFixed(costUsd < 1 ? 3 : 2)}`;
}

export function buildSpanTree(events: ExecutionEvent[]): SpanTree {
  const ordered = [...events].sort((a, b) => a.seq - b.seq);
  const nodes = new Map<string, SpanNode>();
  const roots: SpanNode[] = [];

  let started: ExecutionEvent | null = null;
  let ended: ExecutionEvent | null = null;

  for (const event of ordered) {
    if (event.type === "execution_started") {
      started = event;
      continue;
    }
    if (event.type === "execution_ended") {
      ended = event;
      continue;
    }

    if (event.type === "span_started" && event.span_id && event.kind) {
      if (nodes.has(event.span_id)) continue; // duplicate delivery (ws + polling): keep the first
      const data = { ...(event.data ?? {}) };
      const node: SpanNode = {
        id: event.span_id,
        parentId: event.parent_span_id ?? null,
        kind: event.kind,
        name: event.name ?? null,
        label: spanLabel(event.kind, event.name ?? null, data),
        status: "running",
        startedAt: event.ts,
        endedAt: null,
        durationMs: null,
        startSeq: event.seq,
        endSeq: null,
        data,
        children: [],
      };
      nodes.set(node.id, node);
      const parent = node.parentId ? nodes.get(node.parentId) : undefined;
      if (parent) {
        parent.children.push(node);
      } else {
        if (node.parentId) node.orphan = true;
        roots.push(node);
      }
      continue;
    }

    if (event.type === "span_ended" && event.span_id) {
      const node = nodes.get(event.span_id);
      if (!node) continue;
      node.status = event.status === "error" ? "error" : event.status === "cancelled" ? "cancelled" : "ok";
      node.endedAt = event.ts;
      node.endSeq = event.seq;
      node.durationMs = millisBetween(node.startedAt, event.ts);
      node.data = { ...node.data, ...(event.data ?? {}) };
      if (!node.name && event.name) {
        node.name = event.name;
      }
      node.label = spanLabel(node.kind, node.name, node.data);
    }
  }

  const spans = [...nodes.values()];
  const failedSpans = spans.filter((span) => span.status === "error").length;

  if (!started && !ended && spans.length === 0) {
    return { roots, run: null, spanCount: 0 };
  }

  // ---- run summary --------------------------------------------------------
  const endData = (ended?.data ?? {}) as Record<string, unknown>;
  const declared = asString(endData.status);
  let status: RunState;
  if (declared && (RUN_STATES as string[]).includes(declared)) {
    status = declared as RunState;
  } else if (ended) {
    // execution_ended without an explicit status: judge by the root agent span, not by any nested failure.
    const root = roots.find((span) => span.kind === "agent") ?? roots[0];
    status = root?.status === "error" ? "error" : root?.status === "cancelled" ? "cancelled" : "completed";
  } else {
    status = "running";
  }

  const sums = spans
    .filter((span) => span.kind === "llm_call")
    .reduce(
      (acc, span) => {
        const usage = (span.data.usage ?? {}) as Record<string, unknown>;
        acc.input += asNumber(usage.input_tokens) ?? 0;
        acc.output += asNumber(usage.output_tokens) ?? 0;
        const cost = asNumber(span.data.cost_usd);
        if (cost !== null) acc.cost = (acc.cost ?? 0) + cost;
        return acc;
      },
      { input: 0, output: 0, cost: null as number | null },
    );

  const declaredTotals = (endData.totals ?? null) as Record<string, unknown> | null;
  const totals: RunTotals = {
    llmCalls: asNumber(declaredTotals?.llm_calls) ?? spans.filter((span) => span.kind === "llm_call").length,
    toolCalls: asNumber(declaredTotals?.tool_calls) ?? spans.filter((span) => span.kind === "tool_call").length,
    inputTokens: asNumber(declaredTotals?.input_tokens) ?? sums.input,
    outputTokens: asNumber(declaredTotals?.output_tokens) ?? sums.output,
    costUsd: declaredTotals && "cost_usd" in declaredTotals ? asNumber(declaredTotals.cost_usd) : sums.cost,
  };

  const startedAt = started?.ts ?? ordered[0]?.ts ?? null;
  const endedAt = ended?.ts ?? null;

  return {
    roots,
    spanCount: spans.length,
    run: {
      status,
      startedAt,
      endedAt,
      durationMs: millisBetween(startedAt, endedAt),
      finalOutput: asString(endData.final_output),
      error: asString(endData.error),
      totals,
      failedSpans,
    },
  };
}
