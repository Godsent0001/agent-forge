import { useState } from "react";
import { useStore } from "../store/useStore";
import { DEFAULT_MODELS } from "../config/models";

export function AgentEditor() {
  const agents = useStore((s) => s.agents);
  const tools = useStore((s) => s.tools);
  const selectedAgentId = useStore((s) => s.selectedAgentId);
  const updateAgent = useStore((s) => s.updateAgent);
  const attachToolToSelected = useStore((s) => s.attachToolToSelected);
  const detachToolFromAgent = useStore((s) => s.detachToolFromAgent);
  const attachChildToSelected = useStore((s) => s.attachChildToSelected);
  const detachChildFromAgent = useStore((s) => s.detachChildFromAgent);

  const selectedAgent = agents.find((a) => a.id === selectedAgentId);
  const [activeTab, setActiveTab] = useState<"general" | "prompt" | "tools" | "subagents">("general");

  if (!selectedAgent) {
    return (
      <div className="h-full flex items-center justify-center p-8 text-center bg-studio-950">
        <div>
          <div className="w-12 h-12 rounded-full bg-studio-900 border border-studio-700 flex items-center justify-center mx-auto mb-3 text-studio-400 text-lg">
            🔍
          </div>
          <h3 className="text-sm font-semibold text-studio-100 mb-1">No Agent Selected</h3>
          <p className="text-xs text-studio-400 max-w-xs">
            Select an agent from the explorer or canvas to inspect and edit configuration settings.
          </p>
        </div>
      </div>
    );
  }

  const handleProviderChange = (provider: "google" | "anthropic" | "openai") => {
    updateAgent(selectedAgent.id, {
      provider,
      model: DEFAULT_MODELS[provider],
    });
  };

  const attachedToolIds = selectedAgent.tool_ids || [];
  const unattachedTools = tools.filter((t) => !attachedToolIds.includes(t.id));
  const attachedTools = tools.filter((t) => attachedToolIds.includes(t.id));

  const childAgentIds = selectedAgent.child_agent_ids || [];
  const availableSubAgents = agents.filter(
    (a) => a.id !== selectedAgent.id && !childAgentIds.includes(a.id)
  );
  const attachedSubAgents = agents.filter((a) => childAgentIds.includes(a.id));

  return (
    <div className="h-full flex flex-col bg-studio-900 overflow-hidden text-xs">
      {/* Editor Inspector Header */}
      <div className="p-3 border-b border-studio-800 bg-studio-850 flex items-center justify-between">
        <div className="flex items-center gap-2 min-w-0">
          <span className="w-2 h-2 rounded-full bg-node-agent shrink-0" />
          <h2 className="font-semibold text-studio-100 text-sm truncate">{selectedAgent.name}</h2>
        </div>
        <span className="text-2xs font-mono uppercase bg-studio-800 text-studio-400 px-1.5 py-0.5 rounded border border-studio-700">
          Inspector
        </span>
      </div>

      {/* Sub-navigation Tabs */}
      <div className="flex border-b border-studio-800 bg-studio-950 px-2 gap-1">
        <button
          onClick={() => setActiveTab("general")}
          className={`px-3 py-2 font-medium border-b-2 transition-colors ${
            activeTab === "general"
              ? "border-accent-500 text-accent-400"
              : "border-transparent text-studio-400 hover:text-studio-200"
          }`}
        >
          General & Model
        </button>
        <button
          onClick={() => setActiveTab("prompt")}
          className={`px-3 py-2 font-medium border-b-2 transition-colors ${
            activeTab === "prompt"
              ? "border-accent-500 text-accent-400"
              : "border-transparent text-studio-400 hover:text-studio-200"
          }`}
        >
          System Prompt
        </button>
        <button
          onClick={() => setActiveTab("tools")}
          className={`px-3 py-2 font-medium border-b-2 transition-colors ${
            activeTab === "tools"
              ? "border-accent-500 text-accent-400"
              : "border-transparent text-studio-400 hover:text-studio-200"
          }`}
        >
          Tools ({attachedTools.length})
        </button>
        <button
          onClick={() => setActiveTab("subagents")}
          className={`px-3 py-2 font-medium border-b-2 transition-colors ${
            activeTab === "subagents"
              ? "border-accent-500 text-accent-400"
              : "border-transparent text-studio-400 hover:text-studio-200"
          }`}
        >
          Sub-Agents ({attachedSubAgents.length})
        </button>
      </div>

      {/* Form Area */}
      <div className="flex-1 overflow-auto p-4 space-y-4">
        {activeTab === "general" && (
          <div className="space-y-4 max-w-lg">
            <div>
              <label className="block text-2xs font-mono uppercase text-studio-400 mb-1">Agent Name</label>
              <input
                type="text"
                value={selectedAgent.name}
                onChange={(e) => updateAgent(selectedAgent.id, { name: e.target.value })}
                className="w-full bg-studio-800 text-studio-100 border border-studio-700 rounded px-3 py-1.5 focus:outline-none focus:border-accent-500"
              />
            </div>

            <div>
              <label className="block text-2xs font-mono uppercase text-studio-400 mb-1">Provider</label>
              <select
                value={selectedAgent.provider || "google"}
                onChange={(e) => handleProviderChange(e.target.value as any)}
                className="w-full bg-studio-800 text-studio-100 border border-studio-700 rounded px-3 py-1.5 focus:outline-none focus:border-accent-500"
              >
                <option value="google">Google Gemini</option>
                <option value="openai">OpenAI</option>
                <option value="anthropic">Anthropic Claude</option>
              </select>
            </div>

            <div>
              <label className="block text-2xs font-mono uppercase text-studio-400 mb-1">Model</label>
              <input
                type="text"
                value={selectedAgent.model}
                onChange={(e) => updateAgent(selectedAgent.id, { model: e.target.value })}
                className="w-full bg-studio-800 text-studio-100 border border-studio-700 rounded px-3 py-1.5 font-mono focus:outline-none focus:border-accent-500"
              />
            </div>
          </div>
        )}

        {activeTab === "prompt" && (
          <div className="h-full flex flex-col">
            <label className="block text-2xs font-mono uppercase text-studio-400 mb-1">
              System Instructions & Persona
            </label>
            <textarea
              value={selectedAgent.system_prompt || ""}
              onChange={(e) => updateAgent(selectedAgent.id, { system_prompt: e.target.value })}
              placeholder="Enter system instructions for this agent…"
              rows={12}
              className="w-full flex-1 bg-studio-800 text-studio-100 border border-studio-700 rounded p-3 font-mono text-xs focus:outline-none focus:border-accent-500 resize-none leading-relaxed"
            />
          </div>
        )}

        {activeTab === "tools" && (
          <div className="space-y-4">
            <div>
              <h4 className="text-2xs font-mono uppercase text-studio-400 mb-2">Attached Tools</h4>
              {attachedTools.length === 0 ? (
                <div className="p-3 text-center border border-dashed border-studio-800 rounded text-studio-500">
                  No tools attached to this agent.
                </div>
              ) : (
                <div className="space-y-1.5">
                  {attachedTools.map((t) => (
                    <div
                      key={t.id}
                      className="flex items-center justify-between p-2 rounded bg-studio-800 border border-studio-700"
                    >
                      <div className="flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-node-tool" />
                        <span className="font-semibold text-studio-100">{t.name}</span>
                        <span className="text-2xs font-mono text-studio-400">({t.kind})</span>
                      </div>
                      <button
                        onClick={() => detachToolFromAgent(selectedAgent.id, t.id)}
                        className="text-2xs text-status-error hover:underline px-2"
                      >
                        Detach
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {unattachedTools.length > 0 && (
              <div className="pt-3 border-t border-studio-800">
                <h4 className="text-2xs font-mono uppercase text-studio-400 mb-2">Available Tools</h4>
                <div className="space-y-1.5">
                  {unattachedTools.map((t) => (
                    <div
                      key={t.id}
                      className="flex items-center justify-between p-2 rounded bg-studio-850 border border-studio-800"
                    >
                      <span className="text-studio-300">{t.name}</span>
                      <button
                        onClick={() => attachToolToSelected(t.id)}
                        className="text-2xs text-accent-400 hover:text-accent-300 font-medium px-2"
                      >
                        + Attach
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === "subagents" && (
          <div className="space-y-4">
            <div>
              <h4 className="text-2xs font-mono uppercase text-studio-400 mb-2">Invokable Sub-Agents</h4>
              {attachedSubAgents.length === 0 ? (
                <div className="p-3 text-center border border-dashed border-studio-800 rounded text-studio-500">
                  No child sub-agents assigned.
                </div>
              ) : (
                <div className="space-y-1.5">
                  {attachedSubAgents.map((sa) => (
                    <div
                      key={sa.id}
                      className="flex items-center justify-between p-2 rounded bg-studio-800 border border-studio-700"
                    >
                      <div className="flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-node-agent" />
                        <span className="font-semibold text-studio-100">{sa.name}</span>
                      </div>
                      <button
                        onClick={() => detachChildFromAgent(selectedAgent.id, sa.id)}
                        className="text-2xs text-status-error hover:underline px-2"
                      >
                        Detach
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {availableSubAgents.length > 0 && (
              <div className="pt-3 border-t border-studio-800">
                <h4 className="text-2xs font-mono uppercase text-studio-400 mb-2">Available Sub-Agents</h4>
                <div className="space-y-1.5">
                  {availableSubAgents.map((sa) => (
                    <div
                      key={sa.id}
                      className="flex items-center justify-between p-2 rounded bg-studio-850 border border-studio-800"
                    >
                      <span className="text-studio-300">{sa.name}</span>
                      <button
                        onClick={() => attachChildToSelected(sa.id)}
                        className="text-2xs text-accent-400 hover:text-accent-300 font-medium px-2"
                      >
                        + Attach
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
