import { useState } from "react";
import { api } from "../api/client";
import { useStore } from "../store/useStore";
import { SettingsModal } from "./SettingsModal";

export function TopBar({ onRun }: { onRun: (executionId: string) => void }) {
  const project = useStore((s) => s.project);
  const selectedAgentId = useStore((s) => s.selectedAgentId);
  const agents = useStore((s) => s.agents);
  const [task, setTask] = useState("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const selectedAgent = agents.find((a) => a.id === selectedAgentId);

  const handleRun = async () => {
    if (!project || !selectedAgentId || !task.trim()) return;
    setRunning(true);
    setError(null);
    try {
      const execution = await api.executions.run(project.id, selectedAgentId, task.trim());
      onRun(execution.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start execution");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="h-14 shrink-0 border-b border-white/5 flex items-center gap-3 px-4 bg-surface-950">
      <span className="text-sm font-semibold text-neutral-200">
        {project?.name ?? "AgentForge"}
      </span>
      <span className="text-neutral-700">/</span>
      <span className="text-sm text-neutral-500">
        {selectedAgent ? selectedAgent.name : "no agent selected"}
      </span>

      <div className="flex-1" />

      <input
        value={task}
        onChange={(e) => setTask(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && handleRun()}
        placeholder="Task for the selected agent…"
        disabled={!selectedAgentId}
        className="w-80 bg-surface-800 border border-white/10 rounded-md px-3 py-1.5 text-sm
          placeholder:text-neutral-600 focus:outline-none focus:ring-1 focus:ring-accent-500
          disabled:opacity-40"
      />

      <button
        onClick={handleRun}
        disabled={!selectedAgentId || !task.trim() || running}
        className="text-sm px-4 py-1.5 rounded-md bg-accent-500 hover:bg-accent-400
          transition-colors duration-150 text-white disabled:opacity-40 disabled:pointer-events-none
          flex items-center gap-1.5"
      >
        {running ? "Running…" : "▶ Run"}
      </button>

      {error && <span className="text-xs text-status-error max-w-xs truncate">{error}</span>}

      <button
        onClick={() => setSettingsOpen(true)}
        title="API Keys"
        className="text-neutral-500 hover:text-neutral-300 transition-colors duration-150 text-sm px-1"
      >
        ⚙
      </button>

      {settingsOpen && <SettingsModal onClose={() => setSettingsOpen(false)} />}
    </div>
  );
}
