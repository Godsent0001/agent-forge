import { useEffect, useMemo, useState } from "react";
import type { KeyboardEvent } from "react";
import { useExecutionStream } from "../hooks/useExecutionStream";
import { api } from "../api/client";
import { buildSpanTree, formatCost, formatDuration } from "../lib/buildSpanTree";
import type { RunState, SpanNode } from "../lib/buildSpanTree";
import type { ExecutionEvent } from "../types";
import { useStore } from "../store/useStore";
import { Button } from "./ui/Button";
import { Icon } from "./ui/Icon";
import { SegmentedControl } from "./ui/SegmentedControl";
import { StatusBadge } from "./ui/StatusBadge";

interface ExecutionTreeProps {
  executionId: string | null;
  onSelectExecution: (executionId: string) => void;
  onSelectStep?: (spanId: string) => void;
}

function runBadge(status: RunState): { status: string; label: string } {
  switch (status) {
    case "running":
      return { status: "running", label: "Running" };
    case "completed":
      return { status: "completed", label: "Completed" };
    case "cancelled":
      return { status: "cancelled", label: "Cancelled" };
    case "budget_exceeded":
      return { status: "error", label: "Budget exceeded" };
    case "interrupted":
      return { status: "cancelled", label: "Interrupted" };
    default:
      return { status: "error", label: "Failed" };
  }
}

