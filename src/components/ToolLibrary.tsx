import { useState } from "react";
import { useStore } from "../store/useStore";
import { ToolCatalogModal } from "./ToolCatalogModal";

export function ToolLibrary({ onFeedback }: { onFeedback?: (msg: string) => void }) {
  const tools = useStore((s) => s.tools);
  const createTool = useStore((s) => s.createTool);
  const deleteTool = useStore((s) => s.deleteTool);
  const attachToolToSelected = useStore((s) => s.attachToolToSelected);
  const selectedAgentId = useStore((s) => s.selectedAgentId);
  const agent = useStore((s) => s.agents.find((a) => a.id === s.selectedAgentId));

  const [customName, setCustomName] = useState("");
  const [customKind, setCustomKind] = useState("web_search");
  const [catalogOpen, setCatalogOpen] = useState(false);

  const handleCreateCustom = async () => {
    if (!customName.trim()) return;
    await createTool(customName.trim(), customKind);
    onFeedback?.(`Tool "${customName.trim()}" created`);
    setCustomName("");
  };

  const handleAttach = async (toolId: string, toolName: string) => {
    if (!selectedAgentId) return;
    await attachToolToSelected(toolId);
    onFeedback?.(`Tool "${toolName}" attached to ${agent?.name ?? "agent"}`);
  };

  const handleDeleteTool = async (toolId: string, toolName: string) => {
    if (confirm(`Are you sure you want to delete tool "${toolName}"?`)) {
      await deleteTool(toolId);
      onFeedback?.(`Tool "${toolName}" deleted`);
    }
  };

  return (
    <div className="border-t border-slate-200 p-2.5 bg-slate-50/50 space-y-2 shrink-0">
      <div className="flex items-center justify-between">
        <h3 className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
          Tool Library
        </h3>
        <button
          onClick={() => setCatalogOpen(true)}
          className="text-xs bg-slate-200 hover:bg-slate-300 text-slate-700 font-semibold px-2 py-0.5 rounded transition-colors shadow-sm shrink-0"
        >
          + Catalog
        </button>
      </div>

      <div className="max-h-28 overflow-y-auto space-y-1 pr-1">
        {tools.map((t) => {
          const isAttachedToSelected = agent?.tool_ids?.includes(t.id);
          return (
            <div
              key={t.id}
              className="group flex items-center justify-between text-xs py-1 px-2 rounded bg-white border border-slate-200 shadow-sm min-w-0"
            >
              <span className="truncate font-medium text-slate-700 min-w-0 pr-1">
                🔧 {t.name}
              </span>
              <div className="flex items-center gap-1 shrink-0">
                {selectedAgentId && (
                  <button
                    disabled={isAttachedToSelected}
                    onClick={() => handleAttach(t.id, t.name)}
                    className={`text-[10px] font-bold px-1.5 py-0.5 rounded transition-colors ${
                      isAttachedToSelected
                        ? "text-slate-400 bg-slate-100 cursor-default"
                        : "text-accent-600 hover:bg-accent-100 bg-accent-50"
                    }`}
                  >
                    {isAttachedToSelected ? "Attached" : "+ Attach"}
                  </button>
                )}
                <button
                  onClick={() => handleDeleteTool(t.id, t.name)}
                  className="opacity-0 group-hover:opacity-100 p-0.5 text-slate-400 hover:text-red-600 transition-opacity"
                  title="Delete Tool"
                >
                  ✕
                </button>
              </div>
            </div>
          );
        })}
        {tools.length === 0 && (
          <p className="text-xs text-slate-400 italic">No tools added yet.</p>
        )}
      </div>

      <div className="space-y-1 pt-1.5 border-t border-slate-200">
        <span className="text-[11px] font-semibold text-slate-500">Quick Add Tool</span>
        <div className="flex gap-1">
          <input
            value={customName}
            onChange={(e) => setCustomName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleCreateCustom()}
            placeholder="Tool name…"
            className="flex-1 min-w-0 bg-white border border-slate-300 rounded px-2 py-1 text-xs text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-1 focus:ring-accent-500 shadow-sm"
          />
          <select
            value={customKind}
            onChange={(e) => setCustomKind(e.target.value)}
            className="bg-white border border-slate-300 text-xs text-slate-800 rounded px-1 py-1 focus:outline-none focus:ring-1 focus:ring-accent-500 shadow-sm shrink-0"
          >
            <option value="web_search">web_search</option>
            <option value="python">python</option>
            <option value="file_system">file_system</option>
            <option value="http_request">http_request</option>
          </select>
          <button
            onClick={handleCreateCustom}
            className="bg-accent-500 hover:bg-accent-400 text-white font-bold text-xs px-2 py-1 rounded shadow-sm shrink-0"
          >
            Add
          </button>
        </div>
      </div>

      {catalogOpen && <ToolCatalogModal onClose={() => setCatalogOpen(false)} />}
    </div>
  );
}
