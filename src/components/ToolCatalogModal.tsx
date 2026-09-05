import { useEffect, useState } from "react";
import { api } from "../api/client";
import { useStore } from "../store/useStore";
import type { CatalogShelf, CatalogToolEntry } from "../types";

export function ToolCatalogModal({ onClose }: { onClose: () => void }) {
  const createTool = useStore((s) => s.createTool);
  const attachToolToSelected = useStore((s) => s.attachToolToSelected);
  const selectedAgentId = useStore((s) => s.selectedAgentId);

  const [shelves, setShelves] = useState<CatalogShelf[]>([]);
  const [selectedShelf, setSelectedShelf] = useState<string>("");

  useEffect(() => {
    api.catalog.shelves().then((data) => {
      setShelves(data);
      if (data.length > 0) {
        setSelectedShelf(data[0].shelf);
      }
    });
  }, []);

  const activeShelf = shelves.find((s) => s.shelf === selectedShelf) ?? shelves[0];

  const handleAdd = async (item: CatalogToolEntry) => {
    await createTool(item.name, item.kind);
    if (selectedAgentId) {
      const { tools } = useStore.getState();
      const created = tools.find((t) => t.name === item.name);
      if (created) {
        await attachToolToSelected(created.id);
      }
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-white border border-slate-200 rounded-xl shadow-card w-full max-w-4xl h-[80vh] flex flex-col overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between bg-slate-50">
          <div>
            <h2 className="text-base font-bold text-slate-800">Tool Catalog Shelf</h2>
            <p className="text-xs text-slate-500">Pick production tools from specialized domain shelves</p>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-600 font-bold text-lg px-2"
          >
            ✕
          </button>
        </div>

        <div className="flex-1 grid grid-cols-[220px_1fr] min-h-0">
          <div className="border-r border-slate-200 overflow-y-auto p-2 bg-slate-50 space-y-1">
            {shelves.map((shelf) => (
              <button
                key={shelf.shelf}
                onClick={() => setSelectedShelf(shelf.shelf)}
                className={`w-full text-left px-3 py-2 rounded-lg text-xs font-semibold flex items-center justify-between transition-colors ${
                  selectedShelf === shelf.shelf
                    ? "bg-accent-500 text-white shadow-sm"
                    : "text-slate-700 hover:bg-slate-200/60"
                }`}
              >
                <span>{shelf.label}</span>
                <span className="opacity-80">({shelf.tools.length})</span>
              </button>
            ))}
          </div>

          <div className="overflow-y-auto p-6 space-y-4 bg-white">
            {activeShelf ? (
              <>
                <p className="text-xs text-slate-500 italic">{activeShelf.label} production shelf</p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {activeShelf.tools.map((item) => (
                    <div
                      key={item.kind}
                      className="p-3 border border-slate-200 rounded-lg hover:border-accent-300 transition-all bg-surface-950 flex flex-col justify-between"
                    >
                      <div>
                        <h4 className="text-sm font-bold text-slate-800">{item.name}</h4>
                        <span className="text-[10px] font-mono text-slate-400">{item.kind}</span>
                        <p className="text-xs text-slate-600 mt-1 leading-relaxed">{item.description}</p>
                      </div>
                      <button
                        onClick={() => handleAdd(item)}
                        className="mt-3 text-xs bg-accent-500 hover:bg-accent-400 text-white font-bold py-1.5 px-3 rounded-md shadow-sm transition-colors self-end"
                      >
                        + Add to Library
                      </button>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <p className="text-xs text-slate-400">Loading catalog shelves…</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
