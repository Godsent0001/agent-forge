import { useState } from "react";
import { useStore } from "../store/useStore";
import { ToolLibrary } from "./ToolLibrary";
import type { Agent } from "../types";

function buildForest(agents: Agent[]): { roots: Agent[]; childrenOf: Map<string, Agent[]> } {
  const childIds = new Set<string>();
  const childrenOf = new Map<string, Agent[]>();

  for (const agent of agents) {
    for (const childId of agent.child_agent_ids ?? []) {
      childIds.add(childId);
      const child = agents.find((a) => a.id === childId);
      if (child) {
        childrenOf.set(agent.id, [...(childrenOf.get(agent.id) ?? []), child]);
      }
    }
  }

  const roots = agents.filter((a) => !childIds.has(a.id));
  return { roots, childrenOf };
}

export function AgentTree() {
  const agents = useStore((s) => s.agents);
  const selectedAgentId = useStore((s) => s.selectedAgentId);
  const selectAgent = useStore((s) => s.selectAgent);
  const createAgent = useStore((s) => s.createAgent);

  const [newAgentName, setNewAgentName] = useState("");
  const [isCreating, setIsCreating] = useState(false);

  const { roots, childrenOf } = buildForest(agents);

  const handleCreateAgent = async () => {
    if (!newAgentName.trim()) return;
    await createAgent(newAgentName.trim());
    setNewAgentName("");
    setIsCreating(false);
  };

  const renderNode = (agent: Agent, depth: number) => {
    const children = childrenOf.get(agent.id) ?? [];
    const isSelected = agent.id === selectedAgentId;
    return (
      <div key={agent.id}>
        <button
          onClick={() => selectAgent(agent.id)}
          style={{ paddingLeft: `${12 + depth * 16}px` }}
          className={`w-full text-left py-2 pr-3 rounded-lg text-sm flex items-center justify-between gap-2
            transition-all duration-150 my-0.5
            ${isSelected
              ? "bg-accent-100 text-accent-500 font-medium shadow-sm border border-accent-300/40"
              : "text-slate-700 hover:bg-slate-100"}`}
        >
          <div className="flex items-center gap-2 truncate">
            <span className="text-base">🤖</span>
            <span className="truncate">{agent.name}</span>
          </div>
          {agent.child_agent_ids && agent.child_agent_ids.length > 0 && (
            <span className="text-xs px-1.5 py-0.5 rounded-full bg-slate-200/60 text-slate-600 font-sans shrink-0">
              {agent.child_agent_ids.length}
            </span>
          )}
        </button>
        {children.map((child) => renderNode(child, depth + 1))}
      </div>
    );
  };

  return (
    <div className="h-full flex flex-col border-r border-slate-200 bg-surface-900">
      <div className="px-4 py-3 border-b border-slate-200 flex items-center justify-between bg-slate-50/50">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
          Agents & Hierarchy
        </h2>
        <button
          onClick={() => setIsCreating(true)}
          className="text-xs bg-accent-500 hover:bg-accent-400 text-white font-medium px-2.5 py-1 rounded-md transition-colors shadow-sm flex items-center gap-1"
        >
          <span>+</span> Create Agent
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-2 py-2">
        {roots.length === 0 && (
          <div className="px-4 py-8 text-center">
            <p className="text-sm text-slate-500 font-medium">No agents in this project.</p>
            <p className="text-xs text-slate-400 mt-1">Click "+ Create Agent" to add your first agent.</p>
          </div>
        )}
        {roots.map((agent) => renderNode(agent, 0))}
      </div>

      {isCreating && (
        <div className="p-3 border-t border-slate-200 bg-slate-50 flex flex-col gap-2">
          <span className="text-xs font-semibold text-slate-600">New Agent Name</span>
          <div className="flex gap-1.5">
            <input
              autoFocus
              value={newAgentName}
              onChange={(e) => setNewAgentName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleCreateAgent();
                if (e.key === "Escape") setIsCreating(false);
              }}
              placeholder="e.g. Lead Researcher"
              className="flex-1 bg-white border border-slate-300 rounded-md px-2.5 py-1.5
                text-sm placeholder:text-slate-400 text-slate-800 focus:outline-none focus:ring-2 focus:ring-accent-500 shadow-sm"
            />
            <button
              onClick={handleCreateAgent}
              className="bg-accent-500 hover:bg-accent-400 text-white text-xs px-3 py-1.5 rounded-md font-medium shadow-sm"
            >
              Add
            </button>
            <button
              onClick={() => setIsCreating(false)}
              className="bg-slate-200 hover:bg-slate-300 text-slate-600 text-xs px-2 py-1.5 rounded-md"
            >
              ✕
            </button>
          </div>
        </div>
      )}

      <ToolLibrary />
    </div>
  );
}
