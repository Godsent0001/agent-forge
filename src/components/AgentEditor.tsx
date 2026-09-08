import { useState, useEffect } from "react";
import { useStore } from "../store/useStore";

const PROVIDERS = ["anthropic", "openai", "google"] as const;

const MODEL_OPTIONS: Record<string, string[]> = {
  google: [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-3.1-flash-lite",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
  ],
  openai: [
    "gpt-4o",
    "gpt-4o-mini",
    "o3-mini",
    "o1",
  ],
  anthropic: [
    "claude-3-7-sonnet-20250219",
    "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku-20241022",
    "claude-3-opus-20240229",
  ],
};

export function AgentEditor() {
  const selectedAgentId = useStore((s) => s.selectedAgentId);
  const agent = useStore((s) => s.agents.find((a) => a.id === s.selectedAgentId));
  const agents = useStore((s) => s.agents);
  const tools = useStore((s) => s.tools);

  const updateAgent = useStore((s) => s.updateAgent);
  const createAgent = useStore((s) => s.createAgent);
  const attachToolToAgent = useStore((s) => s.attachToolToAgent);
  const detachToolFromAgent = useStore((s) => s.detachToolFromAgent);
  const attachChildToAgent = useStore((s) => s.attachChildToAgent);
  const detachChildFromAgent = useStore((s) => s.detachChildFromAgent);

  const [linkError, setLinkError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null);
  const [showAddChildModal, setShowAddChildModal] = useState(false);
  const [newChildName, setNewChildName] = useState("");

  // Form local state for smooth editing
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [provider, setProvider] = useState("anthropic");
  const [model, setModel] = useState("");
  const [memoryEnabled, setMemoryEnabled] = useState(false);
  const [systemPrompt, setSystemPrompt] = useState("");
  const [toolUseSchema, setToolUseSchema] = useState("");

  useEffect(() => {
    if (agent) {
      setName(agent.name ?? "");
      setDescription(agent.description ?? "");
      setProvider(agent.provider ?? "anthropic");
      setModel(agent.model ?? "");
      setMemoryEnabled(agent.memory_enabled ?? false);
      setSystemPrompt(agent.system_prompt ?? "");
      setToolUseSchema(agent.tool_use_schema ?? "");
      setSaveSuccess(null);
      setLinkError(null);
    }
  }, [agent?.id, agent?.updated_at]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!selectedAgentId || !agent) {
    return (
      <div className="h-full flex items-center justify-center text-slate-500 text-sm bg-surface-950 p-6">
        <div className="text-center max-w-sm space-y-2">
          <span className="text-3xl block">🤖</span>
          <p className="font-semibold text-slate-700">No Agent Selected</p>
          <p className="text-xs text-slate-500">
            Select or create an agent from the left sidebar to edit its model, tools, sub-agents, and prompts.
          </p>
        </div>
      </div>
    );
  }

  const attachedToolIds = new Set(agent.tool_ids ?? []);
  const attachedChildIds = new Set(agent.child_agent_ids ?? []);
  const availableChildAgents = agents.filter(
    (a) => a.id !== agent.id && !attachedChildIds.has(a.id)
  );

  const triggerSaveFeedback = (msg = "Configuration saved") => {
    setSaveSuccess(msg);
    setTimeout(() => setSaveSuccess(null), 2500);
  };

  const handleSaveAll = async () => {
    try {
      await updateAgent(agent.id, {
        name,
        description,
        provider,
        model,
        memory_enabled: memoryEnabled,
        system_prompt: systemPrompt,
        tool_use_schema: toolUseSchema,
      });
      triggerSaveFeedback("Configuration saved successfully!");
    } catch (e) {
      setLinkError(e instanceof Error ? e.message : "Failed to save configuration");
    }
  };

  const handleAttachChild = async (childId: string) => {
    setLinkError(null);
    try {
      await attachChildToAgent(agent.id, childId);
      triggerSaveFeedback("Sub-agent attached");
    } catch (e) {
      setLinkError(e instanceof Error ? e.message : "Failed to attach agent");
    }
  };

  const handleDetachChild = async (childId: string) => {
    setLinkError(null);
    try {
      await detachChildFromAgent(agent.id, childId);
      triggerSaveFeedback("Sub-agent detached");
    } catch (e) {
      setLinkError(e instanceof Error ? e.message : "Failed to detach agent");
    }
  };

  const handleAttachTool = async (toolId: string) => {
    setLinkError(null);
    try {
      await attachToolToAgent(agent.id, toolId);
      triggerSaveFeedback("Tool attached");
    } catch (e) {
      setLinkError(e instanceof Error ? e.message : "Failed to attach tool");
    }
  };

  const handleDetachTool = async (toolId: string) => {
    setLinkError(null);
    try {
      await detachToolFromAgent(agent.id, toolId);
      triggerSaveFeedback("Tool detached");
    } catch (e) {
      setLinkError(e instanceof Error ? e.message : "Failed to detach tool");
    }
  };

  const handleCreateAndAttachChild = async () => {
    if (!newChildName.trim()) return;
    setLinkError(null);
    try {
      const created = await createAgent(newChildName.trim());
      if (created) {
        await attachChildToAgent(agent.id, created.id);
      }
      setNewChildName("");
      setShowAddChildModal(false);
      triggerSaveFeedback(`Sub-agent "${newChildName.trim()}" created and attached`);
    } catch (e) {
      setLinkError(e instanceof Error ? e.message : "Failed to create & attach child agent");
    }
  };

  return (
    <div className="h-full overflow-y-auto bg-surface-950 px-6 py-6 max-w-3xl mx-auto space-y-6">
      {/* Header with Title & Save Button */}
      <div className="border-b border-slate-200 pb-4 flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-2xl shrink-0">🤖</span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Agent Name"
              className="text-xl font-bold text-slate-800 bg-transparent focus:outline-none w-full
                border-b border-slate-200 focus:border-accent-500 pb-0.5 transition-colors"
            />
          </div>
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Short description of this agent's goal…"
            className="mt-2 text-xs text-slate-500 bg-transparent focus:outline-none w-full"
          />
        </div>

        <button
          onClick={handleSaveAll}
          className="bg-accent-500 hover:bg-accent-400 active:scale-95 text-white font-bold text-xs px-4 py-2.5 rounded-lg shadow-sm transition-all shrink-0 flex items-center gap-1.5"
        >
          <span>💾</span> Save Changes
        </button>
      </div>

      {saveSuccess && (
        <div className="p-3 bg-emerald-50 border border-emerald-200 text-emerald-700 rounded-xl text-xs font-semibold flex items-center justify-between animate-in fade-in">
          <span>✓ {saveSuccess}</span>
        </div>
      )}

      {linkError && (
        <div className="p-3 bg-red-50 border border-red-200 text-red-600 rounded-xl text-xs font-semibold flex items-center justify-between">
          <span>⚠ {linkError}</span>
          <button onClick={() => setLinkError(null)} className="text-slate-400 hover:text-slate-600">✕</button>
        </div>
      )}

      {/* Settings Grid */}
      <Field label="Model Provider & Name">
        <div className="grid grid-cols-1 sm:grid-cols-[140px_1fr] gap-2">
          <select
            value={provider}
            onChange={(e) => {
              const newProvider = e.target.value;
              setProvider(newProvider);
              const defaultModels = MODEL_OPTIONS[newProvider];
              if (defaultModels && defaultModels.length > 0) {
                setModel(defaultModels[0]);
              }
            }}
            className="bg-white border border-slate-300 rounded-md px-3 py-1.5 text-xs font-semibold text-slate-800 shadow-sm focus:outline-none focus:ring-2 focus:ring-accent-500"
          >
            {PROVIDERS.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
          <div className="relative flex gap-2">
            <select
              value={MODEL_OPTIONS[provider]?.includes(model) ? model : "custom"}
              onChange={(e) => {
                if (e.target.value !== "custom") {
                  setModel(e.target.value);
                } else {
                  setModel("");
                }
              }}
              className="bg-white border border-slate-300 rounded-md px-3 py-1.5 text-xs font-medium text-slate-800 shadow-sm focus:outline-none focus:ring-2 focus:ring-accent-500 flex-1 min-w-0"
            >
              {(MODEL_OPTIONS[provider] || []).map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
              <option value="custom">Custom model name...</option>
            </select>
            {(!MODEL_OPTIONS[provider]?.includes(model) || model === "") && (
              <input
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder="Enter model name..."
                className="bg-white border border-slate-300 rounded-md px-3 py-1.5 text-xs text-slate-800 shadow-sm focus:outline-none focus:ring-2 focus:ring-accent-500 flex-1 min-w-0"
              />
            )}
          </div>
        </div>
      </Field>

      <Field label="Memory Engine">
        <label className="flex items-center gap-2.5 text-xs text-slate-700 font-medium cursor-pointer">
          <input
            type="checkbox"
            checked={memoryEnabled}
            onChange={(e) => setMemoryEnabled(e.target.checked)}
            className="w-4 h-4 accent-accent-500 rounded cursor-pointer"
          />
          <span>Enable memory retention & historical context across executions</span>
        </label>
      </Field>

      <Field label="System Prompt" hint="Persona, instructions, and rules for this agent.">
        <textarea
          value={systemPrompt}
          onChange={(e) => setSystemPrompt(e.target.value)}
          rows={4}
          placeholder="You are an expert software architecture agent..."
          className="w-full bg-white border border-slate-300 rounded-md px-3 py-2 text-xs
            font-mono text-slate-800 focus:outline-none focus:ring-2 focus:ring-accent-500 resize-y shadow-sm"
        />
      </Field>

      <Field label="Tool-Use Guidance" hint="Guidelines for tool selection and parameters.">
        <textarea
          value={toolUseSchema}
          onChange={(e) => setToolUseSchema(e.target.value)}
          rows={3}
          placeholder="Always verify file paths before running filesystem commands..."
          className="w-full bg-white border border-slate-300 rounded-md px-3 py-2 text-xs
            font-mono text-slate-800 focus:outline-none focus:ring-2 focus:ring-accent-500 resize-y shadow-sm"
        />
      </Field>

      {/* Tools Configuration */}
      <Field label="Attached Tools" hint="Select tools this agent is authorized to run.">
        <div className="flex flex-wrap gap-2">
          {tools.map((tool) => {
            const attached = attachedToolIds.has(tool.id);
            return (
              <div
                key={tool.id}
                className={`text-xs px-3 py-1.5 rounded-full border font-medium flex items-center gap-2 transition-all
                  ${attached
                    ? "border-accent-300 bg-accent-100 text-accent-700 shadow-sm"
                    : "border-slate-300 bg-white text-slate-600 hover:border-slate-400 hover:bg-slate-50"}`}
              >
                <span>🔧 {tool.name}</span>
                {attached ? (
                  <button
                    onClick={() => handleDetachTool(tool.id)}
                    className="hover:text-red-600 text-slate-400 font-bold ml-1"
                    title="Detach Tool"
                  >
                    ✕
                  </button>
                ) : (
                  <button
                    onClick={() => handleAttachTool(tool.id)}
                    className="hover:text-accent-600 text-accent-500 font-bold ml-1"
                    title="Attach Tool"
                  >
                    +
                  </button>
                )}
              </div>
            );
          })}
          {tools.length === 0 && (
            <p className="text-xs text-slate-400 italic">No tools available in project library.</p>
          )}
        </div>
      </Field>

      {/* Child Agents Configuration */}
      <Field label="Sub-Agents / Child Agents" hint="Sub-agents that this agent can delegate sub-tasks to recursively.">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-slate-500">
            {attachedChildIds.size} sub-agent(s) attached
          </span>
          <button
            onClick={() => setShowAddChildModal(true)}
            className="text-xs bg-slate-100 hover:bg-slate-200 text-slate-700 font-medium px-2.5 py-1 rounded-md border border-slate-300 transition-colors flex items-center gap-1 shadow-sm"
          >
            <span>+</span> Attach / Create Sub-Agent
          </button>
        </div>

        <div className="flex flex-wrap gap-2 mb-2">
          {Array.from(attachedChildIds).map((childId) => {
            const child = agents.find((a) => a.id === childId);
            return (
              <div
                key={childId}
                className="text-xs px-3 py-1.5 rounded-full font-medium border border-accent-300 bg-accent-100 text-accent-700 shadow-sm flex items-center gap-2"
              >
                <span>🤖 {child?.name ?? childId}</span>
                <button
                  onClick={() => handleDetachChild(childId)}
                  className="hover:text-red-600 text-slate-400 font-bold"
                  title="Detach Sub-Agent"
                >
                  ✕
                </button>
              </div>
            );
          })}
          {attachedChildIds.size === 0 && (
            <p className="text-xs text-slate-400 italic">No sub-agents attached yet.</p>
          )}
        </div>

        {showAddChildModal && (
          <div className="mt-3 p-4 rounded-lg bg-slate-50 border border-slate-300 shadow-card space-y-3">
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-600">
              Attach or Create Sub-Agent
            </h4>

            {availableChildAgents.length > 0 && (
              <div>
                <p className="text-xs text-slate-500 mb-1.5">Select existing agent to attach as child:</p>
                <div className="flex flex-wrap gap-2">
                  {availableChildAgents.map((candidate) => (
                    <button
                      key={candidate.id}
                      onClick={() => {
                        handleAttachChild(candidate.id);
                        setShowAddChildModal(false);
                      }}
                      className="text-xs px-3 py-1.5 rounded-md border border-slate-300 bg-white
                        text-slate-700 hover:border-accent-500 hover:text-accent-500 font-medium shadow-sm transition-all"
                    >
                      + {candidate.name}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="border-t border-slate-200 pt-3">
              <p className="text-xs text-slate-500 mb-1.5">Or create a brand new sub-agent:</p>
              <div className="flex gap-2">
                <input
                  value={newChildName}
                  onChange={(e) => setNewChildName(e.target.value)}
                  placeholder="Sub-agent name (e.g. Code Reviewer)…"
                  className="flex-1 min-w-0 bg-white border border-slate-300 rounded-md px-3 py-1.5 text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-accent-500 shadow-sm"
                />
                <button
                  onClick={handleCreateAndAttachChild}
                  className="bg-accent-500 hover:bg-accent-400 text-white text-xs px-3 py-1.5 rounded-md font-medium shadow-sm shrink-0"
                >
                  Create & Attach
                </button>
              </div>
            </div>

            <div className="flex justify-end">
              <button
                onClick={() => setShowAddChildModal(false)}
                className="text-xs text-slate-500 hover:text-slate-700"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </Field>
    </div>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-surface-900 border border-slate-200 rounded-xl p-4 shadow-sm">
      <div className="flex flex-wrap items-baseline justify-between mb-2 gap-1">
        <label className="text-[11px] font-bold uppercase tracking-wider text-slate-600">
          {label}
        </label>
        {hint && <span className="text-[11px] text-slate-400">{hint}</span>}
      </div>
      {children}
    </div>
  );
}
