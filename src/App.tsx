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
 const [activeApiBase, setActiveApiBase] = useState<string>("http://127.0.0.1:8000");
  const fetchProjects = useStore((s) => s.fetchProjects);
  const loadProject = useStore((s) => s.loadProject);
  const [activeExecutionId, setActiveExecutionId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"chat" | "config">("chat");

  useEffect(() => {
    let cancelled = false;

    const bootstrap = async () => {
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
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-surface-950">
      <TopBar
        onRun={setActiveExecutionId}
        activeTab={activeTab}
        onTabChange={setActiveTab}
      />
      <div className="flex-1 grid grid-cols-[280px_1fr_320px] min-h-0">
        <AgentTree />
        <div className={`min-w-0 h-full ${activeTab === "chat" ? "block" : "hidden"}`}>
          <AgentChat onRunExecution={setActiveExecutionId} />
        </div>
        <div className={`min-w-0 h-full ${activeTab === "config" ? "block" : "hidden"}`}>
          <AgentEditor />
        </div>
        <ExecutionTree executionId={activeExecutionId} />
      </div>
    </div>
  );
}
