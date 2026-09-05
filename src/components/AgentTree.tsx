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

  const { roots, childrenOf } = buildForest(agents);

  const renderNode = (agent: Agent, depth: number) => {
    const children = childrenOf.get(agent.id) ?? [];
    const isSelected = agent.id === selectedAgentId;
    return (
      <div key={agent.id}>
        <button
          onClick={() => selectAgent(agent.id)}
          style={{ paddingLeft: `${12 + depth * 16}px` }}
          className={`w-full text-left py-1.5 pr-3 rounded-md text-sm flex items-center gap-2
            transition-colors duration-150
            ${isSelected ? "bg-accent-500/15 text-accent-300" : "text-neutral-300 hover:bg-white/5"}`}
        >
          <span className="text-xs opacity-60">🤖</span>
          <span className="truncate">{agent.name}</span>
        </button>
        {children.map((child) => renderNode(child, depth + 1))}
      </div>
    );
  };

  return (
    <div className="h-full flex flex-col border-r border-white/5 bg-surface-900">
      <div className="px-4 py-3 border-b border-white/5">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-neutral-500">
          Agents
        </h2>
      </div>

      <div className="flex-1 overflow-y-auto py-2">
        {roots.length === 0 && (
          <p className="px-4 py-6 text-sm text-neutral-500">No agents yet.</p>
        )}
        {roots.map((agent) => renderNode(agent, 0))}
      </div>

      <div className="p-3 border-t border-white/5 flex gap-2">
        <input
          value={newAgentName}
          onChange={(e) => setNewAgentName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && newAgentName.trim()) {
              createAgent(newAgentName.trim());
              setNewAgentName("");
            }
          }}
          placeholder="New agent name…"
          className="flex-1 bg-surface-800 border border-white/10 rounded-md px-2.5 py-1.5
            text-sm placeholder:text-neutral-600 focus:outline-none focus:ring-1 focus:ring-accent-500"
        />
      </div>

      <ToolLibrary />
    </div>
  );
}
