import React, { useState } from "react";
import { useStore } from "../store/useStore";

interface AgentTreeProps {
  onOpenConfig?: () => void;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
}

export function AgentTree({ onOpenConfig, isCollapsed, onToggleCollapse }: AgentTreeProps) {
  const agents = useStore((s) => s.agents);
  const tools = useStore((s) => s.tools);
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
      <div className="h-full w-12 bg-studio-900 border-r border-studio-700/80 flex flex-col items-center py-3 select-none">
        <button
          onClick={onToggleCollapse}
          className="p-1.5 text-studio-400 hover:text-studio-100 hover:bg-studio-800 rounded transition-colors"
          title="Expand Explorer"
        >
          ▶
        </button>
      </div>
    );
  }

  return (
    <div className="h-full w-full bg-studio-900 border-r border-studio-700/80 flex flex-col text-xs select-none min-w-0">
      {/* Explorer Header */}
      <div className="px-3 py-2.5 border-b border-studio-800 flex items-center justify-between">
        <span className="text-2xs font-mono font-semibold uppercase tracking-wider text-studio-400">
          Project Explorer
        </span>
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

      {/* Filter / Search Bar */}
      <div className="p-2 border-b border-studio-800">
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Filter agents & tools…"
          className="w-full bg-studio-800 text-studio-100 border border-studio-700/80 rounded px-2.5 py-1 text-2xs focus:outline-none focus:border-accent-500 transition-colors"
        />
      </div>

      {/* Scrollable Explorer List */}
      <div className="flex-1 overflow-auto p-2 space-y-4">
        {/* Agents Section */}
        <div>
          <div className="flex items-center justify-between mb-1.5 px-1">
            <span className="text-2xs font-mono font-semibold text-studio-500 uppercase">
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
            <form onSubmit={handleCreateAgent} className="mb-2 p-1.5 bg-studio-800 rounded border border-studio-700">
              <input
                type="text"
                value={newAgentName}
                onChange={(e) => setNewAgentName(e.target.value)}
                placeholder="Agent name…"
                className="w-full bg-studio-950 text-studio-100 border border-studio-600 rounded px-2 py-1 text-2xs mb-1.5 focus:outline-none focus:border-accent-500"
                autoFocus
              />
              <div className="flex justify-end gap-1">
                <button
                  type="button"
                  onClick={() => setIsCreatingAgent(false)}
                  className="px-2 py-0.5 text-2xs text-studio-400 hover:text-studio-200"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-2 py-0.5 text-2xs bg-accent-500 hover:bg-accent-400 text-white font-medium rounded"
                >
                  Create
                </button>
              </div>
            </form>
          )}

          {filteredAgents.length === 0 ? (
            <div className="p-3 text-center rounded border border-dashed border-studio-800 text-studio-500 text-2xs">
              No agents created.
            </div>
          ) : (
            <div className="space-y-0.5">
              {filteredAgents.map((agent) => {
                const isSelected = agent.id === selectedAgentId;
                return (
                  <div
                    key={agent.id}
                    onClick={() => selectAgent(agent.id)}
                    className={`flex items-center justify-between px-2 py-1.5 rounded cursor-pointer transition-colors group ${
                      isSelected
                        ? "bg-studio-800 text-white font-medium border border-studio-700"
                        : "text-studio-300 hover:bg-studio-850 hover:text-studio-100"
                    }`}
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="w-1.5 h-1.5 rounded-full bg-node-agent shrink-0" />
                      <span className="truncate">{agent.name}</span>
                    </div>

                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      {onOpenConfig && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            selectAgent(agent.id);
                            onOpenConfig();
                          }}
                          className="p-0.5 text-studio-400 hover:text-studio-100"
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
                        className="p-0.5 text-studio-400 hover:text-status-error"
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

        {/* Tools Section */}
        <div>
          <div className="flex items-center justify-between mb-1.5 px-1">
            <span className="text-2xs font-mono font-semibold text-studio-500 uppercase">
              Tools ({filteredTools.length})
            </span>
            <button
              onClick={() => setIsCreatingTool(true)}
              className="text-2xs font-mono text-accent-400 hover:text-accent-300 font-semibold px-1"
            >
              + New
            </button>
          </div>

          {isCreatingTool && (
            <form onSubmit={handleCreateTool} className="mb-2 p-1.5 bg-studio-800 rounded border border-studio-700">
              <input
                type="text"
                value={newToolName}
                onChange={(e) => setNewToolName(e.target.value)}
                placeholder="Tool name…"
                className="w-full bg-studio-950 text-studio-100 border border-studio-600 rounded px-2 py-1 text-2xs mb-1.5 focus:outline-none focus:border-accent-500"
                autoFocus
              />
              <div className="flex justify-end gap-1">
                <button
                  type="button"
                  onClick={() => setIsCreatingTool(false)}
                  className="px-2 py-0.5 text-2xs text-studio-400 hover:text-studio-200"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-2 py-0.5 text-2xs bg-accent-500 hover:bg-accent-400 text-white font-medium rounded"
                >
                  Create
                </button>
              </div>
            </form>
          )}

          {filteredTools.length === 0 ? (
            <div className="p-3 text-center rounded border border-dashed border-studio-800 text-studio-500 text-2xs">
              No custom tools.
            </div>
          ) : (
            <div className="space-y-0.5">
              {filteredTools.map((tool) => (
                <div
                  key={tool.id}
                  className="flex items-center justify-between px-2 py-1.5 rounded text-studio-300 hover:bg-studio-850 hover:text-studio-100 group"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="w-1.5 h-1.5 rounded-full bg-node-tool shrink-0" />
                    <span className="truncate">{tool.name}</span>
                  </div>
                  <button
                    onClick={() => deleteTool(tool.id)}
                    className="p-0.5 text-studio-400 hover:text-status-error opacity-0 group-hover:opacity-100 transition-opacity"
                    title="Delete Tool"
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
