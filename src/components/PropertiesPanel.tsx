import { useState } from "react";
import { useStore } from "../store/useStore";
import { DEFAULT_MODELS, Provider } from "../config/models";
import { Input, Textarea } from "./ui/Input";
import { Button } from "./ui/Button";

interface PropertiesPanelProps {
  onClose: () => void;
  onOpenToolCatalog: () => void;
}

export function PropertiesPanel({ onClose, onOpenToolCatalog }: PropertiesPanelProps) {
  const agents = useStore((s) => s.agents);
  const tools = useStore((s) => s.tools);
  const selectedAgentId = useStore((s) => s.selectedAgentId);
  const updateAgent = useStore((s) => s.updateAgent);
  const detachToolFromAgent = useStore((s) => s.detachToolFromAgent);
  const attachChildToSelected = useStore((s) => s.attachChildToSelected);
  const detachChildFromAgent = useStore((s) => s.detachChildFromAgent);

  const selectedAgent = agents.find((a) => a.id === selectedAgentId);
  const [activeTab, setActiveTab] = useState<"properties" | "prompt" | "tools" | "subagents">("properties");
  const [saveIndicator, setSaveIndicator] = useState<string>("Synced");

  if (!selectedAgent) {
    return (
      <aside className="w-84 h-full bg-studio-900 border-l border-studio-700/80 flex flex-col items-center justify-center p-6 text-center select-none shrink-0">
        <div className="w-10 h-10 rounded-full bg-studio-800 border border-studio-700 flex items-center justify-center text-studio-400 mb-2">
          ⚙️
        </div>
        <h3 className="text-xs font-semibold text-studio-200 mb-1">Properties Inspector</h3>
        <p className="text-2xs text-studio-500 max-w-xs leading-relaxed">
          Select any agent or node on the workflow canvas to configure its properties, models, and capabilities.
        </p>
      </aside>
    );
  }

  const handleProviderChange = (provider: Provider) => {
    updateAgent(selectedAgent.id, {
      provider,
      model: DEFAULT_MODELS[provider],
    });
    setSaveIndicator("Saved");
    setTimeout(() => setSaveIndicator("Synced"), 1500);
  };

  const handleFieldChange = (field: string, value: any) => {
    updateAgent(selectedAgent.id, { [field]: value });
    setSaveIndicator("Saved");
    setTimeout(() => setSaveIndicator("Synced"), 1500);
  };

  const attachedToolIds = selectedAgent.tool_ids || [];
  const attachedTools = tools.filter((t) => attachedToolIds.includes(t.id));
  const childAgentIds = selectedAgent.child_agent_ids || [];
  const availableSubAgents = agents.filter(
    (a) => a.id !== selectedAgent.id && !childAgentIds.includes(a.id)
  );
  const attachedSubAgents = agents.filter((a) => childAgentIds.includes(a.id));

  return (
    <aside className="w-full sm:w-84 h-full bg-studio-900 border-l border-studio-700/80 flex flex-col text-xs select-none shrink-0 overflow-hidden min-w-0 z-20">
      {/* Properties Header */}
      <div className="p-3 border-b border-studio-800 bg-studio-850 flex items-center justify-between">
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-semibold text-studio-100 text-xs">Properties</span>
          <span className="text-2xs font-mono text-accent-400 bg-studio-800 px-1.5 py-0.5 rounded border border-studio-700 truncate max-w-[120px]">
            ID: {selectedAgent.id.replace("agent-", "")}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-2xs font-mono text-studio-500">{saveIndicator}</span>
          <button
            onClick={onClose}
            className="p-1 text-studio-400 hover:text-studio-100 hover:bg-studio-800 rounded transition-colors"
            title="Close Inspector"
          >
            ✕
          </button>
        </div>
      </div>

      {/* Inspector Tabs */}
      <div className="flex border-b border-studio-800 bg-studio-950 px-2 gap-1 shrink-0">
        <button
          onClick={() => setActiveTab("properties")}
          className={`px-2.5 py-2 text-2xs font-mono uppercase tracking-wider border-b-2 transition-colors ${
            activeTab === "properties"
              ? "border-accent-500 text-accent-400 font-semibold"
              : "border-transparent text-studio-400 hover:text-studio-200"
          }`}
        >
          Config
        </button>
        <button
          onClick={() => setActiveTab("prompt")}
          className={`px-2.5 py-2 text-2xs font-mono uppercase tracking-wider border-b-2 transition-colors ${
            activeTab === "prompt"
              ? "border-accent-500 text-accent-400 font-semibold"
              : "border-transparent text-studio-400 hover:text-studio-200"
          }`}
        >
          Prompt
        </button>
        <button
          onClick={() => setActiveTab("tools")}
          className={`px-2.5 py-2 text-2xs font-mono uppercase tracking-wider border-b-2 transition-colors ${
            activeTab === "tools"
              ? "border-accent-500 text-accent-400 font-semibold"
              : "border-transparent text-studio-400 hover:text-studio-200"
          }`}
        >
          Tools ({attachedTools.length})
        </button>
        <button
          onClick={() => setActiveTab("subagents")}
          className={`px-2.5 py-2 text-2xs font-mono uppercase tracking-wider border-b-2 transition-colors ${
            activeTab === "subagents"
              ? "border-accent-500 text-accent-400 font-semibold"
              : "border-transparent text-studio-400 hover:text-studio-200"
          }`}
        >
          Sub-Agents ({attachedSubAgents.length})
        </button>
      </div>

      {/* Content Area */}
      <div className="flex-1 overflow-y-auto p-3 space-y-4">
        {activeTab === "properties" && (
          <div className="space-y-3.5">
            <div>
              <Input
                label="Node Name"
                value={selectedAgent.name}
                onChange={(e) => handleFieldChange("name", e.target.value)}
                placeholder="Agent name…"
              />
            </div>

            <div>
              <Textarea
                label="Description"
                rows={2}
                value={selectedAgent.description || ""}
                onChange={(e) => handleFieldChange("description", e.target.value)}
                placeholder="Autonomous agent role and purpose…"
              />
            </div>

            <div className="space-y-1">
              <label className="block text-2xs font-mono uppercase tracking-wider text-studio-400">
                LLM Provider
              </label>
              <select
                value={selectedAgent.provider || "google"}
                onChange={(e) => handleProviderChange(e.target.value as Provider)}
                className="w-full bg-studio-800 text-studio-100 border border-studio-700 rounded-md px-2.5 py-1.5 text-xs focus:outline-none focus:border-accent-500 transition-colors"
              >
                <option value="google">Google Gemini (Recommended)</option>
                <option value="openai">OpenAI</option>
                <option value="anthropic">Anthropic Claude</option>
              </select>
            </div>

            <div className="space-y-1">
              <label className="block text-2xs font-mono uppercase tracking-wider text-studio-400">
                Chat Model
              </label>
              <select
                value={selectedAgent.model || DEFAULT_MODELS[selectedAgent.provider as Provider] || "gemini-2.5-flash"}
                onChange={(e) => handleFieldChange("model", e.target.value)}
                className="w-full bg-studio-800 text-studio-100 border border-studio-700 rounded-md px-2.5 py-1.5 text-xs font-mono focus:outline-none focus:border-accent-500 transition-colors"
              >
                {selectedAgent.provider === "google" && (
                  <>
                    <option value="gemini-2.5-flash">gemini-2.5-flash (Fast & Reasoning)</option>
                    <option value="gemini-2.5-pro">gemini-2.5-pro (Deep Analytics)</option>
                  </>
                )}
                {selectedAgent.provider === "openai" && (
                  <>
                    <option value="gpt-4o-mini">gpt-4o-mini</option>
                    <option value="gpt-4o">gpt-4o</option>
                  </>
                )}
                {selectedAgent.provider === "anthropic" && (
                  <>
                    <option value="claude-haiku-4-5-20251001">claude-haiku-4-5</option>
                    <option value="claude-sonnet-4-5-20251001">claude-sonnet-4-5</option>
                  </>
                )}
              </select>
            </div>

            <div className="grid grid-cols-2 gap-2 pt-1">
              <div>
                <label className="block text-2xs font-mono uppercase tracking-wider text-studio-400 mb-1">
                  Max Iterations
                </label>
                <input
                  type="number"
                  defaultValue={10}
                  className="w-full bg-studio-800 text-studio-100 border border-studio-700 rounded px-2.5 py-1 text-xs font-mono"
                />
              </div>
              <div>
                <label className="block text-2xs font-mono uppercase tracking-wider text-studio-400 mb-1">
                  Memory Budget
                </label>
                <input
                  type="text"
                  defaultValue="50k tokens"
                  readOnly
                  className="w-full bg-studio-850 text-studio-400 border border-studio-800 rounded px-2.5 py-1 text-xs font-mono cursor-not-allowed"
                />
              </div>
            </div>

            <div className="pt-2 border-t border-studio-800 flex items-center justify-between">
              <div>
                <span className="block text-xs font-medium text-studio-200">Episodic Memory</span>
                <span className="text-2xs text-studio-500">Synthesize learned experience</span>
              </div>
              <input
                type="checkbox"
                checked={selectedAgent.memory_enabled ?? true}
                onChange={(e) => handleFieldChange("memory_enabled", e.target.checked)}
                className="w-4 h-4 accent-accent-500 rounded cursor-pointer"
              />
            </div>
          </div>
        )}

        {activeTab === "prompt" && (
          <div className="space-y-2 h-full flex flex-col">
            <label className="block text-2xs font-mono uppercase tracking-wider text-studio-400">
              System Instructions & Persona
            </label>
            <textarea
              value={selectedAgent.system_prompt || ""}
              onChange={(e) => handleFieldChange("system_prompt", e.target.value)}
              placeholder="Define agent instructions, tone, and step-by-step reasoning behavior…"
              className="w-full h-64 bg-studio-800 text-studio-100 border border-studio-700 rounded-md p-2.5 font-mono text-xs leading-relaxed focus:outline-none focus:border-accent-500 resize-none"
            />
            <p className="text-2xs text-studio-500">
              Tip: Explicitly define how the agent should structure tool calls and synthesize multi-agent findings.
            </p>
          </div>
        )}

        {activeTab === "tools" && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-2xs font-mono uppercase text-studio-400">
                Attached Tools ({attachedTools.length})
              </span>
              <Button size="xs" variant="primary" onClick={onOpenToolCatalog}>
                + Add from Catalog
              </Button>
            </div>

            {attachedTools.length === 0 ? (
              <div className="p-4 text-center border border-dashed border-studio-800 rounded-md text-studio-500 text-2xs">
                No tools attached yet. Attach tools from the catalog to empower this agent.
              </div>
            ) : (
              <div className="space-y-1.5">
                {attachedTools.map((t) => (
                  <div
                    key={t.id}
                    className="flex items-center justify-between p-2 rounded bg-studio-800/80 border border-studio-700/80 group"
                  >
                    <div className="min-w-0 pr-2">
                      <span className="font-medium text-studio-200 block truncate">{t.name}</span>
                      <span className="text-2xs font-mono text-emerald-400">{t.kind}</span>
                    </div>
                    <button
                      onClick={() => detachToolFromAgent(selectedAgent.id, t.id)}
                      className="text-2xs text-studio-500 hover:text-red-400 p-1 opacity-70 group-hover:opacity-100 transition-opacity"
                      title="Detach Tool"
                    >
                      Detach
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {activeTab === "subagents" && (
          <div className="space-y-3">
            <span className="text-2xs font-mono uppercase text-studio-400 block">
              Delegated Sub-Agents ({attachedSubAgents.length})
            </span>

            {attachedSubAgents.length === 0 ? (
              <div className="p-4 text-center border border-dashed border-studio-800 rounded-md text-studio-500 text-2xs">
                No sub-agents attached. Recursive sub-agents allow hierarchical delegation.
              </div>
            ) : (
              <div className="space-y-1.5">
                {attachedSubAgents.map((sa) => (
                  <div
                    key={sa.id}
                    className="flex items-center justify-between p-2 rounded bg-studio-800/80 border border-studio-700/80 group"
                  >
                    <div className="min-w-0 pr-2">
                      <span className="font-medium text-studio-200 block truncate">{sa.name}</span>
                      <span className="text-2xs font-mono text-blue-400">{sa.model}</span>
                    </div>
                    <button
                      onClick={() => detachChildFromAgent(selectedAgent.id, sa.id)}
                      className="text-2xs text-studio-500 hover:text-red-400 p-1 opacity-70 group-hover:opacity-100 transition-opacity"
                      title="Detach Sub-agent"
                    >
                      Detach
                    </button>
                  </div>
                ))}
              </div>
            )}

            {availableSubAgents.length > 0 && (
              <div className="pt-2 border-t border-studio-800 space-y-1.5">
                <span className="text-2xs font-mono text-studio-500 uppercase block">
                  Attach Available Agent
                </span>
                <div className="flex gap-1.5">
                  <select
                    id="subagent-select"
                    className="flex-1 bg-studio-800 text-studio-100 border border-studio-700 rounded px-2 py-1 text-xs"
                  >
                    {availableSubAgents.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.name}
                      </option>
                    ))}
                  </select>
                  <Button
                    size="xs"
                    variant="secondary"
                    onClick={() => {
                      const sel = document.getElementById("subagent-select") as HTMLSelectElement;
                      if (sel?.value) attachChildToSelected(sel.value);
                    }}
                  >
                    Attach
                  </Button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </aside>
  );
}
