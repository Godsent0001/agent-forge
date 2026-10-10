import React, { useState } from "react";
import { useStore } from "../store/useStore";
import { ToolCatalogModal } from "./ToolCatalogModal";
import { SettingsModal } from "./SettingsModal";

interface AgentTreeProps {
  onOpenConfig?: () => void;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
  onSelectExecution?: (execId: string) => void;
}

export function AgentTree({
  onOpenConfig,
  isCollapsed = false,
  onToggleCollapse,
  onSelectExecution: _onSelectExecution,
}: AgentTreeProps) {
  const agents = useStore((s) => s.agents);
  const tools = useStore((s) => s.tools);
  const project = useStore((s) => s.project);
  const selectedAgentId = useStore((s) => s.selectedAgentId);
  const selectAgent = useStore((s) => s.selectAgent);
  const createAgent = useStore((s) => s.createAgent);
  const deleteAgent = useStore((s) => s.deleteAgent);
  const createTool = useStore((s) => s.createTool);
  const deleteTool = useStore((s) => s.deleteTool);

  const [isCreatingAgent, setIsCreatingAgent] = useState(false);
  const [newAgentName, setNewAgentName] = useState("");
  const [isCreatingTool, setIsCreatingTool] = useState(false);
  const [newToolName, setNewToolName] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [showCatalogModal, setShowCatalogModal] = useState(false);
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [activeNavSection, setActiveNavSection] = useState<"workflows" | "tools" | "history">("workflows");

  const handleCreateAgent = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newAgentName.trim()) return;
    await createAgent(newAgentName.trim());
    setNewAgentName("");
    setIsCreatingAgent(false);
  };

  const handleCreateTool = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newToolName.trim()) return;
    await createTool(newToolName.trim(), "python");
    setNewToolName("");
    setIsCreatingTool(false);
  };

  const filteredAgents = agents.filter((a) =>
    a.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const filteredTools = tools.filter((t) =>
    t.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  if (isCollapsed) {
    return (
      <aside className="h-full w-12 bg-studio-900 border-r border-studio-700/80 flex flex-col items-center py-3 select-none justify-between shrink-0">
        <div className="flex flex-col items-center gap-3">
          <button
            onClick={onToggleCollapse}
            className="p-1.5 text-studio-400 hover:text-studio-100 hover:bg-studio-800 rounded transition-colors"
            title="Expand Project Explorer"
          >
            ▶
          </button>
          <div className="h-px w-6 bg-studio-800" />
          <button
            onClick={() => {
              onToggleCollapse?.();
              setActiveNavSection("workflows");
            }}
            className="p-2 text-studio-400 hover:text-accent-400 hover:bg-studio-800 rounded transition-colors"
            title="Workflows"
          >
            🤖
          </button>
          <button
            onClick={() => {
              onToggleCollapse?.();
              setActiveNavSection("tools");
            }}
            className="p-2 text-studio-400 hover:text-emerald-400 hover:bg-studio-800 rounded transition-colors"
            title="Node Library"
          >
            🧩
          </button>
        </div>

        <button
          onClick={() => setShowSettingsModal(true)}
          className="p-2 text-studio-400 hover:text-studio-100 hover:bg-studio-800 rounded transition-colors"
          title="Settings"
        >
          ⚙️
        </button>
      </aside>
    );
  }

  return (
    <aside className="h-full w-full bg-studio-900 border-r border-studio-700/80 flex flex-col text-xs select-none min-w-0">
      {/* Explorer Header */}
      <div className="px-3.5 py-3 border-b border-studio-800 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-accent-500" />
          <span className="font-semibold text-studio-100 text-xs tracking-tight">
            Project Explorer
          </span>
        </div>
        {onToggleCollapse && (
          <button
            onClick={onToggleCollapse}
            className="p-1 text-studio-400 hover:text-studio-100 hover:bg-studio-800 rounded transition-colors"
            title="Collapse Sidebar"
          >
            ◀
          </button>
        )}
      </div>

      {/* Nav Menu Items (Concept 1 style) */}
      <div className="p-2 border-b border-studio-800/80 space-y-0.5 shrink-0">
        <button
          onClick={() => setActiveNavSection("workflows")}
          className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded transition-colors font-medium text-xs ${
            activeNavSection === "workflows"
              ? "bg-studio-800 text-white border border-studio-700"
              : "text-studio-300 hover:bg-studio-850 hover:text-studio-100"
          }`}
        >
          <div className="flex items-center gap-2">
            <span className="text-accent-400">❖</span>
            <span>Workflows & Agents</span>
          </div>
          <span className="text-2xs font-mono text-studio-500">{agents.length}</span>
        </button>

        <button
          onClick={() => setActiveNavSection("tools")}
          className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded transition-colors font-medium text-xs ${
            activeNavSection === "tools"
              ? "bg-studio-800 text-white border border-studio-700"
              : "text-studio-300 hover:bg-studio-850 hover:text-studio-100"
          }`}
        >
          <div className="flex items-center gap-2">
            <span className="text-emerald-400">⊞</span>
            <span>Node Library</span>
          </div>
          <span className="text-2xs font-mono text-studio-500">{tools.length}</span>
        </button>

        <button
          onClick={() => setShowCatalogModal(true)}
          className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded text-studio-400 hover:bg-studio-850 hover:text-studio-200 transition-colors text-xs"
        >
          <span className="text-amber-400">📚</span>
          <span>Catalog Shelves (40+)</span>
        </button>

        <button
          onClick={() => setShowSettingsModal(true)}
          className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded text-studio-400 hover:bg-studio-850 hover:text-studio-200 transition-colors text-xs"
        >
          <span>⚙️</span>
          <span>LLM Provider Keys</span>
        </button>
      </div>

      {/* Filter / Search Bar */}
      <div className="p-2 border-b border-studio-800 shrink-0">
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Filter nodes…"
          className="w-full bg-studio-800 text-studio-100 placeholder:text-studio-500 border border-studio-700 rounded px-2.5 py-1 text-2xs focus:outline-none focus:border-accent-500 transition-colors"
        />
      </div>

      {/* Main List Section */}
      <div className="flex-1 overflow-y-auto p-2 space-y-4">
        {activeNavSection === "workflows" && (
          <div>
            <div className="flex items-center justify-between mb-1.5 px-1">
              <span className="text-2xs font-mono font-semibold text-studio-500 uppercase tracking-wider">
                Agents ({filteredAgents.length})
              </span>
              <button
                onClick={() => setIsCreatingAgent(true)}
                className="text-2xs font-mono text-accent-400 hover:text-accent-300 font-semibold px-1"
              >
                + New
              </button>
            </div>

            {isCreatingAgent && (
              <form onSubmit={handleCreateAgent} className="mb-2 p-2 bg-studio-800 rounded border border-studio-700">
                <input
                  type="text"
                  value={newAgentName}
                  onChange={(e) => setNewAgentName(e.target.value)}
                  placeholder="Agent name…"
                  className="w-full bg-studio-950 text-studio-100 border border-studio-600 rounded px-2 py-1 text-2xs mb-2 focus:outline-none focus:border-accent-500"
                  autoFocus
                />
                <div className="flex justify-end gap-1.5">
                  <button
                    type="button"
                    onClick={() => setIsCreatingAgent(false)}
                    className="px-2 py-0.5 text-2xs text-studio-400 hover:text-studio-200"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="px-2.5 py-0.5 text-2xs bg-accent-600 hover:bg-accent-500 text-white font-medium rounded shadow-studio"
                  >
                    Create
                  </button>
                </div>
              </form>
            )}

            {filteredAgents.length === 0 ? (
              <div className="p-3 text-center rounded border border-dashed border-studio-800 text-studio-500 text-2xs">
                No agents created yet.
              </div>
            ) : (
              <div className="space-y-0.5">
                {filteredAgents.map((agent) => {
                  const isSelected = agent.id === selectedAgentId;
                  const attachedCount = agent.tool_ids?.length || 0;

                  return (
                    <div
                      key={agent.id}
                      onClick={() => selectAgent(agent.id)}
                      className={`flex items-center justify-between px-2.5 py-2 rounded cursor-pointer transition-colors group ${
                        isSelected
                          ? "bg-studio-800 text-white font-medium border border-studio-700"
                          : "text-studio-300 hover:bg-studio-850 hover:text-studio-100"
                      }`}
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="w-2 h-2 rounded-full bg-node-agent shrink-0" />
                        <div className="min-w-0">
                          <span className="truncate block leading-tight">{agent.name}</span>
                          <span className="text-2xs font-mono text-studio-500 truncate block">
                            {agent.model} · {attachedCount} tools
                          </span>
                        </div>
                      </div>

                      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        {onOpenConfig && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              selectAgent(agent.id);
                              onOpenConfig();
                            }}
                            className="p-1 text-studio-400 hover:text-studio-100 rounded"
                            title="Configure Agent"
                          >
                            ⚙️
                          </button>
                        )}
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            deleteAgent(agent.id);
                          }}
                          className="p-1 text-studio-400 hover:text-status-error rounded"
                          title="Delete Agent"
                        >
                          ✕
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {activeNavSection === "tools" && (
          <div>
            <div className="flex items-center justify-between mb-1.5 px-1">
              <span className="text-2xs font-mono font-semibold text-studio-500 uppercase tracking-wider">
                Project Tools ({filteredTools.length})
              </span>
              <button
                onClick={() => setIsCreatingTool(true)}
                className="text-2xs font-mono text-emerald-400 hover:text-emerald-300 font-semibold px-1"
              >
                + Custom
              </button>
            </div>

            {isCreatingTool && (
              <form onSubmit={handleCreateTool} className="mb-2 p-2 bg-studio-800 rounded border border-studio-700">
                <input
                  type="text"
                  value={newToolName}
                  onChange={(e) => setNewToolName(e.target.value)}
                  placeholder="Tool name…"
                  className="w-full bg-studio-950 text-studio-100 border border-studio-600 rounded px-2 py-1 text-2xs mb-2 focus:outline-none focus:border-accent-500"
                  autoFocus
                />
                <div className="flex justify-end gap-1.5">
                  <button
                    type="button"
                    onClick={() => setIsCreatingTool(false)}
                    className="px-2 py-0.5 text-2xs text-studio-400 hover:text-studio-200"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="px-2.5 py-0.5 text-2xs bg-emerald-600 hover:bg-emerald-500 text-white font-medium rounded shadow-studio"
                  >
                    Add
                  </button>
                </div>
              </form>
            )}

            {filteredTools.length === 0 ? (
              <div className="p-3 text-center rounded border border-dashed border-studio-800 text-studio-500 text-2xs">
                No tools added.
              </div>
            ) : (
              <div className="space-y-0.5">
                {filteredTools.map((tool) => (
                  <div
                    key={tool.id}
                    className="flex items-center justify-between px-2.5 py-1.5 rounded text-studio-300 hover:bg-studio-850 hover:text-studio-100 group"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="w-1.5 h-1.5 rounded-full bg-node-tool shrink-0" />
                      <div className="min-w-0">
                        <span className="truncate block font-medium leading-tight">{tool.name}</span>
                        <span className="text-2xs font-mono text-emerald-400/90 truncate block">
                          {tool.kind}
                        </span>
                      </div>
                    </div>
                    <button
                      onClick={() => deleteTool(tool.id)}
                      className="p-1 text-studio-400 hover:text-status-error opacity-0 group-hover:opacity-100 transition-opacity"
                      title="Delete Tool"
                    >
                      ✕
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Explorer Footer (Concept 1 style) */}
      <div className="p-3 border-t border-studio-800 bg-studio-850/60 shrink-0 space-y-2">
        <div className="flex items-center justify-between text-2xs text-studio-400">
          <span className="truncate font-mono">{project?.name || "Active Workspace"}</span>
          <span className="text-emerald-400 font-mono">v1.0</span>
        </div>
        <button
          onClick={() => setIsCreatingAgent(true)}
          className="w-full py-1.5 px-3 bg-accent-600 hover:bg-accent-500 text-white text-xs font-semibold rounded shadow-studio transition-colors flex items-center justify-center gap-1.5 cursor-pointer"
        >
          <span>+</span> New Workflow Node
        </button>
      </div>

      {showCatalogModal && <ToolCatalogModal onClose={() => setShowCatalogModal(false)} />}
      {showSettingsModal && <SettingsModal onClose={() => setShowSettingsModal(false)} />}
    </aside>
  );
}
