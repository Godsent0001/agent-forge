import { useState, useRef, useEffect } from "react";
import { useStore } from "../store/useStore";
import { ToolLibrary } from "./ToolLibrary";
import type { Agent, Tool } from "../types";

export function AgentTree({ onOpenConfig }: { onOpenConfig?: () => void }) {
  const agents = useStore((s) => s.agents);
  const tools = useStore((s) => s.tools);
  const selectedAgentId = useStore((s) => s.selectedAgentId);
  const selectAgent = useStore((s) => s.selectAgent);
  const createAgent = useStore((s) => s.createAgent);
  const deleteAgent = useStore((s) => s.deleteAgent);
  const detachToolFromAgent = useStore((s) => s.detachToolFromAgent);
  const detachChildFromAgent = useStore((s) => s.detachChildFromAgent);

  const [expandedNodes, setExpandedNodes] = useState<Record<string, boolean>>({});
  const [activeMenu, setActiveMenu] = useState<{ id: string; type: "agent" | "subagent" | "tool"; parentId?: string } | null>(null);

  const [newAgentName, setNewAgentName] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const [feedbackMsg, setFeedbackMsg] = useState<string | null>(null);

  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setActiveMenu(null);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const toggleExpand = (id: string, e?: React.MouseEvent) => {
    e?.stopPropagation();
    setExpandedNodes((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const showFeedback = (msg: string) => {
    setFeedbackMsg(msg);
    setTimeout(() => setFeedbackMsg(null), 2500);
  };

  const handleCreateAgent = async () => {
    if (!newAgentName.trim()) return;
    const newAgent = await createAgent(newAgentName.trim());
    setNewAgentName("");
    setIsCreating(false);
    showFeedback(`Agent "${newAgent?.name ?? newAgentName}" created`);
  };

  const childIds = new Set<string>();
  for (const agent of agents) {
    for (const cid of agent.child_agent_ids ?? []) {
      childIds.add(cid);
    }
  }
  const roots = agents.filter((a) => !childIds.has(a.id));

  const renderAgentNode = (agent: Agent, depth: number, parentId?: string, ancestorPath: string[] = []) => {
    const isExpanded = expandedNodes[`${parentId || "root"}-${agent.id}`] ?? true;
    const isSelected = agent.id === selectedAgentId;
    const isSubAgent = !!parentId;

    const attachedTools = (agent.tool_ids ?? [])
      .map((tid) => tools.find((t) => t.id === tid))
      .filter((t): t is Tool => t !== undefined);

    const attachedChildren = (agent.child_agent_ids ?? [])
      .map((cid) => agents.find((a) => a.id === cid))
      .filter((a): a is Agent => a !== undefined);

    const hasChildren = attachedTools.length > 0 || attachedChildren.length > 0;
    const currentPath = [...ancestorPath, agent.id];

    return (
      <div key={`${parentId || "root"}-${agent.id}`} className="select-none">
        <div
          onClick={() => selectAgent(agent.id)}
          style={{ paddingLeft: `${8 + depth * 12}px` }}
          className={`group relative flex items-center justify-between py-1.5 pr-2 rounded-md text-xs cursor-pointer
            transition-all duration-150 my-0.5 border ${
              isSelected
                ? "bg-accent-100 text-accent-600 font-semibold border-accent-300/50 shadow-sm"
                : "text-slate-700 hover:bg-slate-100/80 border-transparent"
            }`}
        >
          <div
            onClick={(e) => {
              e.stopPropagation();
              selectAgent(agent.id);
            }}
            className="flex items-center gap-1.5 truncate min-w-0 pr-1"
          >
            <button
              onClick={(e) => toggleExpand(`${parentId || "root"}-${agent.id}`, e)}
              className={`p-0.5 rounded hover:bg-slate-200/60 text-slate-400 hover:text-slate-600 transition-transform ${
                hasChildren ? "" : "invisible"
              }`}
            >
              <svg
                className={`w-3 h-3 transition-transform duration-150 ${isExpanded ? "rotate-90" : ""}`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M9 5l7 7-7 7" />
              </svg>
            </button>

            <span className="text-sm shrink-0">🤖</span>
            <span className="truncate">{agent.name}</span>
            {isSubAgent && (
              <span className="text-[10px] px-1 py-0.2 rounded bg-slate-200/70 text-slate-600 font-sans shrink-0">
                sub
              </span>
            )}
          </div>

          <div className="flex items-center gap-1 shrink-0">
            {hasChildren && (
              <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-slate-200/80 text-slate-600 font-medium">
                {attachedTools.length + attachedChildren.length}
              </span>
            )}

            <button
              onClick={(e) => {
                e.stopPropagation();
                setActiveMenu(
                  activeMenu?.id === agent.id && activeMenu?.parentId === parentId
                    ? null
                    : { id: agent.id, type: isSubAgent ? "subagent" : "agent", parentId }
                );
              }}
              className="opacity-0 group-hover:opacity-100 focus:opacity-100 p-1 rounded hover:bg-slate-200/70 text-slate-500 hover:text-slate-700 transition-opacity"
              title="Options"
            >
              •••
            </button>
          </div>

          {/* Context 3-dot dropdown */}
          {activeMenu?.id === agent.id && activeMenu?.parentId === parentId && (
            <div
              ref={menuRef}
              className="absolute right-2 top-7 z-30 w-44 bg-white rounded-lg shadow-xl border border-slate-200 py-1 text-slate-700 text-xs animate-in fade-in zoom-in-95 duration-100"
              onClick={(e) => e.stopPropagation()}
            >
              <button
                onClick={() => {
                  selectAgent(agent.id);
                  onOpenConfig?.();
                  setActiveMenu(null);
                }}
                className="w-full text-left px-3 py-1.5 hover:bg-slate-100 flex items-center gap-2"
              >
                <span>⚙️</span> Edit Configuration
              </button>

              {isSubAgent && parentId && (
                <button
                  onClick={async () => {
                    await detachChildFromAgent(parentId, agent.id);
                    setActiveMenu(null);
                    showFeedback(`Sub-agent detached from parent`);
                  }}
                  className="w-full text-left px-3 py-1.5 hover:bg-slate-100 text-amber-600 flex items-center gap-2"
                >
                  <span>✂️</span> Detach from Parent
                </button>
              )}

              <div className="border-t border-slate-100 my-1" />

              <button
                onClick={async () => {
                  if (confirm(`Are you sure you want to delete agent "${agent.name}"?`)) {
                    await deleteAgent(agent.id);
                    setActiveMenu(null);
                    showFeedback(`Agent "${agent.name}" deleted`);
                  }
                }}
                className="w-full text-left px-3 py-1.5 hover:bg-red-50 text-red-600 flex items-center gap-2 font-medium"
              >
                <span>🗑️</span> Delete Agent
              </button>
            </div>
          )}
        </div>

        {/* Nested Child Items (Sub-agents & Tools) */}
        {isExpanded && hasChildren && (
          <div className="ml-1 border-l border-slate-200/80 pl-1 my-0.5 space-y-0.5">
            {attachedChildren.map((child) => {
              if (currentPath.includes(child.id)) {
                return null;
              }
              return renderAgentNode(child, depth + 1, agent.id, currentPath);
            })}

            {attachedTools.map((tool) => (
              <div
                key={`tool-${agent.id}-${tool.id}`}
                style={{ paddingLeft: `${8 + (depth + 1) * 12}px` }}
                className="group relative flex items-center justify-between py-1 pr-2 rounded text-xs text-slate-600 hover:bg-slate-100/70 transition-colors my-0.5"
              >
                <div className="flex items-center gap-1.5 truncate min-w-0">
                  <span className="text-xs text-amber-500 shrink-0">🔧</span>
                  <span className="truncate">{tool.name}</span>
                </div>

                <div className="flex items-center gap-1 shrink-0">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setActiveMenu(
                        activeMenu?.id === tool.id && activeMenu?.parentId === agent.id
                          ? null
                          : { id: tool.id, type: "tool", parentId: agent.id }
                      );
                    }}
                    className="opacity-0 group-hover:opacity-100 focus:opacity-100 p-0.5 rounded hover:bg-slate-200 text-slate-400 hover:text-slate-600"
                  >
                    •••
                  </button>
                </div>

                {/* Tool context menu */}
                {activeMenu?.id === tool.id && activeMenu?.parentId === agent.id && (
                  <div
                    ref={menuRef}
                    className="absolute right-2 top-6 z-30 w-44 bg-white rounded-lg shadow-xl border border-slate-200 py-1 text-slate-700 text-xs"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <button
                      onClick={async () => {
                        await detachToolFromAgent(agent.id, tool.id);
                        setActiveMenu(null);
                        showFeedback(`Tool "${tool.name}" detached`);
                      }}
                      className="w-full text-left px-3 py-1.5 hover:bg-slate-100 text-amber-600 flex items-center gap-2"
                    >
                      <span>✂️</span> Detach from Agent
                    </button>
                    <div className="border-t border-slate-100 my-1" />
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="h-full flex flex-col border-r border-slate-200 bg-surface-900 min-w-0">
      {/* Header */}
      <div className="px-3 py-2.5 border-b border-slate-200 flex items-center justify-between bg-slate-50/60 shrink-0">
        <h2 className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
          Explorer & Flow
        </h2>
        <button
          onClick={() => setIsCreating(true)}
          className="text-xs bg-accent-500 hover:bg-accent-400 text-white font-medium px-2 py-1 rounded-md transition-all shadow-sm flex items-center gap-1 active:scale-95 shrink-0"
        >
          <span>+</span> Create Agent
        </button>
      </div>

      {feedbackMsg && (
        <div className="mx-2 mt-2 px-2.5 py-1.5 bg-accent-100 border border-accent-300 text-accent-700 text-xs rounded-md shadow-sm transition-all animate-in fade-in">
          ✓ {feedbackMsg}
        </div>
      )}

      {/* Forest Tree Scroll Area */}
      <div className="flex-1 overflow-y-auto px-2 py-2 space-y-1 min-h-0">
        {roots.length === 0 && (
          <div className="px-4 py-8 text-center">
            <p className="text-xs text-slate-500 font-medium">No agents in this project.</p>
            <p className="text-[11px] text-slate-400 mt-1">Click "+ Create Agent" to build your flow.</p>
          </div>
        )}
        {roots.map((agent) => renderAgentNode(agent, 0))}
      </div>

      {/* Quick Agent Creator */}
      {isCreating && (
        <div className="p-2.5 border-t border-slate-200 bg-slate-50 flex flex-col gap-1.5 shrink-0">
          <span className="text-[11px] font-semibold text-slate-600">New Agent Name</span>
          <div className="flex gap-1">
            <input
              autoFocus
              value={newAgentName}
              onChange={(e) => setNewAgentName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleCreateAgent();
                if (e.key === "Escape") setIsCreating(false);
              }}
              placeholder="e.g. Code Reviewer"
              className="flex-1 min-w-0 bg-white border border-slate-300 rounded px-2 py-1
                text-xs text-slate-800 focus:outline-none focus:ring-1 focus:ring-accent-500 shadow-sm"
            />
            <button
              onClick={handleCreateAgent}
              className="bg-accent-500 hover:bg-accent-400 text-white text-xs px-2.5 py-1 rounded font-medium shadow-sm shrink-0"
            >
              Add
            </button>
            <button
              onClick={() => setIsCreating(false)}
              className="bg-slate-200 hover:bg-slate-300 text-slate-600 text-xs px-2 py-1 rounded shrink-0"
            >
              ✕
            </button>
          </div>
        </div>
      )}

      <ToolLibrary onFeedback={showFeedback} />
    </div>
  );
}
