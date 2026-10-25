import { useEffect, useMemo, useState } from "react";
import { api } from "../../api/client";
import type { ExecutionEvent } from "../../types";

type Decision = "allow_once" | "allow_run" | "deny";

export function ApprovalDialog({
  executionId,
  events,
}: { executionId: string | null; events: ExecutionEvent[] }) {
  const [busy, setBusy] = useState<Decision | null>(null);
  const [submitted, setSubmitted] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const pendingEvent = useMemo(() => {
    const resolved = new Set(
      events.filter((event) => event.type === "approval_resolved")
        .map((event) => event.data?.approval_id)
        .filter((id): id is string => typeof id === "string"),
    );
    return [...events].reverse().find((event) =>
      event.type === "approval_requested" &&
      typeof event.data?.approval_id === "string" &&
      !resolved.has(event.data.approval_id),
    ) ?? null;
  }, [events]);

  const data = pendingEvent?.data ?? {};
  const approvalId = typeof data.approval_id === "string" ? data.approval_id : null;
  const tool = typeof data.tool === "string" ? data.tool : pendingEvent?.name ?? "Tool";
  const toolKind = typeof data.tool_kind === "string" ? data.tool_kind : tool;
  const reason = typeof data.reason === "string" ? data.reason : "This action requires your approval.";
  const argsPreview = typeof data.args_preview === "string" ? data.args_preview : JSON.stringify(data.args_preview ?? {}, null, 2);
  const permissions = Array.isArray(data.permissions) ? data.permissions.filter((item): item is string => typeof item === "string") : [];

  useEffect(() => {
    setSubmitted(null);
    setBusy(null);
    setError(null);
  }, [approvalId]);

  if (!executionId || !approvalId || !pendingEvent || submitted === approvalId) return null;

  const decide = async (decision: Decision) => {
    if (busy) return;
    setBusy(decision);
    setError(null);
    try {
      await api.executions.resolveApproval(executionId, approvalId, decision);
      setSubmitted(approvalId);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not submit the approval decision.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
      <section role="alertdialog" aria-modal="true" aria-labelledby="approval-title" aria-describedby="approval-reason"
        className="w-full max-w-xl overflow-hidden rounded-panel border border-amber-500/30 bg-studio-900 text-studio-100 shadow-elevated">
        <header className="border-b border-line bg-studio-850 px-5 py-4">
          <p className="text-2xs font-mono uppercase tracking-widest text-amber-300">Approval required</p>
          <h2 id="approval-title" className="mt-1 text-base font-semibold">Allow this tool action?</h2>
          <p className="mt-1 text-xs text-studio-400">The run is paused until you choose an action.</p>
        </header>
        <div className="space-y-4 p-5">
          <div>
            <p className="text-sm font-semibold">{tool}</p>
            <p className="mt-0.5 text-2xs font-mono text-studio-400">Tool kind: {toolKind}</p>
          </div>
          <p id="approval-reason" className="text-sm leading-relaxed text-studio-300">{reason}</p>
          {toolKind === "python" && (
            <p role="note" className="rounded border border-amber-700/70 bg-amber-950/30 p-3 text-xs leading-relaxed text-amber-200">
              Python runs under your user account. CPU, time, memory and captured output are bounded, but file reads and network access are not fully sandboxed. Only approve code you trust.
            </p>
          )}
          <div>
            <p className="mb-1.5 text-2xs font-mono uppercase tracking-wider text-studio-500">Requested permissions</p>
            <div className="flex flex-wrap gap-1.5">
              {permissions.length ? permissions.map((permission) => (
                <span key={permission} className="rounded border border-line-strong bg-studio-950 px-2 py-1 text-2xs font-mono">{permission}</span>
              )) : <span className="text-xs text-studio-400">No explicit permissions listed</span>}
            </div>
          </div>
          <div>
            <p className="mb-1.5 text-2xs font-mono uppercase tracking-wider text-studio-500">Arguments preview</p>
            <pre className="max-h-44 overflow-auto whitespace-pre-wrap break-words rounded border border-line bg-studio-950 p-3 text-2xs font-mono text-studio-200">{argsPreview}</pre>
          </div>
          {error && <p role="alert" className="rounded border border-red-800 bg-red-950/50 p-2 text-xs text-red-300">{error}</p>}
        </div>
        <footer className="flex flex-wrap items-center justify-end gap-2 border-t border-line bg-studio-950/50 px-5 py-4">
          <button type="button" onClick={() => void decide("deny")} disabled={!!busy}
            className="rounded border border-red-800 px-3 py-2 text-xs font-semibold text-red-300 hover:bg-red-950/60 disabled:opacity-50">
            {busy === "deny" ? "Denying…" : "Deny"}
          </button>
          <button type="button" onClick={() => void decide("allow_once")} disabled={!!busy}
            className="rounded border border-studio-600 px-3 py-2 text-xs font-semibold text-studio-200 hover:bg-studio-800 disabled:opacity-50">
            {busy === "allow_once" ? "Sending…" : "Allow once"}
          </button>
          <button type="button" onClick={() => void decide("allow_run")} disabled={!!busy}
            className="rounded bg-accent-600 px-3 py-2 text-xs font-semibold text-white hover:bg-accent-500 disabled:opacity-50">
            {busy === "allow_run" ? "Sending…" : "Allow for this run"}
          </button>
        </footer>
      </section>
    </div>
  );
}
