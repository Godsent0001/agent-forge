import { useState } from "react";
import { useStore } from "../store/useStore";

const PROVIDERS = ["anthropic", "openai", "google"] as const;

export function AgentEditor() {
  const selectedAgentId = useStore((s) => s.selectedAgentId);
  const agent = useStore((s) => s.agents.find((a) => a.id === s.selectedAgentId));
  const agents = useStore((s) => s.agents);
  const tools = useStore((s) => s.tools);
  const createAgent = useStore((s) => s.createAgent);
  const updateAgent = useStore((s) => s.updateAgent);
  const attachToolToSelected = useStore((s) => s.attachToolToSelected);
  const attachChildToSelected = useStore((s) => s.attachChildToSelected);

  const [linkError, setLinkError] = useState<string | null>(null);
  const [showAddChildModal, setShowAddChildModal] = useState(false);
  const [newChildName, setNewChildName] = useState("");

  if (!selectedAgentId || !agent) {
    return (
      <div className="h-full flex items-center justify-center text-slate-500 text-sm bg-surface-950">
        Select or create an agent to configure its properties and child agents.
      </div>
    );
  }

  const attachedToolIds = new Set(agent.tool_ids ?? []);
  const attachedChildIds = new Set(agent.child_agent_ids ?? []);
  const availableChildAgents = agents.filter(
    (a) => a.id !== agent.id && !attachedChildIds.has(a.id)
  );

  const handleAttachChild = async (childId: string) => {
    setLinkError(null);
    try {
      await attachChildToSelected(childId);
    } catch (e) {
      setLinkError(e instanceof Error ? e.message : "Failed to attach agent");
    }
  };

  const handleCreateAndAttachChild = async () => {
    if (!newChildName.trim()) return;
    setLinkError(null);
    try {
      // Create new agent then attach
      const { project } = useStore.getState();
      if (!project) return;

      await createAgent(newChildName.trim());
      // Re-select original parent agent and attach new child
      const state = useStore.getState();
      const created = state.agents.find((a) => a.name === newChildName.trim());
      state.selectAgent(agent.id);
      if (created) {
        await state.attachChildToSelected(created.id);
      }
      setNewChildName("");
      setShowAddChildModal(false);
    } catch (e) {
      setLinkError(e instanceof Error ? e.message : "Failed to create & attach child agent");
    }
  };

  return (
    <div className="h-full overflow-y-auto bg-surface-950 px-8 py-6 max-w-3xl mx-auto space-y-6">
      <div className="border-b border-slate-200 pb-4">
        <div className="flex items-center gap-2">
          <span className="text-2xl">🤖</span>
          <input
            value={agent.name}
            onChange={(e) => updateAgent(agent.id, { name: e.target.value })}
            className="text-2xl font-bold text-slate-800 bg-transparent focus:outline-none w-full
              border-b border-transparent focus:border-accent-500 pb-1"
          />
        </div>
        <input
          value={agent.description}
          onChange={(e) => updateAgent(agent.id, { description: e.target.value })}
          placeholder="Short description of this agent's goal…"
          className="mt-2 text-sm text-slate-500 bg-transparent focus:outline-none w-full"
        />
      </div>

      <Field label="Model Provider & Name">
        <div className="flex gap-2">
          <select
            value={agent.provider}
            onChange={(e) => updateAgent(agent.id, { provider: e.target.value })}
            className="bg-white border border-slate-300 rounded-md px-3 py-1.5 text-sm font-medium text-slate-800 shadow-sm focus:outline-none focus:ring-2 focus:ring-accent-500"
          >
            {PROVIDERS.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
          <input
            value={agent.model}
            onChange={(e) => updateAgent(agent.id, { model: e.target.value })}
            placeholder="e.g. claude-3-5-sonnet-20241022 or gpt-4o"
            className="flex-1 bg-white border border-slate-300 rounded-md px-3 py-1.5 text-sm text-slate-800 shadow-sm focus:outline-none focus:ring-2 focus:ring-accent-500"
          />
        </div>
      </Field>

      <Field label="Memory Engine">
        <label className="flex items-center gap-2 text-sm text-slate-700 font-medium">
          <input
            type="checkbox"
            checked={agent.memory_enabled}
            onChange={(e) => updateAgent(agent.id, { memory_enabled: e.target.checked })}
            className="w-4 h-4 accent-accent-500 rounded"
          />
          Retain memory & past context between execution tasks
        </label>
      </Field>

      <Field label="System Prompt" hint="Instructions, persona, and behavioral rules.">
        <textarea
          value={agent.system_prompt}
          onChange={(e) => updateAgent(agent.id, { system_prompt: e.target.value })}
          rows={4}
          className="w-full bg-white border border-slate-300 rounded-md px-3 py-2 text-sm
            font-mono text-slate-800 focus:outline-none focus:ring-2 focus:ring-accent-500 resize-none shadow-sm"
        />
      </Field>

      <Field label="Tool-Use Guidance" hint="Guidelines for tool selection and parameters.">
        <textarea
          value={agent.tool_use_schema}
          onChange={(e) => updateAgent(agent.id, { tool_use_schema: e.target.value })}
          rows={3}
          className="w-full bg-white border border-slate-300 rounded-md px-3 py-2 text-sm
            font-mono text-slate-800 focus:outline-none focus:ring-2 focus:ring-accent-500 resize-none shadow-sm"
        />
      </Field>

      <Field label="Attached Tools">
        <div className="flex flex-wrap gap-2">
          {tools.map((tool) => {
            const attached = attachedToolIds.has(tool.id);
            return (
              <button
                key={tool.id}
                disabled={attached}
                onClick={() => attachToolToSelected(tool.id)}
                className={`text-xs px-3 py-1.5 rounded-full border font-medium transition-all duration-150
                  ${attached
                    ? "border-accent-300 bg-accent-100 text-accent-500 shadow-sm"
                    : "border-slate-300 bg-white text-slate-600 hover:border-slate-400 hover:bg-slate-50"}`}
              >
                🔧 {tool.name}
              </button>
            );
          })}
          {tools.length === 0 && (
            <p className="text-sm text-slate-500">No tools available in project library.</p>
          )}
        </div>
      </Field>

      <Field label="Child Agents" hint="Child agents are sub-agents that this agent can delegate sub-tasks to.">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-slate-500">
            {attachedChildIds.size} child agent(s) attached
          </span>
          <button
            onClick={() => setShowAddChildModal(true)}
            className="text-xs bg-slate-100 hover:bg-slate-200 text-slate-700 font-medium px-2.5 py-1 rounded-md border border-slate-300 transition-colors flex items-center gap-1 shadow-sm"
          >
            <span>+</span> Attach / Create Child Agent
          </button>
        </div>

        <div className="flex flex-wrap gap-2 mb-2">
          {(agent.child_agent_ids ?? []).map((childId) => {
            const child = agents.find((a) => a.id === childId);
            return (
              <span key={childId} className="text-xs px-3 py-1.5 rounded-full font-medium
                border border-accent-300 bg-accent-100 text-accent-500 shadow-sm flex items-center gap-1">
                🤖 {child?.name ?? childId}
              </span>
            );
          })}
        </div>

        {showAddChildModal && (
          <div className="mt-3 p-4 rounded-lg bg-slate-50 border border-slate-300 shadow-card space-y-3">
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-600">
              Attach or Create Child Agent
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
              <p className="text-xs text-slate-500 mb-1.5">Or create a brand new child agent:</p>
              <div className="flex gap-2">
                <input
                  value={newChildName}
                  onChange={(e) => setNewChildName(e.target.value)}
                  placeholder="Child agent name (e.g. Code Reviewer)…"
                  className="flex-1 bg-white border border-slate-300 rounded-md px-3 py-1.5 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-accent-500 shadow-sm"
                />
                <button
                  onClick={handleCreateAndAttachChild}
                  className="bg-accent-500 hover:bg-accent-400 text-white text-xs px-3 py-1.5 rounded-md font-medium shadow-sm"
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

        {linkError && <p className="mt-2 text-xs text-status-error font-medium">{linkError}</p>}
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
      <div className="flex items-baseline justify-between mb-2">
        <label className="text-xs font-bold uppercase tracking-wider text-slate-600">
          {label}
        </label>
        {hint && <span className="text-xs text-slate-400">{hint}</span>}
      </div>
      {children}
    </div>
  );
}
