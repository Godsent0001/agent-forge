import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { useStore } from "../store/useStore";
import type { CatalogShelf } from "../types";

const STATUS_BADGE: Record<string, string> = {
  real: "bg-status-success/15 text-status-success",
  stub: "bg-status-idle/20 text-neutral-400",
};

export function ToolCatalogModal({ onClose }: { onClose: () => void }) {
  const [shelves, setShelves] = useState<CatalogShelf[] | null>(null);
  const [query, setQuery] = useState("");
  const [openShelf, setOpenShelf] = useState<string | null>(null);
  const [addedFeedback, setAddedFeedback] = useState<string | null>(null);
  const tools = useStore((s) => s.tools);
  const createTool = useStore((s) => s.createTool);

  useEffect(() => {
    api.catalog.shelves().then((data) => {
      setShelves(data);
      setOpenShelf(data[0]?.shelf ?? null);
    });
  }, []);

  const attachedKinds = useMemo(() => new Set(tools.map((t) => t.kind)), [tools]);

  const filteredShelves = useMemo(() => {
    if (!shelves) return [];
    const q = query.trim().toLowerCase();
    if (!q) return shelves;
    return shelves
      .map((shelf) => ({
        ...shelf,
        tools: shelf.tools.filter(
          (t) => t.name.toLowerCase().includes(q) || t.description.toLowerCase().includes(q)
        ),
      }))
      .filter((shelf) => shelf.tools.length > 0);
  }, [shelves, query]);

  const handleAdd = async (kind: string, name: string) => {
    await createTool(name, kind);
    setAddedFeedback(kind);
    setTimeout(() => setAddedFeedback(null), 1200);
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 animate-fade-in p-6">
      <div className="bg-surface-900 border border-white/10 rounded-panel shadow-panel
        w-full max-w-3xl h-[85vh] flex flex-col overflow-hidden">
        <div className="px-6 py-4 border-b border-white/5 flex items-center gap-3 shrink-0">
          <h2 className="text-base font-semibold">Tool Library</h2>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search tools…"
            className="flex-1 bg-surface-800 border border-white/10 rounded-md px-3 py-1.5
              text-sm placeholder:text-neutral-600 focus:outline-none focus:ring-1 focus:ring-accent-500"
          />
          <button onClick={onClose} className="text-neutral-500 hover:text-neutral-300 text-sm">
            ✕
          </button>
        </div>

        <div className="flex-1 overflow-y-auto">
          {!shelves && (
            <p className="px-6 py-8 text-sm text-neutral-500">Loading catalog…</p>
          )}
          {filteredShelves.map((shelf) => (
            <div key={shelf.shelf} className="border-b border-white/5">
              <button
                onClick={() => setOpenShelf(openShelf === shelf.shelf ? null : shelf.shelf)}
                className="w-full flex items-center justify-between px-6 py-3 hover:bg-white/[0.02]
                  transition-colors duration-150"
              >
                <span className="text-sm font-semibold text-neutral-200">{shelf.label}</span>
                <span className="text-xs text-neutral-600">
                  {shelf.tools.length} tool{shelf.tools.length !== 1 ? "s" : ""}
                  <span className="ml-2">{openShelf === shelf.shelf ? "▾" : "▸"}</span>
                </span>
              </button>

              {(openShelf === shelf.shelf || query) && (
                <div className="pb-2">
                  {shelf.tools.map((tool) => {
                    const attached = attachedKinds.has(tool.kind);
                    const justAdded = addedFeedback === tool.kind;
                    return (
                      <div
                        key={tool.kind}
                        className="px-6 py-2.5 flex items-start gap-3 hover:bg-white/[0.02] transition-colors duration-150"
                      >
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm text-neutral-200">{tool.name}</span>
                            <span className={`text-[10px] px-1.5 py-0.5 rounded-full uppercase tracking-wide
                              ${STATUS_BADGE[tool.status]}`}>
                              {tool.status === "real" ? "ready" : "needs setup"}
                            </span>
                          </div>
                          <p className="text-xs text-neutral-500 mt-0.5 leading-relaxed">
                            {tool.description}
                          </p>
                        </div>
                        <button
                          onClick={() => handleAdd(tool.kind, tool.name)}
                          disabled={attached}
                          className={`shrink-0 text-xs px-3 py-1.5 rounded-md transition-colors duration-150
                            ${attached
                              ? "bg-white/5 text-neutral-600 cursor-default"
                              : "bg-accent-500 hover:bg-accent-400 text-white"}`}
                        >
                          {justAdded ? "✓ Added" : attached ? "Added" : "Add"}
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          ))}
          {shelves && filteredShelves.length === 0 && (
            <p className="px-6 py-8 text-sm text-neutral-600">No tools match "{query}".</p>
          )}
        </div>
      </div>
    </div>
  );
}
