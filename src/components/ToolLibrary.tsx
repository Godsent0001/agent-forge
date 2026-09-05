import { useState } from "react";
import { useStore } from "../store/useStore";
import { ToolCatalogModal } from "./ToolCatalogModal";

export function ToolLibrary() {
  const tools = useStore((s) => s.tools);
  const createTool = useStore((s) => s.createTool);
  const attachToolToSelected = useStore((s) => s.attachToolToSelected);
  const selectedAgentId = useStore((s) => s.selectedAgentId);

  const [customName, setCustomName] = useState("");
  const [customKind, setCustomKind] = useState("web_search");
  const [catalogOpen, setCatalogOpen] = useState(false);

  const handleCreateCustom = async () => {
    if (!customName.trim()) return;
    await createTool(customName.trim(), customKind);
    setCustomName("");
  };

  return (
    <div className="border-t border-slate-200 p-3 bg-slate-50/50 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">
          Tool Library
        </h3>
        <button
          onClick={() => setCatalogOpen(true)}
          className="text-xs bg-slate-200 hover:bg-slate-300 text-slate-700 font-semibold px-2 py-0.5 rounded transition-colors shadow-sm"
        >
          + Browse Catalog
        </button>
      </div>

      <div className="max-h-36 overflow-y-auto space-y-1 pr-1">
        {tools.map((t) => (
          <div
            key={t.id}
            className="flex items-center justify-between text-xs py-1 px-2 rounded bg-white border border-slate-200 shadow-sm"
          >
            <span className="truncate font-medium text-slate-700">🔧 {t.name}</span>
            {selectedAgentId && (
              <button
                onClick={() => attachToolToSelected(t.id)}
                className="text-[10px] text-accent-500 hover:text-accent-400 font-bold ml-1"
              >
                Attach
              </button>
            )}
          </div>
        ))}
        {tools.length === 0 && (
          <p className="text-xs text-slate-400 italic">No tools added yet.</p>
        )}
      </div>

      <div className="space-y-1.5 pt-1 border-t border-slate-200">
        <span className="text-[11px] font-semibold text-slate-500">Quick Add Tool</span>
        <div className="flex gap-1">
          <input
            value={customName}
            onChange={(e) => setCustomName(e.target.value)}
            placeholder="Tool name…"
            className="flex-1 bg-white border border-slate-300 rounded px-2 py-1 text-xs text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-1 focus:ring-accent-500 shadow-sm"
          />
          <select
            value={customKind}
            onChange={(e) => setCustomKind(e.target.value)}
            className="bg-white border border-slate-300 text-xs text-slate-800 rounded px-1 py-1 focus:outline-none focus:ring-1 focus:ring-accent-500 shadow-sm"
          >
            <option value="web_search">web_search</option>
            <option value="python">python</option>
            <option value="file_system">file_system</option>
            <option value="http_request">http_request</option>
          </select>
          <button
            onClick={handleCreateCustom}
            className="bg-accent-500 hover:bg-accent-400 text-white font-bold text-xs px-2.5 py-1 rounded shadow-sm"
          >
            Add
          </button>
        </div>
      </div>

      {catalogOpen && <ToolCatalogModal onClose={() => setCatalogOpen(false)} />}
    </div>
  );
}
