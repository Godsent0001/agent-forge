import { useState } from "react";
import { useStore } from "../store/useStore";

const TOOL_KINDS = ["web_search", "python", "file_system", "http_request"] as const;

export function ToolLibrary() {
  const tools = useStore((s) => s.tools);
  const createTool = useStore((s) => s.createTool);
  const [name, setName] = useState("");
  const [kind, setKind] = useState<(typeof TOOL_KINDS)[number]>("web_search");

  return (
    <div className="border-t border-white/5 p-3">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-neutral-500 mb-2">
        Tool Library
      </h3>
      <div className="flex flex-wrap gap-1.5 mb-2">
        {tools.map((t) => (
          <span key={t.id} className="text-xs px-2 py-1 rounded-full bg-surface-800 text-neutral-400">
            🔧 {t.name}
          </span>
        ))}
        {tools.length === 0 && <p className="text-xs text-neutral-600">No tools yet.</p>}
      </div>
      <div className="flex gap-1.5">
        <select
          value={kind}
          onChange={(e) => setKind(e.target.value as typeof kind)}
          className="bg-surface-800 border border-white/10 rounded-md px-2 py-1 text-xs"
        >
          {TOOL_KINDS.map((k) => (
            <option key={k} value={k}>{k}</option>
          ))}
        </select>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="tool name…"
          className="flex-1 bg-surface-800 border border-white/10 rounded-md px-2 py-1 text-xs"
        />
        <button
          onClick={() => {
            if (name.trim()) {
              createTool(name.trim(), kind);
              setName("");
            }
          }}
          className="text-xs px-2.5 py-1 rounded-md bg-accent-500 hover:bg-accent-400
            transition-colors duration-150 text-white"
        >
          Add
        </button>
      </div>
    </div>
  );
}
