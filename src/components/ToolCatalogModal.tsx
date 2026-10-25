import { useEffect, useState } from "react";
import { api } from "../api/client";
import { useStore } from "../store/useStore";
import type { CatalogShelf, CatalogToolEntry } from "../types";
import { Button } from "./ui/Button";
import { Icon } from "./ui/Icon";
import { useEscapeKey } from "../hooks/useEscapeKey";

export function ToolCatalogModal({ onClose }: { onClose: () => void }) {
  useEscapeKey(onClose);
  const createTool = useStore((s) => s.createTool);
  const attachToolToSelected = useStore((s) => s.attachToolToSelected);
  const selectedAgentId = useStore((s) => s.selectedAgentId);
  const agents = useStore((s) => s.agents);
  const tools = useStore((s) => s.tools);

  const selectedAgent = agents.find((a) => a.id === selectedAgentId);

  const [shelves, setShelves] = useState<CatalogShelf[]>([]);
  const [selectedShelf, setSelectedShelf] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState("");
  const [addingKey, setAddingKey] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState<string | null>(null);
  const [videoPackEnabled, setVideoPackEnabled] = useState(() => {
    try { return localStorage.getItem("agentforge-video-pack") === "enabled"; }
    catch { return false; }
  });

  const loadShelves = async (enableVideoPack = videoPackEnabled) => {
    setIsLoading(true);
    setCatalogError(null);
    try {
      const data = await api.catalog.shelves(enableVideoPack ? "video" : "none");
      setShelves(data);
      setSelectedShelf((current) => data.some((shelf) => shelf.shelf === current) ? current : data[0]?.shelf ?? "");
    } catch (error) {
      setCatalogError(error instanceof Error ? error.message : "Could not load the tool catalog.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => { void loadShelves(videoPackEnabled); }, []);

  const toggleVideoPack = (enabled: boolean) => {
    setVideoPackEnabled(enabled);
    try { localStorage.setItem("agentforge-video-pack", enabled ? "enabled" : "disabled"); }
    catch { /* browser storage can be disabled; this session toggle still works */ }
    setSelectedShelf("");
    void loadShelves(enabled);
  };

  const activeShelf = shelves.find((s) => s.shelf === selectedShelf) ?? shelves[0];

  const findProjectTool = (item: CatalogToolEntry) => tools.find(
    (tool) => tool.name.trim().toLowerCase() === item.name.trim().toLowerCase() && tool.kind === item.kind
  );

  const handleAddAndAttach = async (item: CatalogToolEntry) => {
    const actionKey = `${item.kind}:${item.name.trim().toLowerCase()}`;
    setAddingKey(actionKey);
    setActionNotice(null);
    try {
      let projectTool = useStore.getState().tools.find(
        (tool) => tool.name.trim().toLowerCase() === item.name.trim().toLowerCase() && tool.kind === item.kind
      );
      if (!projectTool) {
        const existingIds = new Set(useStore.getState().tools.map((tool) => tool.id));
        await createTool(item.name, item.kind);
        projectTool = useStore.getState().tools.find(
          (tool) => !existingIds.has(tool.id) &&
            tool.name.trim().toLowerCase() === item.name.trim().toLowerCase() &&
            tool.kind === item.kind
        );
      }
      if (!projectTool) throw new Error("The tool was not returned after creation. Refresh the catalog and retry.");

      if (selectedAgentId) {
        const latestAgent = useStore.getState().agents.find((agent) => agent.id === selectedAgentId);
        if (latestAgent?.tool_ids?.includes(projectTool.id)) {
          setActionNotice(`"${projectTool.name}" is already attached to this agent.`);
          return;
        }
        await attachToolToSelected(projectTool.id);
        setActionNotice(`Attached "${projectTool.name}" to ${latestAgent?.name ?? "the selected agent"}.`);
      } else {
        setActionNotice(`Added "${projectTool.name}" to the project.`);
      }
    } catch (error) {
      setActionNotice(error instanceof Error ? error.message : "Could not add this tool. Please retry.");
    } finally {
      setAddingKey(null);
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
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 select-none" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <div role="dialog" aria-modal="true" aria-label="Tool catalog" className="bg-studio-900 rounded-panel shadow-elevated w-full max-w-4xl h-[80vh] flex flex-col overflow-hidden text-studio-100">
        {/* Header */}
        <div className="px-5 py-3.5 border-b border-line flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2.5">
            <span className="w-8 h-8 rounded-lg bg-studio-900 neu-raised-sm text-accent-300 flex items-center justify-center"><Icon name="catalog" size={16} /></span>
            <div><h2 className="text-sm font-semibold text-studio-100">Tool catalog</h2><p className="text-2xs text-studio-400">Browse by category and add tools to the selected agent.</p></div>
          </div>

          <div className="flex items-center gap-2">
            <label className="flex items-center gap-1.5 whitespace-nowrap text-2xs text-studio-300" title="Video-production tools are disabled by default">
              <input type="checkbox" checked={videoPackEnabled} onChange={(event) => toggleVideoPack(event.target.checked)} className="h-3.5 w-3.5 accent-accent-500" />
              Video pack
            </label>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search shelf tools…"
              className="bg-studio-900 text-studio-100 placeholder:text-studio-500 border border-transparent rounded-lg px-3 py-1.5 text-2xs focus:outline-none focus:border-accent-500/60 w-44"
            />
            <button
              onClick={onClose}
              className="neu-btn p-1.5 text-studio-400 transition-all text-xs cursor-pointer"
              title="Close catalog"
              aria-label="Close catalog"
            >
              <Icon name="close" size={14} />
            </button>
          </div>
        </div>

        {/* Modal Body: Left Shelves Rail, Right Tools Grid */}
        <div className="flex-1 grid grid-cols-[220px_1fr] min-h-0 divide-x divide-line">
          {/* Left: Shelves List */}
          <div className="overflow-y-auto p-2.5 space-y-1">
            <span className="text-2xs font-mono uppercase text-studio-500 px-2 py-1 block">
              Domain Shelves ({shelves.length})
            </span>
            {shelves.map((shelf) => {
              const isSelected = selectedShelf === shelf.shelf;
              return (
                <button
                  key={shelf.shelf}
                  onClick={() => setSelectedShelf(shelf.shelf)}
                  className={`w-full text-left px-2.5 py-2 rounded-lg text-xs font-medium flex items-center justify-between transition-all cursor-pointer ${
                    isSelected
                      ? "neu-selected !text-accent-300"
                      : "text-studio-400 hover:bg-studio-850 hover:text-studio-200 hover:shadow-neu-xs"
                  }`}
                >
                  <span className="truncate">{shelf.label}</span>
                  <span className="text-2xs font-mono opacity-60">({shelf.tools.length})</span>
                </button>
              );
            })}
          </div>

          {/* Right: Tools in Selected Shelf */}
          <div className="overflow-y-auto p-5 space-y-4">
            {actionNotice && <div role="status" className="mb-3 rounded-lg bg-studio-900 neu-raised-sm px-3 py-2 text-xs text-studio-300">{actionNotice}</div>}
            {isLoading ? (
              <p role="status" className="p-3 text-xs text-studio-400">Loading catalog shelves…</p>
            ) : catalogError ? (
              <div className="rounded-lg border border-status-error/30 bg-red-950/30 neu-inset p-4 text-xs text-studio-300">
                <p className="mb-3">{catalogError}</p>
                <Button size="xs" variant="secondary" onClick={() => void loadShelves()}>Retry</Button>
              </div>
            ) : activeShelf ? (
              <>
                <div className="flex items-center justify-between pb-2 border-b border-line">
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
                    const existingTool = findProjectTool(item);
                    const isAttached = !!selectedAgent && !!existingTool && selectedAgent.tool_ids?.includes(existingTool.id);
                    const isBusy = addingKey === `${item.kind}:${item.name.trim().toLowerCase()}`;

                    return (
                      <div
                        key={`${activeShelf.shelf}:${item.kind}:${item.name}`}
                        className="p-4 rounded-xl bg-studio-900 neu-raised-sm hover:shadow-neu transition-all flex flex-col justify-between space-y-3"
                      >
                        <div>
                          <div className="flex items-start justify-between gap-2">
                            <h4 className="text-xs font-semibold text-studio-100">
                              {item.name}
                            </h4>

                          </div>
                          <span className="text-2xs font-mono text-studio-500 block mt-0.5">
                            {item.kind}
                          </span>
                          <p className="text-2xs text-studio-400 mt-2 leading-relaxed">
                            {item.description}
                          </p>
                        </div>

                        <div className="pt-2 border-t border-line flex items-center justify-between">
                          <span className="text-2xs font-mono text-studio-500">
                            Shelf: {activeShelf.shelf}
                          </span>
                          <Button
                            size="xs"
                            variant={isAttached ? "secondary" : "primary"}
                            disabled={isAttached || isBusy || (!selectedAgent && !!existingTool)}
                            onClick={() => handleAddAndAttach(item)}
                          >
                            {isBusy
                              ? "Adding…"
                              : isAttached
                              ? "Already attached"
                              : existingTool && !selectedAgent
                              ? "In project"
                              : selectedAgent
                              ? existingTool ? "Attach to agent" : "+ Create & attach"
                              : "+ Add to project"}
                          </Button>
                        </div>
                      </div>
                    );
                  })}

                  {filteredTools.length === 0 && (
                    <div className="col-span-2 p-8 text-center text-studio-500 text-xs border border-dashed border-line rounded-md">
                      No tools match the filter query &ldquo;{searchQuery}&rdquo;.
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div className="rounded border border-dashed border-line p-8 text-center">
                <p className="text-xs font-medium text-studio-200">Video pack is disabled</p>
                <p className="mt-1 text-2xs text-studio-400">Enable Video pack above to browse video-production tools. It stays off by default.</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
