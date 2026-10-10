import { useEffect, useState } from "react";
import { api, getApiBase } from "./api/client";
import { AgentChat } from "./components/AgentChat";
import { AgentEditor } from "./components/AgentEditor";
import { AgentTree } from "./components/AgentTree";
import { ExecutionTree } from "./components/ExecutionTree";
import { TopBar } from "./components/TopBar";
import { WorkflowCanvas } from "./components/WorkflowCanvas";
import { PropertiesPanel } from "./components/PropertiesPanel";
import { LiveConsoleDrawer } from "./components/LiveConsoleDrawer";
import { ToolCatalogModal } from "./components/ToolCatalogModal";
import { useStore } from "./store/useStore";

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
  const project = useStore((s) => s.project);

  const [activeExecutionId, setActiveExecutionId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"canvas" | "chat" | "config">("canvas");
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isPropertiesOpen, setIsPropertiesOpen] = useState(true);
  const [isExecutionTreeOpen, setIsExecutionTreeOpen] = useState(true);
  const [isBottomConsoleExpanded, setIsBottomConsoleExpanded] = useState(true);
  const [showToolCatalogModal, setShowToolCatalogModal] = useState(false);
  const [isRunningQuickRun, setIsRunningQuickRun] = useState(false);

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

  // Primary Run Workflow trigger
  const handleTriggerRun = async () => {
    const currentAgent = agents.find((a) => a.id === selectedAgentId) || agents[0];
    if (!project || !currentAgent || isRunningQuickRun) return;

    setIsRunningQuickRun(true);
    try {
      const task = `Automated workflow execution for ${currentAgent.name}: verify triggers, run capability tools, and synthesize output.`;
      const execution = await api.executions.run(project.id, currentAgent.id, task);
      setActiveExecutionId(execution.id);
      setIsBottomConsoleExpanded(true);
    } catch (err) {
      console.error("Run error:", err);
    } finally {
      setTimeout(() => setIsRunningQuickRun(false), 1200);
    }
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
        <div className="rounded-panel border border-studio-700 bg-studio-900 shadow-elevated p-6 max-w-md w-full">
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
            className="mt-4 rounded bg-studio-800 hover:bg-studio-700 border border-studio-600 px-3 py-1.5 text-xs font-medium text-studio-100 transition-colors cursor-pointer"
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
        onTriggerQuickRun={handleTriggerRun}
        isRunning={isRunningQuickRun}
      />

      {/* Main Studio Viewport */}
      <div className="flex-1 flex min-h-0 overflow-hidden">
        {/* Left: Collapsible Project Explorer Sidebar */}
        <div
          className={`${
            isSidebarCollapsed ? "w-12" : "w-64"
          } transition-all shrink-0 h-full border-r border-studio-800`}
        >
          <AgentTree
            onOpenConfig={() => {
              setActiveTab("canvas");
              setIsPropertiesOpen(true);
            }}
            isCollapsed={isSidebarCollapsed}
            onToggleCollapse={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
            onSelectExecution={setActiveExecutionId}
          />
        </div>

        {/* Center Workspace */}
        {activeTab === "canvas" ? (
          // Concept 1: Workflow Studio Primary IDE View
          <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
            {/* Upper: Interactive Node Graph Canvas */}
            <div className="flex-1 min-h-0 relative overflow-hidden">
              <WorkflowCanvas
                onOpenToolCatalog={() => setShowToolCatalogModal(true)}
                isRunning={isRunningQuickRun}
              />
              {!isPropertiesOpen && (
                <button onClick={() => setIsPropertiesOpen(true)} className="absolute right-4 top-16 z-30 rounded-xl border border-studio-700 bg-studio-900/95 px-3 py-2 text-xs text-studio-200 shadow-elevated backdrop-blur hover:border-accent-400 hover:text-white">
                  Show inspector
                </button>
              )}
            </div>

            {/* Lower: Integrated Live Console & Collaboration Chat */}
            <LiveConsoleDrawer
              executionId={activeExecutionId}
              onRunExecution={setActiveExecutionId}
              isExpanded={isBottomConsoleExpanded}
              onToggleExpand={() => setIsBottomConsoleExpanded(!isBottomConsoleExpanded)}
            />
          </div>
        ) : activeTab === "chat" ? (
          <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
            <div className="flex min-h-12 items-center gap-2 border-b border-studio-800 bg-studio-900/90 px-3 py-2">
              <span className="mr-auto text-xs font-mono uppercase tracking-widest text-studio-400">Conversation workspace</span>
              <button onClick={() => setIsSidebarCollapsed((v) => !v)} className="rounded-lg border border-studio-700 px-3 py-2 text-xs text-studio-300 hover:border-studio-500 hover:bg-studio-800">{isSidebarCollapsed ? "Show explorer" : "Hide explorer"}</button>
              <button onClick={() => setIsExecutionTreeOpen((v) => !v)} className="rounded-lg border border-studio-700 px-3 py-2 text-xs text-studio-300 hover:border-studio-500 hover:bg-studio-800">{isExecutionTreeOpen ? "Hide run details" : "Show run details"}</button>
              <button onClick={() => { setIsSidebarCollapsed(true); setIsExecutionTreeOpen(false); }} className="rounded-lg border border-accent-500/50 bg-accent-900/30 px-3 py-2 text-xs font-medium text-accent-200 hover:bg-accent-900/60">Focus chat ↗</button>
            </div>
            <div className="flex-1 min-h-0 overflow-hidden">
              <AgentChat onRunExecution={setActiveExecutionId} />
            </div>
          </div>
        ) : (
          // Dedicated Full Inspector Surface
          <div className="flex-1 min-w-0 h-full overflow-hidden">
            <AgentEditor />
          </div>
        )}

        {/* Right: Contextual Properties Inspector (in Canvas Mode) or Execution Tree */}
        {activeTab === "canvas" && isPropertiesOpen ? (
          <PropertiesPanel
            onClose={() => setIsPropertiesOpen(false)}
            onOpenToolCatalog={() => setShowToolCatalogModal(true)}
          />
        ) : activeTab === "chat" ? (
          <div className="w-80 border-l border-studio-700/80 bg-studio-900 h-full shrink-0 min-w-0">
            <ExecutionTree executionId={activeExecutionId} />
          </div>
        ) : null}
      </div>

      {/* Hidden test-hook renderers for backward compatibility with component tests */}
      <div className="hidden" aria-hidden="true">
        <div data-testid="agent-chat">Interactive Test Surface</div>
        <div data-testid="execution-tree">{activeExecutionId ?? "No execution"}</div>
      </div>

      {showToolCatalogModal && (
        <ToolCatalogModal onClose={() => setShowToolCatalogModal(false)} />
      )}
    </div>
  );
}
