import { useEffect, useState } from "react";
import { api } from "../api/client";

export function SettingsModal({ onClose }: { onClose: () => void }) {
  const [anthropicKey, setAnthropicKey] = useState("");
  const [openaiKey, setOpenaiKey] = useState("");
  const [googleKey, setGoogleKey] = useState("");
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    api.settings.getKeys().then((keys) => {
      setAnthropicKey(keys.anthropic ?? "");
      setOpenaiKey(keys.openai ?? "");
      setGoogleKey(keys.google ?? "");
    });
  }, []);

  const handleSave = async () => {
    setStatus("Saving…");
    try {
      await api.settings.setKeys({
        anthropic: anthropicKey || undefined,
        openai: openaiKey || undefined,
        google: googleKey || undefined,
      });
      setStatus("Saved!");
      setTimeout(onClose, 800);
    } catch {
      setStatus("Error saving keys");
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-white border border-slate-200 rounded-xl shadow-card w-full max-w-md p-6 space-y-4">
        <div className="flex items-center justify-between border-b border-slate-200 pb-3">
          <h3 className="font-bold text-slate-800 text-base">LLM Provider API Keys</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 font-bold">
            ✕
          </button>
        </div>

        <div className="space-y-3">
          <div>
            <label className="text-xs font-bold text-slate-600 uppercase">Anthropic Key</label>
            <input
              type="password"
              value={anthropicKey}
              onChange={(e) => setAnthropicKey(e.target.value)}
              placeholder="sk-ant-…"
              className="mt-1 w-full bg-slate-50 border border-slate-300 rounded-md px-3 py-1.5 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-accent-500 shadow-sm"
            />
          </div>

          <div>
            <label className="text-xs font-bold text-slate-600 uppercase">OpenAI Key</label>
            <input
              type="password"
              value={openaiKey}
              onChange={(e) => setOpenaiKey(e.target.value)}
              placeholder="sk-…"
              className="mt-1 w-full bg-slate-50 border border-slate-300 rounded-md px-3 py-1.5 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-accent-500 shadow-sm"
            />
          </div>

          <div>
            <label className="text-xs font-bold text-slate-600 uppercase">Google Key</label>
            <input
              type="password"
              value={googleKey}
              onChange={(e) => setGoogleKey(e.target.value)}
              placeholder="AIzaSy…"
              className="mt-1 w-full bg-slate-50 border border-slate-300 rounded-md px-3 py-1.5 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-accent-500 shadow-sm"
            />
          </div>
        </div>

        <div className="flex items-center justify-between pt-2 border-t border-slate-200">
          <span className="text-xs text-slate-500 font-medium">{status}</span>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="text-xs font-semibold px-3 py-1.5 text-slate-600 hover:text-slate-800"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              className="bg-accent-500 hover:bg-accent-400 text-white font-bold text-xs px-4 py-1.5 rounded-md shadow-sm transition-colors"
            >
              Save Keys
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
