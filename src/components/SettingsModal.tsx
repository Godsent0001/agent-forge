import { useEffect, useState } from "react";
import { api } from "../api/client";
import { Button } from "./ui/Button";

export function SettingsModal({ onClose }: { onClose: () => void }) {
  const [anthropicKey, setAnthropicKey] = useState("");
  const [openaiKey, setOpenaiKey] = useState("");
  const [googleKey, setGoogleKey] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [showKeys, setShowKeys] = useState(false);

  useEffect(() => {
    api.settings.getKeys().then((keys) => {
      setAnthropicKey(keys.anthropic ?? "");
      setOpenaiKey(keys.openai ?? "");
      setGoogleKey(keys.google ?? "");
    });
  }, []);

  const handleSave = async () => {
    setStatus("Saving keys…");
    try {
      await api.settings.setKeys({
        anthropic: anthropicKey || undefined,
        openai: openaiKey || undefined,
        google: googleKey || undefined,
      });
      setStatus("Keys saved & synced!");
      setTimeout(onClose, 800);
    } catch {
      setStatus("Error saving keys");
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 select-none">
      <div className="bg-studio-900 border border-studio-700 rounded-panel shadow-elevated w-full max-w-md p-5 space-y-4 text-studio-100">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-studio-800 pb-3">
          <div className="flex items-center gap-2">
            <span className="text-base">⚙️</span>
            <div>
              <h3 className="font-semibold text-studio-100 text-sm">
                LLM Provider Keys & Settings
              </h3>
              <p className="text-2xs text-studio-400">
                Credentials are saved securely for agent reasoning and execution
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 text-studio-400 hover:text-studio-100 hover:bg-studio-800 rounded transition-colors text-xs cursor-pointer"
          >
            ✕
          </button>
        </div>

        {/* Inputs */}
        <div className="space-y-3.5 text-xs">
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-2xs font-mono uppercase text-studio-400 tracking-wider">
                Google Gemini API Key (Default)
              </label>
              <span className="text-2xs font-mono text-emerald-400">Recommended</span>
            </div>
            <input
              type={showKeys ? "text" : "password"}
              value={googleKey}
              onChange={(e) => setGoogleKey(e.target.value)}
              placeholder="AIzaSy…"
              className="w-full bg-studio-800 border border-studio-700 rounded-md px-3 py-1.5 text-xs text-studio-100 font-mono placeholder:text-studio-500 focus:outline-none focus:border-accent-500"
            />
          </div>

          <div>
            <label className="block text-2xs font-mono uppercase text-studio-400 tracking-wider mb-1">
              OpenAI API Key
            </label>
            <input
              type={showKeys ? "text" : "password"}
              value={openaiKey}
              onChange={(e) => setOpenaiKey(e.target.value)}
              placeholder="sk-…"
              className="w-full bg-studio-800 border border-studio-700 rounded-md px-3 py-1.5 text-xs text-studio-100 font-mono placeholder:text-studio-500 focus:outline-none focus:border-accent-500"
            />
          </div>

          <div>
            <label className="block text-2xs font-mono uppercase text-studio-400 tracking-wider mb-1">
              Anthropic API Key
            </label>
            <input
              type={showKeys ? "text" : "password"}
              value={anthropicKey}
              onChange={(e) => setAnthropicKey(e.target.value)}
              placeholder="sk-ant-…"
              className="w-full bg-studio-800 border border-studio-700 rounded-md px-3 py-1.5 text-xs text-studio-100 font-mono placeholder:text-studio-500 focus:outline-none focus:border-accent-500"
            />
          </div>

          <div className="flex items-center justify-between pt-1 text-2xs text-studio-500">
            <label className="flex items-center gap-1.5 cursor-pointer">
              <input
                type="checkbox"
                checked={showKeys}
                onChange={(e) => setShowKeys(e.target.checked)}
                className="w-3.5 h-3.5 accent-accent-500 rounded"
              />
              <span>Reveal keys</span>
            </label>
            <span>Auto-fallback simulation is enabled if keys are unset.</span>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between pt-3 border-t border-studio-800">
          <span className="text-2xs font-mono text-accent-400">{status}</span>
          <div className="flex gap-2">
            <Button size="xs" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button size="xs" variant="primary" onClick={handleSave}>
              Save & Sync Keys
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
