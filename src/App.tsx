import { useEffect, useState } from "react";
import { api, getApiBase } from "./api/client";
import { AgentChat } from "./components/AgentChat";
import { AgentEditor } from "./components/AgentEditor";
import { AgentTree } from "./components/AgentTree";
import { ExecutionTree } from "./components/ExecutionTree";
import { TopBar } from "./components/TopBar";
import { useStore } from "./store/useStore";

type BootState = "checking-sidecar" | "sidecar-down" | "loading-project" | "ready";

export default function App() {
  const [boot, setBoot] = useState<BootState>("checking-sidecar");
  const [bootError, setBootError] = useState<string | null>(null);
  const [activeApiBase, setActiveApiBase] = useState<string>("http://127.0.0.1:8000");
  const fetchProjects = useStore((s) => s.fetchProjects);
  const loadProject = useStore((s) => s.loadProject);
  const [activeExecutionId, setActiveExecutionId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"chat" | "config">("chat");

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
      <div className="h-full flex items-center justify-center bg-surface-950 text-slate-500 text-sm font-medium">
        {boot === "checking-sidecar" ? "Starting runtime sidecar…" : "Loading project workspace…"}
      </div>
    );
  }

  if (boot === "sidecar-down") {
    return (
      <div className="h-full flex items-center justify-center bg-surface-950">
        <div className="rounded-panel border border-slate-200 bg-white shadow-card px-8 py-6 max-w-md">
          <h1 className="text-lg font-bold text-status-error mb-2">Runtime unreachable</h1>
          <p className="text-sm text-slate-600 leading-relaxed">
            The Python sidecar didn't respond on {activeApiBase}. Check your terminal logs or ensure the Python backend is running properly.
          </p>
          {bootError && <pre className="mt-3 max-h-32 overflow-auto rounded-lg bg-red-50 p-3 text-xs text-red-700 whitespace-pre-wrap">{bootError}</pre>}
          <button onClick={() => window.location.reload()} className="mt-4 rounded-lg bg-slate-800 px-3 py-2 text-xs font-semibold text-white hover:bg-slate-700">Reload</button>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen w-screen flex flex-col bg-surface-950 overflow-hidden">
      <TopBar
        onRun={setActiveExecutionId}
        activeTab={activeTab}
        onTabChange={setActiveTab}
      />
      <div className="flex-1 grid grid-cols-[280px_1fr_320px] min-h-0 overflow-hidden">
        <AgentTree onOpenConfig={() => setActiveTab("config")} />
        <div className="min-w-0 h-full overflow-hidden">
          {activeTab === "chat" ? (
            <div className="h-full flex flex-col">
              <AgentChat onRunExecution={setActiveExecutionId} />
            </div>
          ) : (
            <div className="h-full flex flex-col">
              <AgentEditor />
            </div>
          )}
        </div>
        <ExecutionTree executionId={activeExecutionId} />
      </div>
    </div>
  );
}
