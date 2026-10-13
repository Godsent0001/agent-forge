import { useCallback, useEffect, useState } from "react";
import { api, type UsageBucket, type UsageReport } from "../api/client";
import { Button } from "./ui/Button";

function cost(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value)
    ? new Intl.NumberFormat(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 4 }).format(value)
    : "n/a";
}

function Stat({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="min-w-0 rounded border border-studio-800 bg-studio-950/60 p-3">
      <p className="text-2xs text-studio-400">{label}</p>
      <p className="mt-1 break-words text-lg font-semibold tabular-nums text-studio-100">{value}</p>
      {detail && <p className="mt-1 text-2xs text-studio-500">{detail}</p>}
    </div>
  );
}

function BucketList({ title, items, labelKey }: {
  title: string;
  items: UsageBucket[];
  labelKey: "date" | "agent_name" | "model";
}) {
  const maxRuns = Math.max(1, ...items.map((item) => item.runs));
  return (
    <section className="space-y-2">
      <h3 className="text-xs font-semibold text-studio-200">{title}</h3>
      {items.length === 0 ? (
        <p className="rounded border border-dashed border-studio-800 p-3 text-2xs text-studio-500">No runs in this period.</p>
      ) : (
        <div className="space-y-2">
          {items.map((item, index) => {
            const label = item[labelKey] || (labelKey === "date" ? "Unknown date" : labelKey === "model" ? "Unknown model" : "Unknown agent");
            return (
              <div key={`${label}-${index}`} className="rounded border border-studio-800 bg-studio-950/40 p-2.5">
                <div className="flex items-start justify-between gap-3">
                  <span className="break-all text-2xs text-studio-200">{label}</span>
                  <span className="shrink-0 font-mono text-2xs tabular-nums text-studio-300">{item.runs} runs · {cost(item.cost_usd)}</span>
                </div>
                <div className="mt-2 h-1.5 overflow-hidden rounded bg-studio-800" role="img" aria-label={`${item.runs} runs`}>
                  <div className="h-full rounded bg-accent-500" style={{ width: `${Math.max(3, (item.runs / maxRuns) * 100)}%` }} />
                </div>
                <p className="mt-1 text-2xs text-studio-500">{item.llm_calls} LLM calls · {item.tool_calls} tool calls · {(item.input_tokens + item.output_tokens).toLocaleString()} tokens</p>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

export function UsagePanel({ projectId }: { projectId: string | undefined }) {
  const [days, setDays] = useState(7);
  const [report, setReport] = useState<UsageReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!projectId) {
      setReport(null);
      setLoading(false);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setReport(await api.usage.get(projectId, days));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load project usage.");
    } finally {
      setLoading(false);
    }
  }, [projectId, days]);

  useEffect(() => { void refresh(); }, [refresh]);

  if (!projectId) return <p className="text-2xs text-studio-400">Select a project to view its usage.</p>;

  return (
    <section aria-labelledby="usage-title" className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 id="usage-title" className="font-semibold text-studio-100">Usage and cost</h3>
          <p className="mt-1 text-2xs text-studio-400">Totals come from saved execution records. Unknown provider pricing is shown as n/a, never as zero.</p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <label className="sr-only" htmlFor="usage-period">Reporting period</label>
          <select id="usage-period" aria-label="Reporting period" value={days} onChange={(event) => setDays(Number(event.target.value))} className="rounded border border-studio-700 bg-studio-950 px-2 py-1.5 text-2xs text-studio-100">
            <option value={7}>7 days</option>
            <option value={14}>14 days</option>
            <option value={30}>30 days</option>
            <option value={90}>90 days</option>
          </select>
          <Button size="xs" variant="outline" disabled={loading} onClick={() => void refresh()}>{loading ? "Loading…" : "Refresh"}</Button>
        </div>
      </div>

      {error && <p role="alert" className="rounded border border-red-800 bg-red-950/40 p-3 text-2xs text-red-200">{error}</p>}
      {loading && !report && <p role="status" className="text-2xs text-studio-400">Aggregating recent executions…</p>}
      {report && (
        <>
          <div className="grid grid-cols-2 gap-2">
            <Stat label="Known total cost" value={cost(report.totals.cost_usd)} detail={`${report.totals.runs} runs · ${report.totals.completed_runs} completed`} />
            <Stat label="LLM calls" value={report.totals.llm_calls.toLocaleString()} detail={`${report.totals.tool_calls.toLocaleString()} tool calls`} />
            <Stat label="Input tokens" value={report.totals.input_tokens.toLocaleString()} />
            <Stat label="Output tokens" value={report.totals.output_tokens.toLocaleString()} detail={`${report.totals.failed_runs} failed/cancelled runs`} />
          </div>
          {report.totals.cost_usd === null && (
            <p role="note" className="rounded border border-amber-800 bg-amber-950/30 p-3 text-2xs text-amber-200">
              At least one execution has unknown pricing, so the combined cost is not presented as a misleading partial total. Per-model and per-agent totals preserve the same rule.
            </p>
          )}
          <BucketList title="Daily activity" items={report.by_day} labelKey="date" />
          <BucketList title="By agent" items={report.by_agent} labelKey="agent_name" />
          <BucketList title="By model" items={report.by_model} labelKey="model" />
        </>
      )}
    </section>
  );
}
