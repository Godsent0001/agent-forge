import { useEffect, useState } from "react";
import { keychain } from "../api/keychain";

const PROVIDERS = ["anthropic", "openai", "google"] as const;

export function SettingsModal({ onClose }: { onClose: () => void }) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState<Record<string, boolean>>({});

  useEffect(() => {
    (async () => {
      const entries = await Promise.all(
        PROVIDERS.map(async (p) => [p, (await keychain.get(p)) ?? ""] as const)
      );
      setValues(Object.fromEntries(entries));
    })();
  }, []);

  const handleSave = async (provider: string) => {
    await keychain.save(provider, values[provider] ?? "");
    setSaved((s) => ({ ...s, [provider]: true }));
    setTimeout(() => setSaved((s) => ({ ...s, [provider]: false })), 1500);
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 animate-fade-in">
      <div className="bg-surface-900 border border-white/10 rounded-panel shadow-panel w-full max-w-md p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold">API Keys</h2>
          <button onClick={onClose} className="text-neutral-500 hover:text-neutral-300 text-sm">
            ✕
          </button>
        </div>
        <p className="text-xs text-neutral-500 mb-4">
          Stored in your OS keychain — never written to disk in plain text.
        </p>
        <div className="space-y-3">
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
