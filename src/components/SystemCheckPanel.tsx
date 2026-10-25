import { useCallback, useEffect, useState } from "react";
import { api, type SystemCheck } from "../api/client";
import { Button } from "./ui/Button";

export function SystemCheckPanel() {
  const [checks, setChecks] = useState<SystemCheck[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setChecks(await api.system.check());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load system checks.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const failed = checks.filter((check) => !check.ok).length;
  return (
    <section aria-labelledby="system-check-title" className="space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 id="system-check-title" className="font-semibold text-studio-100">Runtime readiness</h3>
          <p className="mt-1 text-2xs text-studio-400">
            Checks run on this device. Optional dependencies may be missing until you use their tools.
          </p>
        </div>
        <Button size="xs" variant="outline" onClick={() => void refresh()} disabled={loading}>
          {loading ? "Checking…" : "Refresh"}
        </Button>
      </div>

      {error && <p role="alert" className="rounded border border-red-800 bg-red-950/40 p-3 text-2xs text-red-200">{error}</p>}
      {!loading && !error && (
        <p role="status" className={`rounded border p-3 text-2xs ${failed ? "border-amber-800 bg-amber-950/30 text-amber-200" : "border-emerald-800 bg-emerald-950/30 text-emerald-200"}`}>
          {failed ? `${failed} check(s) need attention. See each fix below.` : "All reported system checks passed."}
        </p>
      )}

      <div className="divide-y divide-line rounded-lg border border-line">
        {loading && checks.length === 0 && <p className="p-3 text-2xs text-studio-400">Checking local dependencies, storage, and provider configuration…</p>}
        {checks.map((check) => (
          <div key={check.name} className="flex items-start gap-3 p-3">
            <span aria-label={check.ok ? "Passed" : "Needs attention"} className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-2xs ${check.ok ? "bg-emerald-950 text-emerald-300" : "bg-amber-950 text-amber-300"}`}>
              {check.ok ? "✓" : "!"}
            </span>
            <div className="min-w-0 flex-1">
              <p className="break-words font-mono text-2xs text-studio-200">{check.name}</p>
              <p className="mt-1 text-2xs text-studio-400">{check.detail}</p>
              {!check.ok && check.fix && <p className="mt-1 text-2xs text-amber-200">{check.fix}</p>}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
