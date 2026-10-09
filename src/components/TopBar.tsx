import React, { useState } from "react";
import { useStore } from "../store/useStore";
import { SettingsModal } from "./SettingsModal";
import { ToolCatalogModal } from "./ToolCatalogModal";

interface TopBarProps {
  onRun?: (executionId: string) => void;
  activeTab?: "chat" | "config" | "canvas";
  onTabChange?: (tab: "chat" | "config" | "canvas") => void;
}

export function TopBar({ activeTab = "chat", onTabChange }: TopBarProps) {
  const project = useStore((s) => s.project);
  const projects = useStore((s) => s.projects);
  const switchProject = useStore((s) => s.switchProject);
  const createProject = useStore((s) => s.createProject);
  const [showSettings, setShowSettings] = useState(false);
  const [showToolCatalog, setShowToolCatalog] = useState(false);
  const [isCreatingProject, setIsCreatingProject] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");

  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProjectName.trim()) return;
    await createProject(newProjectName.trim());
    setNewProjectName("");
    setIsCreatingProject(false);
  };

  return (
    <>
      <header className="h-12 bg-studio-900 border-b border-studio-700/80 px-4 flex items-center justify-between text-xs select-none">
        {/* Left: Brand Identity & Project Selector */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 rounded bg-accent-500 flex items-center justify-center font-mono font-bold text-white text-2xs shadow-studio">
              AF
            </div>
            <span className="font-semibold text-studio-100 tracking-tight">AgentForge</span>
          </div>

          <div className="h-4 w-px bg-studio-700" />

          {/* Project Selector Dropdown */}
          <div className="flex items-center gap-2">
            <span className="text-2xs font-mono text-studio-500 uppercase tracking-wider">Project:</span>
            {isCreatingProject ? (
              <form onSubmit={handleCreateProject} className="flex items-center gap-1.5">
                <input
                  type="text"
                  value={newProjectName}
                  onChange={(e) => setNewProjectName(e.target.value)}
                  placeholder="Project name…"
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
              <div className="flex items-center gap-1">
                <select
                  value={project?.id || ""}
                  onChange={(e) => switchProject(e.target.value)}
                  className="bg-studio-800 text-studio-100 border border-studio-700 rounded px-2 py-1 text-xs font-medium hover:border-studio-600 focus:outline-none focus:border-accent-500 transition-colors"
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
          </div>
        </div>

        {/* Center: Studio Segmented View Tabs */}
        <div className="flex items-center gap-1 bg-studio-950 p-1 rounded-panel border border-studio-700/60">
          <button
            onClick={() => onTabChange?.("canvas")}
            className={`px-3 py-1 rounded-md font-medium text-xs transition-all ${
              activeTab === "canvas"
                ? "bg-studio-800 text-accent-400 border border-studio-700 shadow-studio"
                : "text-studio-400 hover:text-studio-200"
            }`}
          >
            Workflow Canvas
          </button>
          <button
            onClick={() => onTabChange?.("chat")}
            className={`px-3 py-1 rounded-md font-medium text-xs transition-all ${
              activeTab === "chat"
                ? "bg-studio-800 text-accent-400 border border-studio-700 shadow-studio"
                : "text-studio-400 hover:text-studio-200"
            }`}
          >
            Interactive Chat
          </button>
          <button
            onClick={() => onTabChange?.("config")}
            className={`px-3 py-1 rounded-md font-medium text-xs transition-all ${
              activeTab === "config"
                ? "bg-studio-800 text-accent-400 border border-studio-700 shadow-studio"
                : "text-studio-400 hover:text-studio-200"
            }`}
          >
            Agent Inspector
          </button>
        </div>

        {/* Right: Actions & Settings */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowToolCatalog(true)}
            className="px-2.5 py-1 text-xs font-medium text-studio-300 hover:text-white bg-studio-800 hover:bg-studio-700 border border-studio-700 rounded-md transition-colors"
          >
            Tool Catalog
          </button>

          <button
            onClick={() => setShowSettings(true)}
            className="p-1.5 text-studio-400 hover:text-studio-100 hover:bg-studio-800 rounded-md transition-colors"
            title="Settings"
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
