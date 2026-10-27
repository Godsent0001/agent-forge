import { useEffect, useState } from "react";
import { useStore } from "../store/useStore";
import { Button } from "./ui/Button";

type Policy = "ask" | "allow" | "deny";
const POLICY_DEFAULTS: Record<string, Policy> = {
  python: "allow",
  shell: "allow",
  browser: "allow",
  http_request: "allow",
  web_search: "allow",
  file_system: "allow",
  scene_template_manager: "allow",
  render_queue: "allow",
  project_manager: "allow",
  asset_cache_store: "allow",
  production_config: "allow",
  cache_engine: "allow",
};

export function ProjectSettings({ onClose }: { onClose: () => void }) {
  const project = useStore((state) => state.project);
  const updateProjectSettings = useStore((state) => state.updateProjectSettings);
  const [parallelTools, setParallelTools] = useState(false);
  const [maxCostUsd, setMaxCostUsd] = useState("0.50");
  const [maxLlmCalls, setMaxLlmCalls] = useState("30");
  const [maxSeconds, setMaxSeconds] = useState("300");
  const [policy, setPolicy] = useState<Record<string, Policy>>(POLICY_DEFAULTS);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    const settings = project?.settings ?? {};
    const budget = (settings.budget && typeof settings.budget === "object" ? settings.budget : {}) as Record<string, unknown>;
    const configuredPolicy = (settings.tool_policy && typeof settings.tool_policy === "object" ? settings.tool_policy : {}) as Record<string, unknown>;
    setParallelTools(project?.parallel_execution === true);
    setMaxCostUsd(typeof budget.max_cost_usd === "number" ? String(budget.max_cost_usd) : budget.max_cost_usd === null ? "" : "0.50");
    setMaxLlmCalls(typeof budget.max_llm_calls === "number" ? String(budget.max_llm_calls) : "30");
    setMaxSeconds(typeof budget.max_seconds === "number" ? String(budget.max_seconds) : "300");
    setPolicy(Object.fromEntries(
      Object.entries(POLICY_DEFAULTS).map(([kind, fallback]) => {
        const value = configuredPolicy[kind];
        return [kind, value === "allow" || value === "ask" || value === "deny" ? value : fallback];
      }),
    ) as Record<string, Policy>);
  }, [project?.id, project?.settings]);

  const save = async () => {
    if (!project || saving) return;
    const cost = maxCostUsd.trim() === "" ? null : Number(maxCostUsd);
    const calls = Number(maxLlmCalls);
    const seconds = Number(maxSeconds);
    if ((cost !== null && (!Number.isFinite(cost) || cost < 0 || cost > 1_000_000)) || !Number.isInteger(calls) || calls < 1 || calls > 10_000 || !Number.isInteger(seconds) || seconds < 1 || seconds > 86_400) {
      setError("Cost must be between 0 and 1,000,000 USD; LLM calls must be 1–10,000; seconds must be 1–86,400.");
      return;
    }
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const previous = project.settings ?? {};
      const previousBudget = previous.budget && typeof previous.budget === "object" ? previous.budget as Record<string, unknown> : {};
      await updateProjectSettings({ parallel_execution: parallelTools, settings: {
        ...previous,
        parallel_tools: parallelTools,
        budget: { ...previousBudget, max_cost_usd: cost, max_llm_calls: calls, max_seconds: seconds },
        tool_policy: policy,
      } });
      setNotice("Project settings saved. They apply to new runs.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not save project settings.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/70 p-4" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section role="dialog" aria-modal="true" aria-labelledby="project-settings-title" className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-panel bg-studio-900 text-studio-100 shadow-elevated">
        <header className="flex items-start justify-between gap-4 border-b border-line bg-studio-850 px-5 py-4">
          <div><h2 id="project-settings-title" className="text-sm font-semibold">Project execution settings</h2><p className="mt-1 text-xs text-studio-400">Policies and budgets are enforced by the runtime, not just the UI.</p></div>
          <button type="button" onClick={onClose} aria-label="Close project settings" className="rounded px-2 py-1 text-studio-400 hover:bg-studio-800 hover:text-studio-100">✕</button>
        </header>
        <div className="space-y-6 p-5">
          <label className="flex items-start justify-between gap-4 rounded-lg bg-studio-950/50 neu-inset p-3">
            <span><span className="block text-xs font-semibold">Parallel tool calls</span><span className="mt-1 block text-2xs text-studio-400">Allow multiple tool calls from one model turn to execute concurrently.</span></span>
            <input aria-label="Parallel tool calls" type="checkbox" checked={parallelTools} onChange={(event) => setParallelTools(event.target.checked)} className="mt-1 h-4 w-4 accent-indigo-500" />
          </label>
          <div>
            <h3 className="mb-3 text-2xs font-mono uppercase tracking-wider text-studio-400">Run budgets</h3>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <label className="text-xs text-studio-300">Maximum cost (USD)<input value={maxCostUsd} onChange={(event) => setMaxCostUsd(event.target.value)} inputMode="decimal" placeholder="Blank = no cap" className="mt-1 w-full rounded border border-line-strong bg-studio-950 px-2.5 py-2 text-xs text-studio-100" /></label>
              <label className="text-xs text-studio-300">Maximum LLM calls<input value={maxLlmCalls} onChange={(event) => setMaxLlmCalls(event.target.value)} inputMode="numeric" className="mt-1 w-full rounded border border-line-strong bg-studio-950 px-2.5 py-2 text-xs text-studio-100" /></label>
              <label className="text-xs text-studio-300">Maximum seconds<input value={maxSeconds} onChange={(event) => setMaxSeconds(event.target.value)} inputMode="numeric" className="mt-1 w-full rounded border border-line-strong bg-studio-950 px-2.5 py-2 text-xs text-studio-100" /></label>
            </div>
          </div>
          <div>
            <h3 className="mb-2 text-2xs font-mono uppercase tracking-wider text-studio-400">Tool policy</h3>
            <p className="mb-3 text-2xs text-studio-500">Known tools default to Allow; unrecognized tool types default to Ask. Change any listed tool to “Ask” to approve each call, or “Deny” to block it. “Allow” runs without an approval prompt.</p>
            <div className="divide-y divide-line rounded border border-line">
              {Object.keys(POLICY_DEFAULTS).map((kind) => (
                <label key={kind} className="flex items-center justify-between gap-3 px-3 py-2.5">
                  <span className="text-xs font-mono">{kind}</span>
                  <select aria-label={`Policy for ${kind}`} value={policy[kind]} onChange={(event) => setPolicy((current) => ({ ...current, [kind]: event.target.value as Policy }))} className="rounded border border-line-strong bg-studio-950 px-2 py-1.5 text-xs">
                    <option value="ask">Ask</option><option value="allow">Allow</option><option value="deny">Deny</option>
                  </select>
                </label>
              ))}
            </div>
          </div>
          {error && <p role="alert" className="rounded border border-red-800 bg-red-950/50 p-2.5 text-xs text-red-300">{error}</p>}
          {notice && <p role="status" className="rounded border border-line-strong bg-studio-950 p-2.5 text-xs text-studio-300">{notice}</p>}
        </div>
        <footer className="flex justify-end gap-2 border-t border-line px-5 py-4">
          <Button variant="secondary" size="sm" onClick={onClose}>Close</Button>
          <Button variant="primary" size="sm" onClick={() => void save()} disabled={saving || !project}>{saving ? "Saving…" : "Save settings"}</Button>
        </footer>
      </section>
    </div>
  );
}
