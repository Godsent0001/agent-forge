import { useState } from "react";
import { useStore } from "../store/useStore";
import { ModelPicker } from "./ModelPicker";
import { Input, Textarea } from "./ui/Input";
import type { InputProps, TextareaProps } from "./ui/Input";
import { Button } from "./ui/Button";
import { Icon } from "./ui/Icon";
import { useDraft } from "../hooks/useDraft";
import type { Agent } from "../types";
import { AgentMemoryPanel } from "./AgentMemoryPanel";

type DraftProps = { value: string; onCommit: (next: string) => void };

function DraftInput({ value, onCommit, ...props }: DraftProps & Omit<InputProps, "value" | "onChange">) {
  const draft = useDraft(value, onCommit);
  return <Input {...props} value={draft.value} onChange={(e) => draft.onChange(e.target.value)} onBlur={draft.flush} />;
}

function DraftTextarea({ value, onCommit, ...props }: DraftProps & Omit<TextareaProps, "value" | "onChange">) {
  const draft = useDraft(value, onCommit);
  return <Textarea {...props} value={draft.value} onChange={(e) => draft.onChange(e.target.value)} onBlur={draft.flush} />;
}

type SaveState = "Synced" | "Saving…" | "Saved" | "Save failed";

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
  const [activeTab, setActiveTab] = useState<"properties" | "prompt" | "tools" | "subagents" | "memory" | "lessons">("properties");
  const [saveIndicator, setSaveIndicator] = useState<SaveState>("Synced");

  if (!selectedAgent) {
    return (
      <aside className="w-full h-full bg-studio-900 border-l border-studio-700/80 flex flex-col items-center justify-center p-6 text-center select-none shrink-0">
        <div className="w-10 h-10 rounded-full bg-studio-800 border border-studio-700 flex items-center justify-center text-studio-400 mb-2">
          <Icon name="settings" size={18} />
        </div>
        <h3 className="text-xs font-semibold text-studio-200 mb-1">Agent setup</h3>
        <p className="text-2xs text-studio-500 max-w-xs leading-relaxed">
          Select an agent from the explorer to configure its model, instructions, tools, and delegation.
        </p>
      </aside>
    );
  }

  const persist = async (patch: Partial<Agent>) => {
    setSaveIndicator("Saving…");
    try {
      await updateAgent(selectedAgent.id, patch);
      setSaveIndicator("Saved");
      setTimeout(() => setSaveIndicator((current) => (current === "Saved" ? "Synced" : current)), 1500);
    } catch {
      setSaveIndicator("Save failed");
    }
  };

  const handleFieldChange = (field: keyof Agent, value: Agent[keyof Agent]) => {
    void persist({ [field]: value } as Partial<Agent>);
  };

  const attachedToolIds = selectedAgent.tool_ids || [];
  const attachedTools = tools.filter((t) => attachedToolIds.includes(t.id));
  const childAgentIds = selectedAgent.child_agent_ids || [];
  const availableSubAgents = agents.filter(
    (a) => a.id !== selectedAgent.id && !childAgentIds.includes(a.id)
  );
  const attachedSubAgents = agents.filter((a) => childAgentIds.includes(a.id));

  return (
    <aside className="w-full h-full bg-studio-900 border-l border-studio-700/80 flex flex-col text-xs select-none shrink-0 overflow-hidden min-w-0 z-20">
      {/* Properties Header */}
      <div className="p-3 border-b border-studio-800 bg-studio-850 flex items-center justify-between">
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-semibold text-studio-100 text-xs">Agent settings</span>
          <span className="text-2xs font-mono text-accent-400 bg-studio-800 px-1.5 py-0.5 rounded border border-studio-700 truncate max-w-[120px]">
            ID: {selectedAgent.id.replace("agent-", "")}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span role="status" className={`text-2xs font-mono ${saveIndicator === "Save failed" ? "text-red-400" : "text-studio-500"}`}>{saveIndicator}</span>
          <button
            onClick={onClose}
            className="p-1 text-studio-400 hover:text-studio-100 hover:bg-studio-800 rounded transition-colors"
            title="Close inspector"
            aria-label="Close inspector"
          >
            <Icon name="close" size={14} />
          </button>
        </div>
      </div>

      {/* Inspector Tabs */}
      <div role="tablist" aria-label="Agent settings sections" className="flex shrink-0 gap-0.5 overflow-x-auto border-b border-studio-800 bg-studio-950 px-2">
        {([
          { id: "properties", label: "Setup" },
          { id: "prompt", label: "Instructions" },
          { id: "tools", label: "Tools", count: attachedTools.length },
          { id: "subagents", label: "Delegation", count: attachedSubAgents.length },
          { id: "memory", label: "Memory" },
          { id: "lessons", label: "Lessons" },
        ] as const).map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={activeTab === tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`shrink-0 whitespace-nowrap border-b-2 px-2 py-2 text-xs font-medium transition-colors ${
              activeTab === tab.id
                ? "border-accent-500 text-accent-400"
                : "border-transparent text-studio-400 hover:text-studio-200"
            }`}
          >
            {tab.label}
            {"count" in tab && (
              <span className="ml-1.5 rounded bg-studio-800 px-1 font-mono text-2xs text-studio-400">{tab.count}</span>
            )}
          </button>
        ))}
      </div>

      {/* Content Area */}
      <div className="flex-1 overflow-y-auto p-3 space-y-4">
        {activeTab === "properties" && (
          <div className="space-y-3.5">
            <div>
              <DraftInput
                key={`name-${selectedAgent.id}`}
                label="Node Name"
                value={selectedAgent.name}
                onCommit={(next) => handleFieldChange("name", next)}
                placeholder="Agent name…"
              />
            </div>

            <div>
              <DraftTextarea
                key={`desc-${selectedAgent.id}`}
                label="Description"
                rows={2}
                value={selectedAgent.description || ""}
                onCommit={(next) => handleFieldChange("description", next)}
                placeholder="Autonomous agent role and purpose…"
              />
            </div>

            <ModelPicker
              key={`model-${selectedAgent.id}`}
              provider={selectedAgent.provider}
              model={selectedAgent.model}
              onChange={(patch) => void persist(patch)}
            />

          </div>
        )}

        {(activeTab === "memory" || activeTab === "lessons") && (
          <AgentMemoryPanel key={`${selectedAgent.id}-${activeTab}`} agent={selectedAgent} section={activeTab} />
        )}

        {activeTab === "prompt" && (
          <div className="space-y-2 h-full flex flex-col">
            <DraftTextarea
              key={`prompt-${selectedAgent.id}`}
              label="System instructions & persona"
              value={selectedAgent.system_prompt || ""}
              onCommit={(next) => handleFieldChange("system_prompt", next)}
              placeholder="Define agent instructions, tone, and step-by-step reasoning behavior…"
              className="h-64 leading-relaxed"
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
