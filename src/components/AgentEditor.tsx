import { useState } from "react";
import { useStore } from "../store/useStore";

const PROVIDERS = ["anthropic", "openai", "google"] as const;

export function AgentEditor() {
  const selectedAgentId = useStore((s) => s.selectedAgentId);
  const agent = useStore((s) => s.agents.find((a) => a.id === s.selectedAgentId));
  const agents = useStore((s) => s.agents);
  const tools = useStore((s) => s.tools);
  const updateAgent = useStore((s) => s.updateAgent);
  const attachToolToSelected = useStore((s) => s.attachToolToSelected);
  const attachChildToSelected = useStore((s) => s.attachChildToSelected);
  const [linkError, setLinkError] = useState<string | null>(null);

  if (!selectedAgentId || !agent) {
    return (
      <div className="h-full flex items-center justify-center text-neutral-600 text-sm">
        Select or create an agent to configure it.
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

  return (
    <div className="h-full overflow-y-auto px-8 py-6 max-w-2xl mx-auto space-y-6">
      <div>
        <input
          value={agent.name}
          onChange={(e) => updateAgent(agent.id, { name: e.target.value })}
          className="text-xl font-semibold bg-transparent focus:outline-none w-full
            border-b border-transparent focus:border-white/10 pb-1"
        />
        <input
          value={agent.description}
          onChange={(e) => updateAgent(agent.id, { description: e.target.value })}
          placeholder="Short description…"
          className="mt-1 text-sm text-neutral-500 bg-transparent focus:outline-none w-full"
        />
      </div>

      <Field label="Model">
        <div className="flex gap-2">
          <select
            value={agent.provider}
            onChange={(e) => updateAgent(agent.id, { provider: e.target.value })}
            className="bg-surface-800 border border-white/10 rounded-md px-2.5 py-1.5 text-sm"
          >
            {PROVIDERS.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
          <input
            value={agent.model}
            onChange={(e) => updateAgent(agent.id, { model: e.target.value })}
            placeholder="model id…"
            className="flex-1 bg-surface-800 border border-white/10 rounded-md px-2.5 py-1.5 text-sm"
          />
        </div>
      </Field>

      <Field label="Memory">
        <label className="flex items-center gap-2 text-sm text-neutral-300">
          <input
            type="checkbox"
            checked={agent.memory_enabled}
            onChange={(e) => updateAgent(agent.id, { memory_enabled: e.target.checked })}
            className="accent-accent-500"
          />
          Retain memory between executions
        </label>
      </Field>

      <Field label="System Prompt" hint="Who this agent is and how it behaves.">
        <textarea
          value={agent.system_prompt}
          onChange={(e) => updateAgent(agent.id, { system_prompt: e.target.value })}
          rows={4}
          className="w-full bg-surface-800 border border-white/10 rounded-md px-3 py-2 text-sm
            font-mono focus:outline-none focus:ring-1 focus:ring-accent-500 resize-none"
        />
      </Field>

      <Field label="Tool-Use Schema" hint="How this agent should decide to use its tools.">
        <textarea
          value={agent.tool_use_schema}
          onChange={(e) => updateAgent(agent.id, { tool_use_schema: e.target.value })}
          rows={3}
          className="w-full bg-surface-800 border border-white/10 rounded-md px-3 py-2 text-sm
            font-mono focus:outline-none focus:ring-1 focus:ring-accent-500 resize-none"
        />
      </Field>

      <Field label="Tools">
        <div className="flex flex-wrap gap-2">
          {tools.map((tool) => {
            const attached = attachedToolIds.has(tool.id);
            return (
              <button
                key={tool.id}
                disabled={attached}
                onClick={() => attachToolToSelected(tool.id)}
                className={`text-xs px-2.5 py-1 rounded-full border transition-colors duration-150
                  ${attached
                    ? "border-accent-500/40 bg-accent-500/10 text-accent-300"
                    : "border-white/10 text-neutral-400 hover:border-white/20"}`}
              >
                🔧 {tool.name}
              </button>
            );
          })}
          {tools.length === 0 && (
            <p className="text-sm text-neutral-600">No tools yet — add some in the Tool Library.</p>
          )}
        </div>
      </Field>

      <Field label="Child Agents" hint="Agents attached here become tools this agent can delegate to.">
        <div className="flex flex-wrap gap-2 mb-2">
          {(agent.child_agent_ids ?? []).map((childId) => {
            const child = agents.find((a) => a.id === childId);
            return (
              <span key={childId} className="text-xs px-2.5 py-1 rounded-full
                border border-accent-500/40 bg-accent-500/10 text-accent-300">
                🤖 {child?.name ?? childId}
              </span>
            );
          })}
        </div>
        <div className="flex flex-wrap gap-2">
          {availableChildAgents.map((candidate) => (
            <button
              key={candidate.id}
              onClick={() => handleAttachChild(candidate.id)}
              className="text-xs px-2.5 py-1 rounded-full border border-white/10
                text-neutral-400 hover:border-white/20 transition-colors duration-150"
            >
              + {candidate.name}
            </button>
          ))}
        </div>
        {linkError && <p className="mt-2 text-xs text-status-error">{linkError}</p>}
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
    <div>
      <div className="flex items-baseline justify-between mb-1.5">
        <label className="text-xs font-semibold uppercase tracking-wide text-neutral-500">
          {label}
        </label>
        {hint && <span className="text-xs text-neutral-600">{hint}</span>}
      </div>
      {children}
    </div>
  );
}
