import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import { providersNeedingKeys } from "../config/providers";
import { useEscapeKey } from "../hooks/useEscapeKey";
import { Button } from "./ui/Button";
import { Icon } from "./ui/Icon";
import { SystemCheckPanel } from "./SystemCheckPanel";

type KeyStatus = Record<string, { saved: boolean; hint: string }>;

export function SettingsModal({ onClose }: { onClose: () => void }) {
  useEscapeKey(onClose);
  const providers = providersNeedingKeys();

  const [saved, setSaved] = useState<KeyStatus>({});
  const [runtime, setRuntime] = useState<Record<string, boolean> | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [showKeys, setShowKeys] = useState(false);
  const [status, setStatus] = useState<{ tone: "info" | "ok" | "error"; text: string } | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [activeSection, setActiveSection] = useState<"keys" | "system">("keys");

  const refresh = useCallback(async () => {
    setSaved(await api.settings.getKeyStatus());
    try {
      setRuntime(await api.settings.runtimeKeyStatus());
    } catch {
      setRuntime(null); // runtime unreachable: just hide the per-provider runtime hints
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const pending = Object.entries(drafts).filter(([, value]) => value.trim().length > 0);

  const handleSave = async () => {
    if (pending.length === 0 || isBusy) return;
    setIsBusy(true);
    setStatus({ tone: "info", text: "Saving keys…" });
    try {
      await api.settings.setKeys(Object.fromEntries(pending.map(([slot, value]) => [slot, value.trim()])));
      setDrafts({});
      await refresh();
      setStatus({ tone: "ok", text: "Keys saved securely and applied to the runtime." });
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "";
      if (message === "ENCRYPTION_UNAVAILABLE") {
        setStatus({ tone: "error", text: "Secure key storage is unavailable. Keys were not saved. Configure a system keyring or explicitly opt into plaintext storage with AGENTFORGE_ALLOW_PLAINTEXT_KEYS=1." });
      } else if (message === "KEY_SAVED_NOT_APPLIED") {
        setStatus({ tone: "error", text: "Key was saved securely, but the runtime could not apply it. It will be retried at startup." });
        setSaved(await api.settings.getKeyStatus());
      } else {
        setStatus({ tone: "error", text: "Could not save or apply keys. Check the local runtime and try again." });
      }
    } finally {
      setIsBusy(false);
    }
  };

  const handleRemove = async (slot: string, label: string) => {
    if (isBusy) return;
    setIsBusy(true);
    try {
      await api.settings.removeKey(slot);
      await refresh();
      setStatus({ tone: "ok", text: `${label} key removed.` });
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "";
      setStatus({ tone: "error", text: message === "KEY_REMOVED_NOT_APPLIED"
        ? `${label} key was removed from local storage, but the runtime has not received the change yet.`
        : `Could not remove the ${label} key.` });
    } finally {
      setIsBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex select-none items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-title"
        className="flex max-h-[90vh] w-full max-w-lg flex-col rounded-panel border border-studio-700 bg-studio-900 text-studio-100 shadow-elevated"
      >
        <div className="flex items-start justify-between gap-3 border-b border-studio-800 p-5 pb-3">
          <div>
            <h2 id="settings-title" className="text-sm font-semibold">
              Provider API keys
            </h2>
            <p className="mt-0.5 text-2xs text-studio-400">
              Keys stay on this device and are applied to the runtime each time the app starts. Saved keys are never shown in full again.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded p-1 text-studio-400 transition-colors hover:bg-studio-800 hover:text-studio-100"
          >
            <Icon name="close" size={14} />
          </button>
        </div>

        <div role="tablist" aria-label="Settings sections" className="flex gap-1 border-b border-studio-800 bg-studio-950 px-4">
          <button type="button" role="tab" aria-selected={activeSection === "keys"} onClick={() => setActiveSection("keys")} className={`border-b-2 px-3 py-2 text-xs ${activeSection === "keys" ? "border-accent-500 text-accent-300" : "border-transparent text-studio-400 hover:text-studio-200"}`}>Provider keys</button>
          <button type="button" role="tab" aria-selected={activeSection === "system"} onClick={() => setActiveSection("system")} className={`border-b-2 px-3 py-2 text-xs ${activeSection === "system" ? "border-accent-500 text-accent-300" : "border-transparent text-studio-400 hover:text-studio-200"}`}>System check</button>
        </div>
        <div className="flex-1 space-y-4 overflow-y-auto p-5 py-4 text-xs">
          {activeSection === "keys" ? (
          <div className="space-y-4">
          {providers.map((provider) => {
            const info = saved[provider.keyId];
            const runtimeKnown = runtime ? provider.keyId in runtime : true;
            const runtimeActive = runtime ? runtime[provider.keyId] : undefined;
            return (
              <div key={provider.id}>
                <div className="mb-1 flex items-center justify-between gap-2">
                  <label htmlFor={`key-${provider.keyId}`} className="text-2xs font-mono uppercase tracking-wider text-studio-400">
                    {provider.label}
                  </label>
                  <div className="flex items-center gap-2">
                    {info?.saved ? (
                      <span className="font-mono text-2xs text-emerald-400">Saved {info.hint}</span>
                    ) : (
                      <span className="font-mono text-2xs text-studio-500">Not set</span>
                    )}
                    {info?.saved && (
                      <button
                        type="button"
                        onClick={() => void handleRemove(provider.keyId, provider.label)}
                        className="text-2xs text-studio-500 transition-colors hover:text-red-300"
                      >
                        Remove
                      </button>
                    )}
                  </div>
                </div>
                <input
                  id={`key-${provider.keyId}`}
                  type={showKeys ? "text" : "password"}
                  autoComplete="off"
                  spellCheck={false}
                  value={drafts[provider.keyId] ?? ""}
                  onChange={(e) => setDrafts((prev) => ({ ...prev, [provider.keyId]: e.target.value }))}
                  placeholder={info?.saved ? "Paste a new key to replace it" : provider.keyPlaceholder}
                  className="w-full rounded-md border border-studio-700 bg-studio-800 px-3 py-1.5 font-mono text-xs text-studio-100 placeholder:text-studio-500 focus:border-accent-500 focus:outline-none"
                />
                {info?.saved && !runtimeKnown && (
                  <p className="mt-1 text-2xs text-amber-300">
                    Saved on this device, but this version of the runtime does not accept {provider.label} keys yet.
                  </p>
                )}
                {info?.saved && runtimeKnown && runtimeActive === false && (
                  <p className="mt-1 text-2xs text-amber-300">Saved, but not active in the runtime yet. Press Save or restart the app.</p>
                )}
              </div>
            );
          })}
          <p className="text-2xs text-studio-500">Local models (Ollama) need no key.</p>
          </div>
          ) : <SystemCheckPanel />}
        </div>

        <div className="space-y-3 border-t border-studio-800 p-5 pt-3">
          {status && (
            <p
              role={status.tone === "error" ? "alert" : "status"}
              className={`text-2xs ${status.tone === "error" ? "text-red-300" : status.tone === "ok" ? "text-emerald-400" : "text-studio-400"}`}
            >
              {status.text}
            </p>
          )}
          <div className="flex items-center justify-between">
            <label className="flex cursor-pointer items-center gap-1.5 text-2xs text-studio-500">
              <input
                type="checkbox"
                checked={showKeys}
                onChange={(e) => setShowKeys(e.target.checked)}
                className="h-3.5 w-3.5 rounded accent-accent-500"
              />
              <span>Show what I type</span>
            </label>
            <div className="flex gap-2">
              <Button size="xs" variant="outline" onClick={onClose}>
                Close
              </Button>
              <Button size="xs" variant="primary" onClick={() => void handleSave()} disabled={pending.length === 0 || isBusy}>
                {isBusy ? "Saving…" : "Save keys"}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
