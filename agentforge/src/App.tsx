import { useEffect, useState } from "react";
import { api } from "./api/client";
import { AgentEditor } from "./components/AgentEditor";
import { AgentTree } from "./components/AgentTree";
import { ExecutionTree } from "./components/ExecutionTree";
import { TopBar } from "./components/TopBar";
import { useStore } from "./store/useStore";

type BootState = "checking-sidecar" | "sidecar-down" | "loading-project" | "ready";

const API_BASE = "http://127.0.0.1:8756";

export default function App() {
  const [boot, setBoot] = useState<BootState>("checking-sidecar");
  const fetchProjects = useStore((s) => s.fetchProjects);
  const loadProject = useStore((s) => s.loadProject);
  const [activeExecutionId, setActiveExecutionId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const bootstrap = async () => {
      let sidecarUp = false;
      for (let attempt = 0; attempt < 15 && !cancelled; attempt++) {
        try {
          const res = await fetch(`${API_BASE}/health`);
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
      <div className="h-full flex items-center justify-center text-neutral-500 text-sm">
        {boot === "checking-sidecar" ? "Starting runtime…" : "Loading project…"}
      </div>
    );
  }

  if (boot === "sidecar-down") {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="rounded-panel border border-white/10 bg-surface-900 shadow-panel px-8 py-6 max-w-md">
          <h1 className="text-lg font-semibold text-status-error mb-2">Runtime unreachable</h1>
          <p className="text-sm text-neutral-400">
            The Python sidecar didn't respond on {API_BASE}. Check the terminal for
            <code className="mx-1 px-1 bg-surface-800 rounded">[python-runtime:err]</code>
            lines — see the README's sidecar naming/path section.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      <TopBar onRun={setActiveExecutionId} />
      <div className="flex-1 grid grid-cols-[260px_1fr_320px] min-h-0">
        <AgentTree />
        <AgentEditor />
        <ExecutionTree executionId={activeExecutionId} />
      </div>
    </div>
  );
}
