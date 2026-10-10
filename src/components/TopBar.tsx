import React, { useState } from "react";
import { useStore } from "../store/useStore";
import { SettingsModal } from "./SettingsModal";
import { ToolCatalogModal } from "./ToolCatalogModal";
import { SegmentedControl } from "./ui/SegmentedControl";
import { Button } from "./ui/Button";

interface TopBarProps {
  onRun?: (executionId: string) => void;
  activeTab?: "canvas" | "chat" | "config";
  onTabChange?: (tab: "canvas" | "chat" | "config") => void;
  onTriggerQuickRun?: () => void;
  isRunning?: boolean;
}

export function TopBar({
  activeTab = "canvas",
  onTabChange,
  onTriggerQuickRun,
  isRunning = false,
}: TopBarProps) {
  const project = useStore((s) => s.project);
  const projects = useStore((s) => s.projects);
  const agents = useStore((s) => s.agents);
  const selectedAgentId = useStore((s) => s.selectedAgentId);
  const switchProject = useStore((s) => s.switchProject);
  const createProject = useStore((s) => s.createProject);

  const [showSettings, setShowSettings] = useState(false);
  const [showToolCatalog, setShowToolCatalog] = useState(false);
  const [isCreatingProject, setIsCreatingProject] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const [isWorkflowActive, setIsWorkflowActive] = useState(true);

  const selectedAgent = agents.find((a) => a.id === selectedAgentId) || agents[0];

  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProjectName.trim()) return;
    await createProject(newProjectName.trim());
    setNewProjectName("");
    setIsCreatingProject(false);
  };

  return (
    <>
      <header className="h-12 bg-studio-900 border-b border-studio-700/80 px-4 flex items-center justify-between text-xs select-none shrink-0 z-30">
        {/* Left: Brand Identity & Breadcrumbs */}
        <div className="flex items-center gap-3 min-w-0">
          <div className="flex items-center gap-2 shrink-0">
            <div className="w-6 h-6 rounded bg-accent-600 flex items-center justify-center font-mono font-bold text-white text-xs shadow-studio">
              AF
            </div>
            <span className="font-semibold text-studio-100 tracking-tight text-sm hidden sm:inline">
              AgentForge
            </span>
          </div>

          <div className="h-4 w-px bg-studio-700 hidden sm:block" />

          {/* Breadcrumbs with Project Switcher */}
          <div className="flex items-center gap-1.5 text-studio-400 min-w-0">
            <span className="text-2xs font-mono uppercase text-studio-500 hidden md:inline">
              Workflows /
            </span>

            {isCreatingProject ? (
              <form onSubmit={handleCreateProject} className="flex items-center gap-1.5">
                <input
                  type="text"
                  value={newProjectName}
                  onChange={(e) => setNewProjectName(e.target.value)}
                  placeholder="New project name…"
                  className="bg-studio-800 text-studio-100 border border-studio-600 rounded px-2 py-0.5 text-xs focus:outline-none focus:border-accent-500"
                  autoFocus
                />
                <button type="submit" className="text-accent-400 hover:text-accent-300 font-semibold px-1">
                  Save
                </button>
                <button
                  type="button"
                  onClick={() => setIsCreatingProject(false)}
                  className="text-studio-400 hover:text-studio-200 px-1"
                >
                  Cancel
                </button>
              </form>
            ) : (
              <div className="flex items-center gap-1 min-w-0">
                <select
                  value={project?.id || ""}
                  onChange={(e) => switchProject(e.target.value)}
                  className="bg-studio-800 text-studio-100 border border-studio-700 rounded px-2 py-1 text-xs font-medium hover:border-studio-600 focus:outline-none focus:border-accent-500 transition-colors max-w-[160px] truncate"
                >
                  {projects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
                <button
                  onClick={() => setIsCreatingProject(true)}
                  className="p-1 text-studio-400 hover:text-studio-100 hover:bg-studio-800 rounded transition-colors"
                  title="Create new project"
                >
                  +
                </button>
              </div>
            )}

            {selectedAgent && (
              <span className="text-studio-400 hidden lg:inline truncate">
                / <strong className="text-studio-200 font-medium">{selectedAgent.name}</strong>
              </span>
            )}
          </div>
        </div>

        {/* Center: Segmented View Switcher (Editor / Executions / Test) */}
        <div className="flex items-center">
          <SegmentedControl
            options={[
              { value: "canvas", label: "Editor" },
              { value: "chat", label: "Test" },
              { value: "config", label: "Inspector" },
            ]}
            value={activeTab}
            onChange={(val) => onTabChange?.(val)}
            size="sm"
          />
        </div>

        {/* Right: Active Toggle, Catalog, Run Button, Settings */}
        <div className="flex items-center gap-2">
          {/* Active status toggle (Concept 1 style) */}
          <div className="hidden sm:flex items-center gap-1.5 px-2 py-1 rounded bg-studio-850 border border-studio-700/60">
            <button
              onClick={() => setIsWorkflowActive(!isWorkflowActive)}
              className={`w-7 h-4 rounded-full transition-colors relative cursor-pointer ${
                isWorkflowActive ? "bg-emerald-600" : "bg-studio-700"
              }`}
              title="Toggle Workflow Active state"
            >
              <span
                className={`absolute top-0.5 w-3 h-3 rounded-full bg-white transition-transform ${
                  isWorkflowActive ? "left-3.5" : "left-0.5"
                }`}
              />
            </button>
            <span className="text-2xs font-mono text-studio-300">
              {isWorkflowActive ? "Active" : "Paused"}
            </span>
          </div>

          {/* Quick Tool Catalog Button */}
          <Button
            size="xs"
            variant="secondary"
            onClick={() => setShowToolCatalog(true)}
            className="hidden md:inline-flex"
          >
            + Catalog
          </Button>

          {/* Primary Run Workflow Button */}
          <Button
            size="sm"
            variant="primary"
            onClick={onTriggerQuickRun}
            disabled={isRunning}
            icon={isRunning ? "⚙️" : "▶"}
          >
            {isRunning ? "Running…" : "Run Workflow"}
          </Button>

          {/* LLM Settings */}
          <button
            onClick={() => setShowSettings(true)}
            className="p-1.5 text-studio-400 hover:text-studio-100 hover:bg-studio-800 rounded-md transition-colors"
            title="Configure API Keys & Settings"
          >
            ⚙️
          </button>
        </div>
      </header>

      {showSettings && <SettingsModal onClose={() => setShowSettings(false)} />}
      {showToolCatalog && <ToolCatalogModal onClose={() => setShowToolCatalog(false)} />}
    </>
  );
}
