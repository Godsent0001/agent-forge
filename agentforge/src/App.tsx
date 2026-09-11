import { useEffect, useState } from "react";
import { api } from "./api/client";
import { AgentEditor } from "./components/AgentEditor";
import { AgentTree } from "./components/AgentTree";
import { ChatSection, ChatMessage } from "./components/ChatSection";
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
  const [viewMode, setViewMode] = useState<"chat" | "config">("chat");
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [isExecuting, setIsExecuting] = useState(false);
  const selectedAgentId = useStore((s) => s.selectedAgentId);
  const agents = useStore((s) => s.agents);

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

  const handleRunTask = async (taskText: string) => {
    const selectedAgent = agents.find((a) => a.id === selectedAgentId);
    const userMsg: ChatMessage = {
      id: Date.now().toString(),
      sender: "user",
      content: taskText,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };
    setChatMessages((prev) => [...prev, userMsg]);
    setIsExecuting(true);

    try {
      const project = useStore.getState().project;
      if (!project || !selectedAgentId) return;
      const execution = await api.executions.run(project.id, selectedAgentId, taskText);
      setActiveExecutionId(execution.id);

      const agentMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        sender: "agent",
        agentName: selectedAgent?.name ?? "Agent",
        content: execution.final_output || "(Execution completed with no output)",
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };
      setChatMessages((prev) => [...prev, agentMsg]);
    } catch (err) {
      const errorMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        sender: "agent",
        agentName: selectedAgent?.name ?? "Agent",
        content: `Error: ${err instanceof Error ? err.message : "Execution failed"}`,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };
      setChatMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsExecuting(false);
    }
  };

  return (
    <div className="h-full flex flex-col bg-surface-950 text-neutral-100">
      <TopBar onRun={handleRunTask} />
      <div className="px-4 py-1.5 border-b border-white/5 bg-surface-900 flex items-center justify-between text-xs">
        <div className="flex gap-2">
          <button
            onClick={() => setViewMode("chat")}
            className={`px-3 py-1 rounded transition-colors ${
              viewMode === "chat" ? "bg-accent-500 text-white font-medium" : "text-neutral-400 hover:text-white"
            }`}
          >
            💬 Chat Mode
          </button>
          <button
            onClick={() => setViewMode("config")}
            className={`px-3 py-1 rounded transition-colors ${
              viewMode === "config" ? "bg-accent-500 text-white font-medium" : "text-neutral-400 hover:text-white"
            }`}
          >
            ⚙️ Agent & Tool Builder
          </button>
        </div>
      </div>
      <div className="flex-1 grid grid-cols-[260px_1fr_320px] min-h-0 overflow-hidden">
        <AgentTree />
        <div className="flex flex-col h-full min-h-0 bg-surface-950">
          {viewMode === "chat" ? (
            <ChatSection messages={chatMessages} running={isExecuting} />
          ) : (
            <AgentEditor />
          )}
        </div>
        <ExecutionTree executionId={activeExecutionId} />
      </div>
    </div>
  );
}
