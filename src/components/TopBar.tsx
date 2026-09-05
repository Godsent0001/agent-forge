import { useState } from "react";
import { useStore } from "../store/useStore";
import { SettingsModal } from "./SettingsModal";

export function TopBar({
  activeTab,
  onTabChange,
}: {
  onRun?: (executionId: string) => void;
  activeTab: "chat" | "config";
  onTabChange: (tab: "chat" | "config") => void;
}) {
  const projects = useStore((s) => s.projects);
  const project = useStore((s) => s.project);
  const switchProject = useStore((s) => s.switchProject);
  const createProject = useStore((s) => s.createProject);
  const selectedAgentId = useStore((s) => s.selectedAgentId);
  const agents = useStore((s) => s.agents);

  const [settingsOpen, setSettingsOpen] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const [isCreatingProj, setIsCreatingProj] = useState(false);

  const selectedAgent = agents.find((a) => a.id === selectedAgentId);

  const handleCreateProject = async () => {
    if (!newProjectName.trim()) return;
    await createProject(newProjectName.trim());
    setNewProjectName("");
    setIsCreatingProj(false);
  };

  return (
    <div className="h-14 shrink-0 border-b border-slate-200 flex items-center justify-between px-4 bg-surface-900 shadow-sm">
      {/* Project selector dropdown */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <span className="font-bold text-slate-800 text-base">AgentForge</span>
          <span className="text-slate-300">/</span>
          <select
            value={project?.id ?? ""}
            onChange={(e) => e.target.value && switchProject(e.target.value)}
            className="bg-white border border-slate-300 text-slate-800 text-xs font-semibold rounded-md px-2.5 py-1 focus:outline-none focus:ring-2 focus:ring-accent-500 shadow-sm"
          >
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} {p.parallel_execution ? "(⚡ Parallel)" : "(Sequential)"}
              </option>
            ))}
          </select>

          {isCreatingProj ? (
            <div className="flex items-center gap-1">
              <input
                type="text"
                placeholder="New Project..."
                value={newProjectName}
                onChange={(e) => setNewProjectName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleCreateProject()}
                className="bg-white border border-slate-300 text-xs text-slate-800 px-2 py-1 rounded w-32 focus:outline-none shadow-sm"
              />
              <button
                onClick={handleCreateProject}
                className="bg-accent-500 text-white text-xs px-2 py-1 rounded hover:bg-accent-400 font-medium"
              >
                Add
              </button>
              <button
                onClick={() => setIsCreatingProj(false)}
                className="text-slate-400 hover:text-slate-600 text-xs px-1"
              >
                ✕
              </button>
            </div>
          ) : (
            <button
              onClick={() => setIsCreatingProj(true)}
              title="Create New Project"
              className="text-slate-600 hover:text-slate-800 text-xs font-medium px-2 py-1 bg-white border border-slate-300 rounded hover:bg-slate-50 shadow-sm"
            >
              + New
            </button>
          )}
        </div>

        <span className="text-slate-300">/</span>
        <span className="text-xs font-semibold text-slate-600">
          {selectedAgent ? selectedAgent.name : "No Agent Selected"}
        </span>
      </div>

      {/* Mode Switcher: Agent Chat vs Agent Config */}
      <div className="flex items-center bg-slate-100 p-1 rounded-lg border border-slate-200">
        <button
          onClick={() => onTabChange("chat")}
          className={`text-xs font-bold px-3 py-1 rounded-md transition-all ${
            activeTab === "chat"
              ? "bg-white text-accent-500 shadow-sm"
              : "text-slate-600 hover:text-slate-800"
          }`}
        >
          💬 Agent Chat
        </button>
        <button
          onClick={() => onTabChange("config")}
          className={`text-xs font-bold px-3 py-1 rounded-md transition-all ${
            activeTab === "config"
              ? "bg-white text-accent-500 shadow-sm"
              : "text-slate-600 hover:text-slate-800"
          }`}
        >
          ⚙ Agent Config
        </button>
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={() => setSettingsOpen(true)}
          title="API Keys & Settings"
          className="text-slate-500 hover:text-slate-800 transition-colors text-sm px-2 py-1 rounded hover:bg-slate-100"
        >
          ⚙ Settings
        </button>
      </div>

      {settingsOpen && <SettingsModal onClose={() => setSettingsOpen(false)} />}
    </div>
  );
}
