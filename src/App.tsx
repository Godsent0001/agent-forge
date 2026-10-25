import { useEffect, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import { api, getApiBase } from "./api/client";
import { AgentChat } from "./components/AgentChat";
import { AgentEditor } from "./components/AgentEditor";
import { AgentTree } from "./components/AgentTree";
import { ExecutionTree } from "./components/ExecutionTree";
import { TopBar } from "./components/TopBar";
import { RunTaskModal } from "./components/RunTaskModal";
import { WorkflowCanvas } from "./components/WorkflowCanvas";
import { PropertiesPanel } from "./components/PropertiesPanel";
import { ToolCatalogModal } from "./components/ToolCatalogModal";
import { SystemEngineerWorkspace } from "./components/SystemEngineerWorkspace";
import { FloatingSystemEngineer } from "./components/FloatingSystemEngineer";
import { useStore } from "./store/useStore";
import { Icon } from "./components/ui/Icon";

type BootState = "checking-sidecar" | "sidecar-down" | "loading-project" | "ready";

export default function App() {
  const [boot, setBoot] = useState<BootState>("checking-sidecar");
  const [bootError, setBootError] = useState<string | null>(null);
  const [activeApiBase, setActiveApiBase] = useState<string>(
    typeof window !== "undefined" ? window.location.origin : ""
  );

  const fetchProjects = useStore((s) => s.fetchProjects);
  const loadProject = useStore((s) => s.loadProject);
  const selectedAgentId = useStore((s) => s.selectedAgentId);
  const agents = useStore((s) => s.agents);
  const selectAgent = useStore((s) => s.selectAgent);
  const queueTask = useStore((s) => s.queueTask);
  const project = useStore((s) => s.project);

  const [activeExecutionId, setActiveExecutionId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"canvas" | "chat" | "config" | "engineer">("chat");
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [sidebarWidth, setSidebarWidth] = useState(248);
  const [inspectorWidth, setInspectorWidth] = useState(320);
  const [resizeDrag, setResizeDrag] = useState<{ panel: "sidebar" | "inspector"; startX: number; startWidth: number } | null>(null);
  const [isCompactViewport, setIsCompactViewport] = useState(false);
  const [isPropertiesOpen, setIsPropertiesOpen] = useState(true);
  const [showRunDialog, setShowRunDialog] = useState(false);
  const [isExecutionTreeOpen, setIsExecutionTreeOpen] = useState(false);
  const [showToolCatalogModal, setShowToolCatalogModal] = useState(false);
  const [isRunningQuickRun, setIsRunningQuickRun] = useState(false);

  useEffect(() => {
    const updateViewport = () => setIsCompactViewport(window.innerWidth < 768);
    updateViewport();
    window.addEventListener("resize", updateViewport);
    return () => window.removeEventListener("resize", updateViewport);
  }, []);

  useEffect(() => {
    if (!isCompactViewport) return;
    // On phones, start with chat unobstructed; the explorer and inspector open on demand.
    setIsSidebarCollapsed(true);
    setIsPropertiesOpen(false);
    setIsExecutionTreeOpen(false);
  }, [isCompactViewport]);

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
            // not ready yet
          }
          await new Promise((r) => setTimeout(r, 400));
        }

        if (cancelled) return;
        if (!sidecarUp) {
          setBoot("sidecar-down");
          return;
        }

        setBoot("loading-project");
        await api.settings.syncKeysToBackend();
        const projects = await fetchProjects();
        const initialProject = projects[0] ?? (await api.projects.create("Workflow Studio"));
        await loadProject(initialProject);
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

  // A chat run should surface its live trace immediately, without leaving the conversation.
  const handleChatRunStarted = (executionId: string) => {
    setActiveExecutionId(executionId);
    setIsExecutionTreeOpen(true);
    setIsPropertiesOpen(false);
  };

  const beginResize = (panel: "sidebar" | "inspector", event: ReactPointerEvent<HTMLDivElement>) => {
    if (isCompactViewport) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    setResizeDrag({ panel, startX: event.clientX, startWidth: panel === "sidebar" ? sidebarWidth : inspectorWidth });
  };
  const moveResize = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!resizeDrag) return;
    const delta = event.clientX - resizeDrag.startX;
    if (resizeDrag.panel === "sidebar") setSidebarWidth(Math.max(184, Math.min(440, resizeDrag.startWidth + delta)));
    else setInspectorWidth(Math.max(240, Math.min(560, resizeDrag.startWidth - delta)));
  };
  const endResize = () => setResizeDrag(null);
  const toggleInspector = () => {
    if (isPropertiesOpen && !isExecutionTreeOpen) setIsPropertiesOpen(false);
    else { setIsPropertiesOpen(true); setIsExecutionTreeOpen(false); }
  };
  const toggleLogs = () => {
    if (isExecutionTreeOpen) setIsExecutionTreeOpen(false);
    else { setIsExecutionTreeOpen(true); setIsPropertiesOpen(false); }
  };

  // Primary Run Workflow trigger
  // "Run workflow" is the chat composer with room for more options later: the task is queued into the
  // selected agent's conversation, so it is saved to chat history and produces a run log like any message.
  const handleTriggerRun = async (task: string) => {
    const currentAgent = agents.find((a) => a.id === selectedAgentId) || agents[0];
    if (!project || !currentAgent) throw new Error("Create an agent before running a workflow.");
    selectAgent(currentAgent.id);
    queueTask(currentAgent.id, task);
    setActiveTab("chat");
    setIsRunningQuickRun(true);
    setTimeout(() => setIsRunningQuickRun(false), 1200);
  };

  if (boot === "checking-sidecar" || boot === "loading-project") {
    return (
      <div className="h-full w-full flex items-center justify-center bg-studio-950 text-studio-400 text-xs font-mono">
        {boot === "checking-sidecar" ? "Connecting to AgentForge runtime…" : "Loading workspace…"}
      </div>
    );
  }

  if (boot === "sidecar-down") {
    return (
      <div className="h-full w-full flex items-center justify-center bg-studio-950 p-4">
        <div className="rounded-panel bg-studio-900 neu-raised p-6 max-w-md w-full">
          <h1 className="text-base font-bold text-status-error mb-2">Runtime Unreachable</h1>
          <p className="text-xs text-studio-300 leading-relaxed">
            The AgentForge backend did not respond on <code className="text-accent-400">{activeApiBase}</code>.
            Ensure the server process is running.
          </p>
          {bootError && (
            <pre className="mt-3 max-h-32 overflow-auto rounded bg-red-950/40 border border-red-900/60 p-2.5 text-2xs text-red-300 font-mono whitespace-pre-wrap">
              {bootError}
            </pre>
          )}
          <button
            onClick={() => window.location.reload()}
            className="mt-4 rounded-lg bg-studio-850 neu-raised-sm hover:text-white active:shadow-neu-pressed px-3 py-1.5 text-xs font-medium text-studio-100 transition-all cursor-pointer"
          >
            Reload Workspace
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen w-screen flex flex-col bg-studio-950 overflow-hidden text-studio-100">
      {/* Top Application Header */}
      <TopBar
        onRun={setActiveExecutionId}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        onTriggerQuickRun={() => setShowRunDialog(true)}
        isRunning={isRunningQuickRun}
      />

      {/* Main Studio Viewport */}
      <div className="relative flex-1 flex min-h-0 gap-2.5 overflow-hidden p-2.5 pt-3">
        <div className={`relative h-full shrink-0 rounded-panel bg-studio-900 neu-raised ${isCompactViewport ? "absolute inset-y-2.5 left-2.5 z-40 h-auto shadow-elevated" : ""}`} style={{ width: isSidebarCollapsed ? 44 : sidebarWidth }}>
          <AgentTree
            onOpenConfig={() => { setActiveTab("config"); setIsPropertiesOpen(false); setIsExecutionTreeOpen(false); }}
            isCollapsed={isSidebarCollapsed}
            onToggleCollapse={() => setIsSidebarCollapsed((value) => !value)}
            onSelectExecution={setActiveExecutionId}
          />
          {!isSidebarCollapsed && !isCompactViewport && (
            <div role="separator" aria-label="Resize explorer" aria-orientation="vertical" tabIndex={0}
              onPointerDown={(event) => beginResize("sidebar", event)} onPointerMove={moveResize}
              onPointerUp={endResize} onPointerCancel={endResize}
              onKeyDown={(event) => { if (event.key === "ArrowLeft" || event.key === "ArrowRight") { event.preventDefault(); setSidebarWidth((width) => Math.max(184, Math.min(440, width + (event.key === "ArrowRight" ? 12 : -12)))); } }}
              className="absolute right-[-7px] top-3 bottom-3 z-30 w-1.5 cursor-col-resize touch-none rounded-full hover:bg-accent-500/50 focus-visible:bg-accent-500/60"
            />
          )}
        </div>

        {activeTab === "engineer" ? (
          <SystemEngineerWorkspace
            onOpenToolCatalog={() => setShowToolCatalogModal(true)}
          />
        ) : activeTab === "canvas" ? (
          <div className="relative flex-1 min-w-0 h-full overflow-hidden rounded-panel bg-studio-900 neu-raised"><WorkflowCanvas onOpenToolCatalog={() => setShowToolCatalogModal(true)} isRunning={isRunningQuickRun} /></div>
        ) : activeTab === "chat" ? (
          <div className="flex-1 flex min-w-0 h-full overflow-hidden rounded-panel bg-studio-900 neu-raised"><AgentChat onRunExecution={handleChatRunStarted} /></div>
        ) : (
          <div className="flex-1 min-w-0 h-full overflow-hidden rounded-panel bg-studio-900 neu-raised"><AgentEditor /></div>
        )}

        {((isPropertiesOpen && !isExecutionTreeOpen) || isExecutionTreeOpen) && activeTab !== "config" && activeTab !== "engineer" && (
          <div className={`relative h-full shrink-0 rounded-panel bg-studio-900 neu-raised ${isCompactViewport ? "absolute inset-y-2.5 right-16 z-40 h-auto shadow-elevated" : ""}`} style={{ width: isCompactViewport ? "min(22rem, calc(100vw - 5.75rem))" : inspectorWidth }}>
            {!isCompactViewport && (
              <div role="separator" aria-label="Resize inspector" aria-orientation="vertical" tabIndex={0}
                onPointerDown={(event) => beginResize("inspector", event)} onPointerMove={moveResize}
                onPointerUp={endResize} onPointerCancel={endResize}
                onKeyDown={(event) => { if (event.key === "ArrowLeft" || event.key === "ArrowRight") { event.preventDefault(); setInspectorWidth((width) => Math.max(240, Math.min(560, width + (event.key === "ArrowLeft" ? 12 : -12)))); } }}
                className="absolute left-[-7px] top-3 bottom-3 z-30 w-1.5 cursor-col-resize touch-none rounded-full hover:bg-accent-500/50 focus-visible:bg-accent-500/60"
              />
            )}
            {isExecutionTreeOpen ? <ExecutionTree executionId={activeExecutionId} onSelectExecution={setActiveExecutionId} /> : <PropertiesPanel onClose={() => setIsPropertiesOpen(false)} onOpenToolCatalog={() => setShowToolCatalogModal(true)} />}
          </div>
        )}

        {activeTab !== "config" && activeTab !== "engineer" && (
          <aside aria-label="Workspace panels" className="z-30 flex h-full w-12 shrink-0 flex-col items-center gap-2.5 rounded-panel bg-studio-900 neu-raised py-2.5">
            <button type="button" onClick={toggleInspector} aria-label={activeTab === "chat" ? "Model & delegation" : "Inspector"} aria-pressed={isPropertiesOpen && !isExecutionTreeOpen} title={activeTab === "chat" ? "Model and delegation" : "Inspector"}
              className={`rounded-lg p-2 transition-all ${isPropertiesOpen && !isExecutionTreeOpen ? "bg-studio-900 shadow-neu-pressed text-accent-300" : "text-studio-400 hover:text-studio-100 hover:shadow-neu-sm"}`}>
              <Icon name="inspector" />
            </button>
            <button type="button" onClick={toggleLogs} aria-label={activeTab === "chat" ? "Activity" : "View logs"} aria-pressed={isExecutionTreeOpen} title={activeTab === "chat" ? "Activity" : "View logs"}
              className={`rounded-lg p-2 transition-all ${isExecutionTreeOpen ? "bg-studio-900 shadow-neu-pressed text-accent-300" : "text-studio-400 hover:text-studio-100 hover:shadow-neu-sm"}`}>
              <Icon name="logs" />
            </button>
          </aside>
        )}
      </div>

      {showToolCatalogModal && <ToolCatalogModal onClose={() => setShowToolCatalogModal(false)} />}
      {showRunDialog && (
        <RunTaskModal
          agentName={(agents.find((a) => a.id === selectedAgentId) || agents[0])?.name ?? "Agent"}
          onClose={() => setShowRunDialog(false)}
          onSubmit={handleTriggerRun}
        />
      )}
      <FloatingSystemEngineer />
    </div>
  );
}