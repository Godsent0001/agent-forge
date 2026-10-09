import { useEffect, useState } from "react";
import { api, getApiBase } from "./api/client";
import { AgentChat } from "./components/AgentChat";
import { AgentEditor } from "./components/AgentEditor";
import { AgentTree } from "./components/AgentTree";
import { ExecutionTree } from "./components/ExecutionTree";
import { TopBar } from "./components/TopBar";
import { WorkflowCanvas } from "./components/WorkflowCanvas";
import { useStore } from "./store/useStore";

type BootState = "checking-sidecar" | "sidecar-down" | "loading-project" | "ready";

export default function App() {
  const [boot, setBoot] = useState<BootState>("checking-sidecar");
  const [bootError, setBootError] = useState<string | null>(null);
  const [activeApiBase, setActiveApiBase] = useState<string>("http://127.0.0.1:8000");
  const fetchProjects = useStore((s) => s.fetchProjects);
  const loadProject = useStore((s) => s.loadProject);
  const [activeExecutionId, setActiveExecutionId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"chat" | "config" | "canvas">("chat");
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const bootstrap = async () => {
      try {
        let sidecarUp = false;
        for (let attempt = 0; attempt < 15 && !cancelled; attempt++) {
          try {
            const apiBase = await getApiBase();
            setActiveApiBase(apiBase);
            const res = await fetch(`${apiBase}/health`);
            if (res.ok) {
              sidecarUp = true;
              break;
            }
          } catch {
            // not up yet
          }
          await new Promise((r) => setTimeout(r, 500));
        }
        if (cancelled) return;
        if (!sidecarUp) {
          setBoot("sidecar-down");
          return;
        }

        setBoot("loading-project");
        await api.settings.syncKeysToBackend();
        const projects = await fetchProjects();
        const project = projects[0] ?? (await api.projects.create("My First Project"));
        await loadProject(project);
        if (!cancelled) setBoot("ready");
      } catch (error) {
        if (!cancelled) {
          setBootError(error instanceof Error ? error.message : "AgentForge failed to start");
          setBoot("sidecar-down");
        }
      }
    };

    bootstrap();
    return () => {
      cancelled = true;
    };
  }, [fetchProjects, loadProject]);

  if (boot === "checking-sidecar" || boot === "loading-project") {
    return (
      <div className="h-full flex items-center justify-center bg-studio-950 text-studio-400 text-xs font-mono">
        {boot === "checking-sidecar" ? "Starting runtime sidecar…" : "Loading project workspace…"}
      </div>
    );
  }

  if (boot === "sidecar-down") {
    return (
      <div className="h-full flex items-center justify-center bg-studio-950 p-4">
        <div className="rounded-panel border border-studio-700 bg-studio-900 shadow-elevated p-6 max-w-md w-full">
          <h1 className="text-base font-bold text-status-error mb-2">Runtime Unreachable</h1>
          <p className="text-xs text-studio-300 leading-relaxed">
            The Python sidecar runtime did not respond on <code className="text-accent-400">{activeApiBase}</code>.
            Ensure the backend is running properly.
          </p>
          {bootError && (
            <pre className="mt-3 max-h-32 overflow-auto rounded bg-red-950/40 border border-red-900/60 p-2.5 text-2xs text-red-300 font-mono whitespace-pre-wrap">
              {bootError}
            </pre>
          )}
          <button
            onClick={() => window.location.reload()}
            className="mt-4 rounded bg-studio-800 hover:bg-studio-700 border border-studio-600 px-3 py-1.5 text-xs font-medium text-studio-100 transition-colors"
          >
            Reload Workspace
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen w-screen flex flex-col bg-studio-950 overflow-hidden text-studio-100">
      <TopBar
        onRun={setActiveExecutionId}
        activeTab={activeTab}
        onTabChange={setActiveTab}
      />
      <div className="flex-1 flex min-h-0 overflow-hidden">
        {/* Collapsible Project Explorer Sidebar */}
        <div className={`${isSidebarCollapsed ? "w-12" : "w-64"} transition-all shrink-0 h-full`}>
          <AgentTree
            onOpenConfig={() => setActiveTab("config")}
            isCollapsed={isSidebarCollapsed}
            onToggleCollapse={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
          />
        </div>

        {/* Center Main Workspace */}
        <div className="flex-1 min-w-0 h-full overflow-hidden">
          {activeTab === "canvas" && <WorkflowCanvas />}
          {activeTab === "chat" && <AgentChat onRunExecution={setActiveExecutionId} />}
          {activeTab === "config" && <AgentEditor />}
        </div>

        {/* Right Execution & Debug Inspector */}
        <div className="w-80 border-l border-studio-700/80 bg-studio-900 h-full shrink-0 min-w-0">
          <ExecutionTree executionId={activeExecutionId} />
        </div>
      </div>
    </div>
  );
}
