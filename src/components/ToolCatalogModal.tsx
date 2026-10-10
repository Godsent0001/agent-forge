import { useEffect, useState } from "react";
import { api } from "../api/client";
import { useStore } from "../store/useStore";
import type { CatalogShelf, CatalogToolEntry } from "../types";
import { Button } from "./ui/Button";

export function ToolCatalogModal({ onClose }: { onClose: () => void }) {
  const createTool = useStore((s) => s.createTool);
  const attachToolToSelected = useStore((s) => s.attachToolToSelected);
  const selectedAgentId = useStore((s) => s.selectedAgentId);
  const agents = useStore((s) => s.agents);
  const tools = useStore((s) => s.tools);

  const selectedAgent = agents.find((a) => a.id === selectedAgentId);

  const [shelves, setShelves] = useState<CatalogShelf[]>([]);
  const [selectedShelf, setSelectedShelf] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState("");
  const [addingKind, setAddingKind] = useState<string | null>(null);

  useEffect(() => {
    api.catalog.shelves().then((data) => {
      setShelves(data);
      if (data.length > 0) {
        setSelectedShelf(data[0].shelf);
      }
    });
  }, []);

  const activeShelf = shelves.find((s) => s.shelf === selectedShelf) ?? shelves[0];

  // Attached tool names for current agent
  const attachedToolNames = new Set(
    tools
      .filter((t) => selectedAgent?.tool_ids?.includes(t.id))
      .map((t) => t.name.toLowerCase())
  );

  const handleAddAndAttach = async (item: CatalogToolEntry) => {
    setAddingKind(item.kind);
    try {
      await createTool(item.name, item.kind);
      if (selectedAgentId) {
        // Find newly created tool in refreshed store
        const currentTools = useStore.getState().tools;
        const created = currentTools.find((t) => t.name === item.name);
        if (created) {
          await attachToolToSelected(created.id);
        }
      }
    } catch (err) {
      console.error("Failed to add tool from catalog:", err);
    } finally {
      setAddingKind(null);
    }
  };

  const filteredTools = activeShelf
    ? activeShelf.tools.filter(
        (t) =>
          !searchQuery.trim() ||
          t.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
          t.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
          t.kind.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : [];

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 select-none">
      <div className="bg-studio-900 border border-studio-700/90 rounded-panel shadow-elevated w-full max-w-4xl h-[80vh] flex flex-col overflow-hidden text-studio-100">
        {/* Header */}
        <div className="px-5 py-3.5 border-b border-studio-800 flex items-center justify-between bg-studio-850 shrink-0">
          <div className="flex items-center gap-2.5">
            <span className="w-6 h-6 rounded bg-accent-900 text-accent-400 border border-accent-400/30 flex items-center justify-center text-xs">
              📚
            </span>
            <div>
              <h2 className="text-sm font-semibold text-studio-100">
                Tool Catalog & Domain Shelves
              </h2>
              <p className="text-2xs text-studio-400">
                Explore 40+ specialized production tools across 12 domain shelves
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search shelf tools…"
              className="bg-studio-800 text-studio-100 placeholder:text-studio-500 border border-studio-700 rounded px-2.5 py-1 text-2xs focus:outline-none focus:border-accent-500 w-44"
            />
            <button
              onClick={onClose}
              className="p-1.5 text-studio-400 hover:text-studio-100 hover:bg-studio-800 rounded transition-colors text-xs cursor-pointer"
              title="Close Catalog"
            >
              ✕
            </button>
          </div>
        </div>

        {/* Modal Body: Left Shelves Rail, Right Tools Grid */}
        <div className="flex-1 grid grid-cols-[220px_1fr] min-h-0 divide-x divide-studio-800">
          {/* Left: Shelves List */}
          <div className="overflow-y-auto p-2 bg-studio-950/60 space-y-0.5">
            <span className="text-2xs font-mono uppercase text-studio-500 px-2 py-1 block">
              Domain Shelves ({shelves.length})
            </span>
            {shelves.map((shelf) => {
              const isSelected = selectedShelf === shelf.shelf;
              return (
                <button
                  key={shelf.shelf}
                  onClick={() => setSelectedShelf(shelf.shelf)}
                  className={`w-full text-left px-2.5 py-2 rounded text-xs font-medium flex items-center justify-between transition-colors cursor-pointer ${
                    isSelected
                      ? "bg-studio-800 text-accent-400 border border-studio-700/80 shadow-studio"
                      : "text-studio-400 hover:bg-studio-850 hover:text-studio-200"
                  }`}
                >
                  <span className="truncate">{shelf.label}</span>
                  <span className="text-2xs font-mono opacity-60">({shelf.tools.length})</span>
                </button>
              );
            })}
          </div>

          {/* Right: Tools in Selected Shelf */}
          <div className="overflow-y-auto p-5 space-y-4 bg-studio-900">
            {activeShelf ? (
              <>
                <div className="flex items-center justify-between pb-2 border-b border-studio-800">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-studio-200 text-xs">
                      {activeShelf.label} Shelf
                    </span>
                    <span className="text-2xs font-mono text-studio-500">
                      ({filteredTools.length} tools)
                    </span>
                  </div>
                  {selectedAgent && (
                    <span className="text-2xs font-mono text-accent-400">
                      Target: {selectedAgent.name}
                    </span>
                  )}
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {filteredTools.map((item) => {
                    const isAttached = attachedToolNames.has(item.name.toLowerCase());
                    const isBusy = addingKind === item.kind;

                    return (
                      <div
                        key={item.kind}
                        className="p-3.5 border border-studio-800 rounded-md hover:border-studio-700 transition-all bg-studio-950/40 flex flex-col justify-between space-y-3"
                      >
                        <div>
                          <div className="flex items-start justify-between gap-2">
                            <h4 className="text-xs font-semibold text-studio-100">
                              {item.name}
                            </h4>
                            <span className="text-2xs font-mono text-emerald-400/90 bg-emerald-950/40 border border-emerald-900/60 px-1.5 py-0.2 rounded shrink-0">
                              {item.status}
                            </span>
                          </div>
                          <span className="text-2xs font-mono text-studio-500 block mt-0.5">
                            {item.kind}
                          </span>
                          <p className="text-2xs text-studio-400 mt-2 leading-relaxed">
                            {item.description}
                          </p>
                        </div>

                        <div className="pt-2 border-t border-studio-850 flex items-center justify-between">
                          <span className="text-2xs font-mono text-studio-500">
                            Shelf: {activeShelf.shelf}
                          </span>
                          <Button
                            size="xs"
                            variant={isAttached ? "secondary" : "primary"}
                            disabled={isAttached || isBusy}
                            onClick={() => handleAddAndAttach(item)}
                          >
                            {isBusy
                              ? "Adding…"
                              : isAttached
                              ? "Already Attached"
                              : selectedAgent
                              ? "+ Attach to Agent"
                              : "+ Add to Project"}
                          </Button>
                        </div>
                      </div>
                    );
                  })}

                  {filteredTools.length === 0 && (
                    <div className="col-span-2 p-8 text-center text-studio-500 text-xs border border-dashed border-studio-800 rounded-md">
                      No tools match the filter query &ldquo;{searchQuery}&rdquo;.
                    </div>
                  )}
                </div>
              </>
            ) : (
              <p className="text-xs text-studio-400">Loading catalog shelves…</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
