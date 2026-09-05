import { useEffect, useState } from "react";
import { keychain } from "../api/keychain";

const PROVIDERS = ["anthropic", "openai", "google"] as const;

import { useStore } from "../store/useStore";

export function SettingsModal({ onClose }: { onClose: () => void }) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState<Record<string, boolean>>({});

  const project = useStore((s) => s.project);
  const updateProjectSettings = useStore((s) => s.updateProjectSettings);

  const [projName, setProjName] = useState(project?.name ?? "");
  const [parallelExecution, setParallelExecution] = useState(project?.parallel_execution ?? false);
  const [projSaved, setProjSaved] = useState(false);

  useEffect(() => {
    (async () => {
      const entries = await Promise.all(
        PROVIDERS.map(async (p) => [p, (await keychain.get(p)) ?? ""] as const)
      );
      setValues(Object.fromEntries(entries));
    })();
  }, []);

  useEffect(() => {
    if (project) {
      setProjName(project.name);
      setParallelExecution(project.parallel_execution);
    }
  }, [project]);

  const handleSave = async (provider: string) => {
    await keychain.save(provider, values[provider] ?? "");
    setSaved((s) => ({ ...s, [provider]: true }));
    setTimeout(() => setSaved((s) => ({ ...s, [provider]: false })), 1500);
  };

  const handleSaveProjectSettings = async () => {
    if (!project) return;
    await updateProjectSettings({
      name: projName,
      parallel_execution: parallelExecution,
    });
    setProjSaved(true);
    setTimeout(() => setProjSaved(false), 1500);
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 animate-fade-in">
      <div className="bg-surface-900 border border-white/10 rounded-panel shadow-panel w-full max-w-lg p-6 space-y-6">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold">Settings</h2>
          <button onClick={onClose} className="text-neutral-500 hover:text-neutral-300 text-sm">
            ✕
          </button>
        </div>

        {/* Project General Settings Section */}
        {project && (
          <div className="border border-white/10 rounded-md p-4 space-y-3 bg-surface-950">
            <h3 className="text-sm font-medium text-neutral-200">Project General Settings ({project.name})</h3>
            <div className="space-y-2">
              <label className="block text-xs text-neutral-400">Project Name</label>
              <input
                type="text"
                value={projName}
                onChange={(e) => setProjName(e.target.value)}
                className="w-full bg-surface-800 border border-white/10 rounded-md px-2.5 py-1.5 text-sm text-white focus:outline-none focus:ring-1 focus:ring-accent-500"
              />
            </div>

            <div className="flex items-center justify-between pt-1">
              <div>
                <label className="text-xs font-medium text-neutral-300 block">Parallel Tool & Child Agent Execution</label>
                <span className="text-[11px] text-neutral-500 block">
                  When enabled, multiple tool or child agent calls run concurrently via asyncio.gather. Default is sequential.
                </span>
              </div>
              <input
                type="checkbox"
                checked={parallelExecution}
                onChange={(e) => setParallelExecution(e.target.checked)}
                className="w-4 h-4 accent-accent-500 cursor-pointer"
              />
            </div>

            <div className="pt-2 flex justify-end">
              <button
                onClick={handleSaveProjectSettings}
                className="text-xs px-3 py-1.5 rounded-md bg-accent-500 hover:bg-accent-400 transition-colors text-white"
              >
                {projSaved ? "✓ Saved" : "Save Project Settings"}
              </button>
            </div>
          </div>
        )}

        {/* API Keys Section */}
        <div className="space-y-3">
          <h3 className="text-sm font-medium text-neutral-200">Provider API Keys</h3>
          <p className="text-xs text-neutral-500">
            Stored in your OS keychain — never written to disk in plain text.
          </p>
          {PROVIDERS.map((provider) => (
            <div key={provider} className="flex items-center gap-2">
              <label className="w-20 text-sm text-neutral-400 capitalize">{provider}</label>
              <input
                type="password"
                value={values[provider] ?? ""}
                onChange={(e) => setValues((v) => ({ ...v, [provider]: e.target.value }))}
                placeholder="sk-…"
                className="flex-1 bg-surface-800 border border-white/10 rounded-md px-2.5 py-1.5
                  text-sm focus:outline-none focus:ring-1 focus:ring-accent-500"
              />
              <button
                onClick={() => handleSave(provider)}
                className="text-xs px-2.5 py-1.5 rounded-md bg-accent-500 hover:bg-accent-400
                  transition-colors duration-150 text-white w-14"
              >
                {saved[provider] ? "✓" : "Save"}
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