function asText(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function downloadJson(filename: string, payload: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function copyToClipboard(text: string) {
  try {
    void navigator.clipboard?.writeText(text);
  } catch {
    /* clipboard can be unavailable (permissions / insecure context); copying is best-effort */
  }
}

function SpanDot({ status }: { status: SpanNode["status"] }) {
  const tone =
    status === "error"
      ? "bg-red-400"
      : status === "ok"
        ? "bg-emerald-400"
        : status === "cancelled"
          ? "bg-studio-500"
          : "bg-amber-400 animate-pulse";
  return <span aria-hidden="true" className={`h-1.5 w-1.5 shrink-0 rounded-full ${tone}`} />;
}

function KindGlyph({ kind }: { kind: SpanNode["kind"] }) {
  if (kind === "agent") return <Icon name="agents" size={13} className="shrink-0 text-accent-400" />;
  if (kind === "tool_call") return <Icon name="tools" size={13} className="shrink-0 text-emerald-400" />;
  return (
    <span className="shrink-0 rounded border border-studio-700 px-1 text-[9px] font-mono leading-4 text-studio-400">LLM</span>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  if (!value) return null;
  return (
    <div className="space-y-1">
      <div className="text-2xs font-mono uppercase tracking-wider text-studio-500">{label}</div>
      <pre className="max-h-32 overflow-auto whitespace-pre-wrap break-words rounded border border-studio-800 bg-studio-950 p-2 text-2xs font-mono leading-relaxed text-studio-200">
        {value}
      </pre>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-[10px] font-mono uppercase tracking-wider text-studio-500">{label}</dt>
      <dd className="truncate font-mono text-xs tabular-nums text-studio-100">{value}</dd>
    </div>
  );
}

function SpanDetails({ span }: { span: SpanNode }) {
  const [copied, setCopied] = useState(false);
  const data = span.data;
  const usage = (data.usage ?? {}) as Record<string, unknown>;
  const toolCalls = Array.isArray(data.tool_calls) ? (data.tool_calls as unknown[]).map(String) : [];
  const artifacts = Array.isArray(data.artifacts) ? (data.artifacts as unknown[]).map(String) : [];
  const raw = JSON.stringify(span, (key, value) => (key === "children" ? undefined : value), 2);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <KindGlyph kind={span.kind} />
        <span className="min-w-0 flex-1 truncate text-xs font-semibold text-studio-100">{span.label}</span>
        <span className="text-2xs font-mono text-studio-500">{formatDuration(span.durationMs)}</span>
      </div>

      {span.kind === "tool_call" && <Field label="Arguments" value={asText(data.args)} />}
      {span.kind === "agent" && <Field label="Input" value={asText(data.input_preview)} />}
      {span.kind === "llm_call" && (
        <dl className="grid grid-cols-2 gap-2">
          <Stat label="Model" value={asText(data.model) || "—"} />
          <Stat label="Finish" value={asText(data.finish_reason) || "—"} />
          <Stat
            label="Tokens in → out"
            value={`${Number(usage.input_tokens ?? 0).toLocaleString()} → ${Number(usage.output_tokens ?? 0).toLocaleString()}`}
          />
          <Stat label="Cost" value={formatCost(typeof data.cost_usd === "number" ? data.cost_usd : null)} />
        </dl>
      )}
      {toolCalls.length > 0 && <Field label="Requested tools" value={toolCalls.join(", ")} />}

      <Field label="Output" value={asText(data.result_preview ?? data.output_preview)} />
      {artifacts.length > 0 && <Field label="Files produced" value={artifacts.join("\n")} />}
      {span.status === "error" && !asText(data.result_preview ?? data.output_preview) && (
        <p className="rounded border border-red-900/60 bg-red-950/40 px-2 py-1.5 text-2xs text-red-300">
          This step failed and returned no message.
        </p>
      )}

      <details className="group">
        <summary className="cursor-pointer select-none text-2xs font-mono uppercase tracking-wider text-studio-500 hover:text-studio-300">
          Raw span
        </summary>
        <div className="mt-1.5 flex justify-end">
          <button
            type="button"
            onClick={() => {
              copyToClipboard(raw);
              setCopied(true);
              setTimeout(() => setCopied(false), 1500);
            }}
            className="rounded px-1.5 py-0.5 text-2xs font-mono text-studio-400 hover:bg-studio-800 hover:text-white"
          >
            {copied ? "Copied" : "Copy JSON"}
          </button>
        </div>
        <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap break-all rounded border border-studio-800 bg-studio-950 p-2 text-2xs font-mono text-studio-300">
          {raw}
        </pre>
      </details>
    </div>
  );
}

function TraceNode({
  node,
  depth,
  selectedId,
  collapsed,
  onSelect,
  onToggle,
}: {
  node: SpanNode;
  depth: number;
  selectedId: string | null;
  collapsed: Set<string>;
  onSelect: (id: string) => void;
  onToggle: (id: string) => void;
}) {
  const hasChildren = node.children.length > 0;
  const isCollapsed = collapsed.has(node.id);
  const isSelected = selectedId === node.id;

  const handleKey = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onSelect(node.id);
    } else if (event.key === "ArrowRight" && hasChildren && isCollapsed) {
      event.preventDefault();
      onToggle(node.id);
    } else if (event.key === "ArrowLeft" && hasChildren && !isCollapsed) {
      event.preventDefault();
      onToggle(node.id);
    }
  };

  return (
    <div role="none">
      <div
        role="treeitem"
        tabIndex={0}
        aria-level={depth + 1}
        aria-selected={isSelected}
        aria-expanded={hasChildren ? !isCollapsed : undefined}
        onClick={() => onSelect(node.id)}
        onKeyDown={handleKey}
        className={`group flex cursor-pointer items-center gap-1.5 rounded px-1.5 py-1 text-xs transition-colors ${
          isSelected ? "bg-studio-800 ring-1 ring-accent-500/60" : "hover:bg-studio-850"
        }`}
      >
        {hasChildren ? (
          <button
            type="button"
            tabIndex={-1}
            aria-label={isCollapsed ? `Expand ${node.label}` : `Collapse ${node.label}`}
            onClick={(event) => {
              event.stopPropagation();
              onToggle(node.id);
            }}
            className="flex h-4 w-4 shrink-0 items-center justify-center rounded text-studio-500 hover:bg-studio-700 hover:text-studio-100"
          >
            <Icon name="chevron-right" size={12} className={`transition-transform ${isCollapsed ? "" : "rotate-90"}`} />
          </button>
        ) : (
          <span className="h-4 w-4 shrink-0" />
        )}
        <KindGlyph kind={node.kind} />
        <span className={`min-w-0 flex-1 truncate ${node.status === "error" ? "text-red-300" : "text-studio-100"}`}>
          {node.label}
        </span>
        {node.orphan && <span className="text-[9px] font-mono uppercase text-amber-400">orphan</span>}
        <SpanDot status={node.status} />
        <span className="w-14 shrink-0 text-right text-2xs font-mono tabular-nums text-studio-500">
          {node.status === "running" ? "…" : formatDuration(node.durationMs)}
        </span>
      </div>

      {hasChildren && !isCollapsed && (
        <div role="group" className="ml-[15px] border-l border-studio-800 pl-1.5">
          {node.children.map((child) => (
            <TraceNode
              key={child.id}
              node={child}
              depth={depth + 1}
              selectedId={selectedId}
              collapsed={collapsed}
              onSelect={onSelect}
              onToggle={onToggle}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function eventTitle(event: ExecutionEvent): string {
  const type = event.type.replace(/_/g, " ");
  return event.name ? `${type} · ${event.name}` : type;
}

export function ExecutionTree({ executionId, onSelectExecution }: ExecutionTreeProps) {
  const projectId = useStore((s) => s.project?.id ?? null);
  const [recentRuns, setRecentRuns] = useState<import("../api/client").ExecutionSummary[]>([]);
  const [runsError, setRunsError] = useState<string | null>(null);
  const { events } = useExecutionStream(executionId);

  useEffect(() => {
    if (!projectId) {
      setRecentRuns([]);
      return;
    }
    let cancelled = false;
    void api.executions.list(projectId, 10).then((runs) => {
      if (!cancelled) {
        setRecentRuns(runs);
        setRunsError(null);
      }
    }).catch((error) => {
      if (!cancelled) {
        setRunsError(error instanceof Error ? error.message : "Could not load recent runs.");
      }
    });
    return () => { cancelled = true; };
  }, [projectId, executionId]);
  const { roots, run, spanCount } = useMemo(() => buildSpanTree(events), [events]);

  const [view, setView] = useState<"trace" | "events">("trace");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedSeq, setSelectedSeq] = useState<number | null>(null);
  const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set());
  const [isCancelling, setIsCancelling] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setSelectedId(null);
    setSelectedSeq(null);
    setCollapsed(new Set());
    setCancelError(null);
  }, [executionId]);

  const allSpans = useMemo(() => {
    const out = new Map<string, SpanNode>();
    const visit = (node: SpanNode) => {
      out.set(node.id, node);
      node.children.forEach(visit);
    };
    roots.forEach(visit);
    return out;
  }, [roots]);

  if (!executionId) {
    return (
      <div className="flex h-full select-none flex-col items-center justify-center gap-3 overflow-y-auto bg-studio-900 p-4 text-center text-xs">
        <div className="flex h-10 w-10 items-center justify-center rounded-full border border-studio-700 bg-studio-800 text-studio-400">
          <Icon name="logs" size={18} />
        </div>
        <div>
          <h3 className="mb-1 font-semibold text-studio-200">No run selected</h3>
          <p className="max-w-xs text-2xs leading-relaxed text-studio-500">
            Send a task from Chat, or choose a previous run below to reopen its trace.
          </p>
        </div>
        {runsError && <p role="alert" className="text-2xs text-red-300">{runsError}</p>}
        {recentRuns.length > 0 && (
          <div className="w-full max-w-sm space-y-1 text-left">
            <p className="px-1 text-2xs font-mono uppercase tracking-wider text-studio-500">Recent runs</p>
            {recentRuns.map((item) => (
              <button key={item.id} type="button" onClick={() => onSelectExecution(item.id)}
                className="w-full rounded border border-studio-800 bg-studio-950/60 px-2 py-2 text-left hover:bg-studio-850">
                <span className="block truncate text-xs text-studio-200">{item.task_preview || "Untitled run"}</span>
                <span className="mt-1 block text-2xs font-mono text-studio-500">
                  {item.status} · {new Date(item.started_at).toLocaleString()}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>
    );
  }

  const isRunning = !run || run.status === "running";
  const badge = run ? runBadge(run.status) : { status: "running", label: "Starting" };
  const selectedSpan = selectedId ? allSpans.get(selectedId) ?? null : null;
  const selectedEvent = selectedSeq != null ? events.find((e) => e.seq === selectedSeq) ?? null : null;

  const toggle = (id: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const handleCancelRun = async () => {
    if (isCancelling) return;
    setIsCancelling(true);
    setCancelError(null);
    try {
      await api.executions.cancel(executionId);
    } catch (err) {
      setCancelError(err instanceof Error ? err.message : "Could not cancel the run.");
    } finally {
      setIsCancelling(false);
    }
  };

  const totals = run?.totals;
  const tokenText = totals ? `${totals.inputTokens.toLocaleString()} → ${totals.outputTokens.toLocaleString()}` : "—";

  return (
    <div className="flex h-full min-w-0 select-none flex-col overflow-hidden bg-studio-900 text-xs">
      {/* Header */}
      <div className="flex shrink-0 items-center justify-between gap-2 border-b border-studio-800 bg-studio-850 p-3">
        <div className="flex min-w-0 items-center gap-2">
          <span className="shrink-0 font-semibold text-studio-100">
            Run <span className="font-mono text-studio-400">#{executionId.slice(0, 8)}</span>
          </span>
          <StatusBadge status={badge.status} label={badge.label} />
          {recentRuns.length > 0 && (
            <select
              aria-label="Open a recent run"
              value={executionId}
              onChange={(event) => onSelectExecution(event.target.value)}
              className="min-w-0 max-w-40 truncate rounded border border-studio-700 bg-studio-950 px-1.5 py-1 text-2xs text-studio-300"
            >
              {!recentRuns.some((item) => item.id === executionId) && <option value={executionId}>Current run</option>}
              {recentRuns.map((item) => (
                <option key={item.id} value={item.id}>
                  {(item.task_preview || "Untitled run").slice(0, 48)}
                </option>
              ))}
            </select>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {events.length > 0 && (
            <button
              type="button"
              onClick={() => downloadJson(`agentforge-run-${executionId.slice(0, 8)}.json`, { execution_id: executionId, run, events })}
              className="rounded px-2 py-1 text-2xs font-mono text-studio-400 transition-colors hover:bg-studio-800 hover:text-studio-100"
              title="Download this run's full event log as JSON"
            >
              Export log
            </button>
          )}
          {isRunning && (
            <Button size="xs" variant="danger" onClick={handleCancelRun} disabled={isCancelling || !run}>
              {isCancelling ? "Cancelling…" : "Cancel run"}
            </Button>
          )}
        </div>
      </div>

      {cancelError && (
        <div role="alert" className="shrink-0 border-b border-red-900/60 bg-red-950/40 px-3 py-1.5 text-2xs text-red-300">
          {cancelError}
        </div>
      )}

      {/* Run summary */}
      {run && (
        <dl className="grid shrink-0 grid-cols-4 gap-2 border-b border-studio-800 px-3 py-2">
          <Stat label="Time" value={run.durationMs != null ? formatDuration(run.durationMs) : isRunning ? "live" : "—"} />
          <Stat label="Tokens" value={tokenText} />
          <Stat label="Cost" value={formatCost(totals?.costUsd)} />
          <Stat label="LLM / Tool" value={`${totals?.llmCalls ?? 0} / ${totals?.toolCalls ?? 0}`} />
        </dl>
      )}

      {run && run.status === "completed" && run.failedSpans > 0 && (
        <div className="shrink-0 border-b border-amber-900/50 bg-amber-950/30 px-3 py-1.5 text-2xs text-amber-300">
          Finished, but {run.failedSpans} step{run.failedSpans === 1 ? "" : "s"} failed along the way. Select a red step to see why.
        </div>
      )}
      {run?.error && (
        <div role="alert" className="shrink-0 border-b border-red-900/60 bg-red-950/40 px-3 py-1.5 text-2xs text-red-300">
          {run.error}
        </div>
      )}
      {(() => {
        const pending = new Map<string, ExecutionEvent>();
        for (const event of events) {
          const approvalId = String(event.data?.approval_id ?? event.data?.approvalId ?? event.seq);
          if (event.type === "approval_requested") pending.set(approvalId, event);
          if (event.type === "approval_resolved") pending.delete(approvalId);
        }
        const pendingRequests = [...pending.values()];
        const request = pendingRequests[pendingRequests.length - 1];
        if (!request) return null;
        const toolName = String(request.data?.tool ?? request.data?.tool_name ?? request.name ?? "requested tool");
        return (
          <div role="status" aria-live="polite" className="shrink-0 border-b border-amber-800/70 bg-amber-950/40 px-3 py-2 text-2xs text-amber-200">
            <strong>Waiting for approval</strong> · {toolName}
            <p className="mt-0.5 text-amber-300/80">This run is paused until the approval controls resolve this request.</p>
          </div>
        );
      })()}

      {/* View switch */}
      <div className="shrink-0 border-b border-studio-800 bg-studio-950/70 p-1.5">
        <SegmentedControl
          size="sm"
          value={view}
          onChange={setView}
          options={[
            { value: "trace", label: "Trace", badge: spanCount },
            { value: "events", label: "Events", badge: events.length },
          ]}
        />
      </div>

      {/* List */}
      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        {events.length === 0 ? (
          <div className="flex items-center gap-2 px-1 py-4 text-studio-400" role="status" aria-live="polite">
            <span className="h-2 w-2 animate-pulse rounded-full bg-amber-300" /> Waiting for the run to start…
          </div>
        ) : view === "trace" ? (
          roots.length === 0 ? (
            <p className="px-1 py-4 text-studio-500">No steps recorded yet.</p>
          ) : (
            <div role="tree" aria-label="Run trace" className="space-y-0.5">
              {roots.map((node) => (
                <TraceNode
                  key={node.id}
                  node={node}
                  depth={0}
                  selectedId={selectedId}
                  collapsed={collapsed}
                  onSelect={setSelectedId}
                  onToggle={toggle}
                />
              ))}
            </div>
          )
        ) : (
          <ul className="space-y-1">
            {events.map((evt) => (
              <li key={evt.seq}>
                <button
                  type="button"
                  onClick={() => setSelectedSeq(evt.seq)}
                  className={`flex w-full items-center justify-between gap-2 rounded border px-2 py-1.5 text-left transition-colors ${
                    selectedSeq === evt.seq
                      ? "border-accent-500 bg-studio-800"
                      : "border-studio-800/80 bg-studio-950/60 hover:bg-studio-850"
                  }`}
                >
                  <span className="min-w-0 truncate font-mono text-2xs capitalize text-studio-200">{eventTitle(evt)}</span>
                  <span className="shrink-0 font-mono text-2xs tabular-nums text-studio-500">#{evt.seq}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Inspector */}
      <div className="h-60 shrink-0 select-text overflow-y-auto border-t border-studio-800 bg-studio-950 p-3">
        {view === "events" && selectedEvent ? (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-2xs font-mono font-semibold uppercase text-studio-400">Event #{selectedEvent.seq}</span>
              <button
                type="button"
                onClick={() => {
                  copyToClipboard(JSON.stringify(selectedEvent, null, 2));
                  setCopied(true);
                  setTimeout(() => setCopied(false), 1500);
                }}
                className="rounded px-1.5 py-0.5 text-2xs font-mono text-studio-400 hover:bg-studio-800 hover:text-white"
              >
                {copied ? "Copied" : "Copy JSON"}
              </button>
            </div>
            <pre className="whitespace-pre-wrap break-all rounded border border-studio-800 bg-studio-900 p-2 text-2xs font-mono text-studio-300">
              {JSON.stringify(selectedEvent, null, 2)}
            </pre>
          </div>
        ) : view === "trace" && selectedSpan ? (
          <SpanDetails span={selectedSpan} />
        ) : run && run.finalOutput ? (
          <Field label="Final output" value={run.finalOutput} />
        ) : (
          <p className="text-2xs leading-relaxed text-studio-500">
            {view === "trace"
              ? "Select a step to inspect its input, output, tokens and cost."
              : "Select an event to view its raw payload."}
          </p>
        )}
      </div>
    </div>
  );
}
