import { useState, useRef } from "react";
import { useStore } from "../store/useStore";
import { ToolCatalogModal } from "./ToolCatalogModal";

interface WorkflowCanvasProps {
  onOpenToolCatalog?: () => void;
  isRunning?: boolean;
}

export function WorkflowCanvas({ onOpenToolCatalog, isRunning = false }: WorkflowCanvasProps) {
  const agents = useStore((s) => s.agents) || [];
  const tools = useStore((s) => s.tools) || [];
  const selectedAgentId = useStore((s) => s.selectedAgentId);
  const selectAgent = useStore((s) => s.selectAgent);

  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 40, y: 30 });
  const [isPanning, setIsPanning] = useState(false);
  const [startPan, setStartPan] = useState({ x: 0, y: 0 });
  const [catalogModalOpen, setCatalogModalOpen] = useState(false);
  const [selectedNodeId, setSelectedNodeId] = useState<string>("agent-main");

  const canvasRef = useRef<HTMLDivElement>(null);

  // Active agent (root or selected)
  const activeAgent = agents.find((a) => a.id === selectedAgentId) || agents[0];
  const attachedTools = tools.filter((t) => activeAgent?.tool_ids?.includes(t.id));
  const childAgents = agents.filter((a) => activeAgent?.child_agent_ids?.includes(a.id));

  // Dynamic layout coordinates for connection lines
  // Trigger -> Main Agent -> Actions / Sub-agents
  const triggerNode = { x: 40, y: 160, width: 220, height: 110 };
  const agentNode = { x: 340, y: 60, width: 340, height: Math.max(340, 220 + attachedTools.length * 48) };
  
  // Right side action nodes
  const actionNodes = [
    ...(childAgents.length > 0
      ? childAgents.map((ca, idx) => ({
          id: `child-${ca.id}`,
          type: "subagent" as const,
          title: ca.name,
          subtitle: `Sub-agent (${ca.model})`,
          x: 770,
          y: 70 + idx * 110,
          width: 250,
          height: 85,
        }))
      : []),
    {
      id: "action-execute",
      type: "action" as const,
      title: "Synthesize Results",
      subtitle: "Consolidate tool outputs & format final response",
      x: 770,
      y: 70 + (childAgents.length) * 110,
      width: 250,
      height: 85,
    },
    {
      id: "action-notify",
      type: "action" as const,
      title: "Stream & Log Traces",
      subtitle: "Emit execution events to live telemetry debugger",
      x: 770,
      y: 190 + (childAgents.length) * 110,
      width: 250,
      height: 85,
    },
  ];

  // Mouse wheel zoom
  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? -0.1 : 0.1;
    setZoom((z) => Math.min(Math.max(0.6, z + delta), 1.8));
  };

  // Pan interaction
  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.target === canvasRef.current || (e.target as HTMLElement).tagName === "svg") {
      setIsPanning(true);
      setStartPan({ x: e.clientX - pan.x, y: e.clientY - pan.y });
    }
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isPanning) return;
    setPan({ x: e.clientX - startPan.x, y: e.clientY - startPan.y });
  };

  const handleMouseUp = () => {
    setIsPanning(false);
  };

  const handleFitView = () => {
    setZoom(1);
    setPan({ x: 40, y: 30 });
  };

  const handleAddToolClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (onOpenToolCatalog) {
      onOpenToolCatalog();
    } else {
      setCatalogModalOpen(true);
    }
  };

  // SVG Cubic Bezier Curve Generator
  const generateBezierPath = (x1: number, y1: number, x2: number, y2: number) => {
    const dx = Math.max(40, (x2 - x1) * 0.5);
    return `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;
  };

  return (
    <div
      ref={canvasRef}
      onWheel={handleWheel}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      className="h-full w-full bg-studio-950 bg-grid-pattern relative flex flex-col overflow-hidden select-none cursor-grab active:cursor-grabbing"
    >
      {/* Floating Canvas Toolbar Controls */}
      <div className="absolute top-4 left-4 z-20 flex items-center gap-1.5 bg-studio-900/90 backdrop-blur-md border border-studio-700/80 rounded-panel p-1.5 shadow-elevated">
        <span className="text-2xs font-mono font-semibold uppercase tracking-wider text-studio-400 px-2">
          Canvas
        </span>
        <div className="h-4 w-px bg-studio-700" />
        <button
          onClick={handleFitView}
          className="px-2 py-1 text-2xs font-mono text-studio-300 hover:text-white hover:bg-studio-800 rounded transition-colors"
          title="Reset Canvas View"
        >
          Fit View
        </button>
        <button
          onClick={() => setZoom((z) => Math.min(1.8, z + 0.15))}
          className="px-2 py-1 text-2xs font-mono text-studio-300 hover:text-white hover:bg-studio-800 rounded transition-colors"
          title="Zoom In"
        >
          +
        </button>
        <button
          onClick={() => setZoom((z) => Math.max(0.6, z - 0.15))}
          className="px-2 py-1 text-2xs font-mono text-studio-300 hover:text-white hover:bg-studio-800 rounded transition-colors"
          title="Zoom Out"
        >
          -
        </button>
        <div className="h-4 w-px bg-studio-700" />
        <span className="text-2xs font-mono text-studio-500 px-1.5">
          {Math.round(zoom * 100)}%
        </span>
      </div>

      {/* Floating Node Inventory Info */}
      <div className="absolute top-4 right-4 z-10 hidden sm:flex items-center gap-2 bg-studio-900/80 backdrop-blur-sm border border-studio-800 rounded-md px-3 py-1.5 text-2xs font-mono text-studio-400">
        <span className="text-amber-400">⚡ 1 Trigger</span>
        <span>·</span>
        <span className="text-accent-400">✨ 1 Agent</span>
        <span>·</span>
        <span className="text-emerald-400">🔧 {attachedTools.length} Tools</span>
        <span>·</span>
        <span className="text-blue-400">⊕ {actionNodes.length} Actions</span>
      </div>

      {/* Canvas Viewport Transformer */}
      <div
        className="w-full h-full relative"
        style={{
          transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
          transformOrigin: "0 0",
          transition: isPanning ? "none" : "transform 75ms ease-out",
        }}
      >
        {/* SVG Bezier Wire Connections Layer */}
        <svg
          className="absolute inset-0 pointer-events-none overflow-visible"
          style={{ width: 1400, height: 900 }}
        >
          <defs>
            <linearGradient id="wireGradient" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#6366f1" stopOpacity="0.8" />
              <stop offset="100%" stopColor="#10b981" stopOpacity="0.8" />
            </linearGradient>
            <filter id="glow">
              <feGaussianBlur stdDeviation="2" result="coloredBlur" />
              <feMerge>
                <feMergeNode in="coloredBlur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>

          {/* Trigger -> Agent Wire */}
          <path
            d={generateBezierPath(
              triggerNode.x + triggerNode.width,
              triggerNode.y + 55,
              agentNode.x,
              agentNode.y + 55
            )}
            fill="none"
            stroke={isRunning ? "#818cf8" : "#475569"}
            strokeWidth={isRunning ? "2.5" : "2"}
            strokeDasharray={isRunning ? "5 5" : undefined}
            className={isRunning ? "animate-pulse" : ""}
          />

          {/* Agent -> Action / Sub-agent Wires */}
          {actionNodes.map((action, idx) => {
            const startY = agentNode.y + 60 + idx * 35;
            const endY = action.y + 40;
            return (
              <path
                key={action.id}
                d={generateBezierPath(
                  agentNode.x + agentNode.width,
                  startY,
                  action.x,
                  endY
                )}
                fill="none"
                stroke={isRunning ? "#34d399" : "#475569"}
                strokeWidth={isRunning ? "2.5" : "1.8"}
                strokeDasharray={isRunning ? "6 4" : undefined}
                className={isRunning ? "animate-pulse" : ""}
              />
            );
          })}
        </svg>

        {/* 1. TRIGGER NODE (Left) */}
        <div
          onClick={() => setSelectedNodeId("trigger-input")}
          style={{
            position: "absolute",
            left: `${triggerNode.x}px`,
            top: `${triggerNode.y}px`,
            width: `${triggerNode.width}px`,
          }}
          className={`rounded-panel border bg-studio-900/95 backdrop-blur shadow-elevated p-3 cursor-pointer transition-all ${
            selectedNodeId === "trigger-input"
              ? "border-accent-500 ring-1 ring-accent-500 shadow-accent-900"
              : "border-studio-700/80 hover:border-studio-600"
          }`}
        >
          {/* Header */}
          <div className="flex items-center justify-between mb-2 pb-2 border-b border-studio-800">
            <div className="flex items-center gap-2">
              <span className="w-5 h-5 rounded bg-blue-950 text-blue-400 border border-blue-800 flex items-center justify-center text-xs">
                ⚡
              </span>
              <span className="text-2xs font-mono uppercase tracking-wider text-blue-400 font-semibold">
                TRIGGER
              </span>
            </div>
            <span className="text-2xs font-mono text-studio-500">v1</span>
          </div>

          <h4 className="text-xs font-semibold text-studio-100 truncate">
            Task Prompt & Input
          </h4>
          <p className="text-2xs text-studio-400 mt-1 leading-relaxed">
            Receives prompt from test runner or API execution call.
          </p>

          {/* Right Connection Port Handle */}
          <div
            style={{ right: "-7px", top: "50px" }}
            className="absolute w-3.5 h-3.5 rounded-full bg-studio-800 border-2 border-accent-400 shadow-sm"
            title="Trigger Output"
          />
        </div>

        {/* 2. MAIN ORCHESTRATOR AGENT NODE (Center) */}
        {activeAgent ? (
          <div
            onClick={() => {
              setSelectedNodeId(activeAgent.id);
              selectAgent?.(activeAgent.id);
            }}
            style={{
              position: "absolute",
              left: `${agentNode.x}px`,
              top: `${agentNode.y}px`,
              width: `${agentNode.width}px`,
            }}
            className={`rounded-panel border bg-studio-900/95 backdrop-blur-md shadow-elevated cursor-pointer transition-all ${
              selectedNodeId === activeAgent.id || selectedAgentId === activeAgent.id
                ? "border-emerald-500 ring-1 ring-emerald-500/80 shadow-emerald-950/50"
                : "border-studio-700/80 hover:border-studio-600"
            }`}
          >
            {/* Left Input Port Handle (connected from Trigger) */}
            <div
              style={{ left: "-7px", top: "50px" }}
              className="absolute w-3.5 h-3.5 rounded-full bg-studio-800 border-2 border-blue-400 shadow-sm"
              title="Agent Input Port"
            />

            {/* Node Header */}
            <div className="p-3.5 border-b border-studio-800 bg-studio-850/60 rounded-t-panel flex items-start justify-between">
              <div className="flex items-center gap-2.5 min-w-0">
                <span className="w-7 h-7 rounded-md bg-emerald-950/80 border border-emerald-700/80 text-emerald-400 flex items-center justify-center text-sm shrink-0">
                  ✨
                </span>
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="font-semibold text-studio-100 text-xs truncate">
                      {activeAgent.name}
                    </h3>
                    <span className="text-2xs font-mono uppercase bg-emerald-950 text-emerald-400 border border-emerald-800 px-1.5 py-0.2 rounded font-semibold shrink-0">
                      MAIN
                    </span>
                  </div>
                  <p className="text-2xs text-studio-400 truncate mt-0.5">
                    {activeAgent.description || "AI orchestration node"}
                  </p>
                </div>
              </div>
            </div>

            {/* Model & Config Strip */}
            <div className="px-3.5 py-2 border-b border-studio-800/80 bg-studio-950/40 flex items-center justify-between text-2xs font-mono">
              <span className="text-studio-500 uppercase tracking-wider">Model:</span>
              <span className="text-studio-300 bg-studio-800/80 px-2 py-0.5 rounded border border-studio-700/60 truncate max-w-[190px]">
                {activeAgent.provider} / {activeAgent.model}
              </span>
            </div>

            {/* Attached Tools Shelf (Concept 1 style) */}
            <div className="p-3.5 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-2xs font-mono font-semibold uppercase tracking-wider text-studio-400">
                  AI Agent Tools ({attachedTools.length})
                </span>
                <span className="text-2xs text-studio-500 font-mono">Capability Shelf</span>
              </div>

              {/* Tools List */}
              <div className="space-y-1.5 max-h-48 overflow-y-auto pr-0.5">
                {attachedTools.length === 0 ? (
                  <div className="p-3 text-center border border-dashed border-studio-800 rounded bg-studio-950/40 text-studio-500 text-2xs">
                    No tools attached to this agent.
                  </div>
                ) : (
                  attachedTools.map((tool, idx) => (
                    <div
                      key={tool.id}
                      className="flex items-center justify-between p-2 rounded bg-studio-800/60 border border-studio-700/60 hover:border-studio-600 transition-colors"
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="text-xs shrink-0">
                          {tool.kind.includes("search")
                            ? "🔍"
                            : tool.kind.includes("voice") || tool.kind.includes("audio")
                            ? "🎙️"
                            : tool.kind.includes("timeline") || tool.kind.includes("video")
                            ? "🎬"
                            : "🔧"}
                        </span>
                        <div className="min-w-0">
                          <span className="text-2xs text-studio-200 font-medium block truncate">
                            Tool #{idx + 1}: {tool.name}
                          </span>
                        </div>
                      </div>
                      <span className="text-2xs font-mono text-emerald-400 bg-emerald-950/40 border border-emerald-900/60 px-1 rounded shrink-0">
                        active
                      </span>
                    </div>
                  ))
                )}
              </div>

              {/* Functional "+ Add tool" button inside node */}
              <button
                onClick={handleAddToolClick}
                className="w-full mt-2 py-1.5 px-3 rounded border border-dashed border-studio-700 hover:border-accent-400 bg-studio-850/40 hover:bg-studio-800 text-studio-300 hover:text-white text-2xs font-mono font-medium flex items-center justify-center gap-1.5 transition-colors cursor-pointer"
              >
                <span>+</span> Add tool from catalog
              </button>
            </div>

            {/* Right Output Port Handles */}
            {actionNodes.map((_, idx) => (
              <div
                key={idx}
                style={{
                  right: "-7px",
                  top: `${50 + idx * 35}px`,
                }}
                className="absolute w-3.5 h-3.5 rounded-full bg-studio-800 border-2 border-emerald-400 shadow-sm"
                title={`Output Branch #${idx + 1}`}
              />
            ))}
          </div>
        ) : (
          <div
            style={{
              position: "absolute",
              left: `${agentNode.x}px`,
              top: `${agentNode.y}px`,
              width: `${agentNode.width}px`,
            }}
            className="rounded-panel border border-studio-800 p-8 text-center text-studio-500 text-xs bg-studio-900"
          >
            No agent found in project.
          </div>
        )}

        {/* 3. DOWNSTREAM ACTION & SUB-AGENT NODES (Right) */}
        {actionNodes.map((action) => (
          <div
            key={action.id}
            onClick={() => setSelectedNodeId(action.id)}
            style={{
              position: "absolute",
              left: `${action.x}px`,
              top: `${action.y}px`,
              width: `${action.width}px`,
            }}
            className={`rounded-panel border bg-studio-900/95 backdrop-blur shadow-elevated p-3 cursor-pointer transition-all ${
              selectedNodeId === action.id
                ? "border-accent-500 ring-1 ring-accent-500 shadow-accent-900"
                : "border-studio-700/80 hover:border-studio-600"
            }`}
          >
            {/* Left Input Port Handle */}
            <div
              style={{ left: "-7px", top: "35px" }}
              className="absolute w-3.5 h-3.5 rounded-full bg-studio-800 border-2 border-emerald-400 shadow-sm"
              title="Action Input Port"
            />

            <div className="flex items-center justify-between mb-1">
              <span className="text-2xs font-mono uppercase tracking-wider text-studio-400 font-semibold flex items-center gap-1.5">
                <span>{action.type === "subagent" ? "🤖 AGENT" : "⊕ ACTION"}</span>
              </span>
              <span className="text-2xs font-mono text-emerald-400 bg-emerald-950/30 border border-emerald-900 px-1 rounded">
                connected
              </span>
            </div>

            <h4 className="text-xs font-semibold text-studio-100 truncate">
              {action.title}
            </h4>
            <p className="text-2xs text-studio-400 mt-0.5 line-clamp-1 leading-relaxed">
              {action.subtitle}
            </p>
          </div>
        ))}
      </div>

      {/* Catalog modal fallback */}
      {catalogModalOpen && (
        <ToolCatalogModal onClose={() => setCatalogModalOpen(false)} />
      )}
    </div>
  );
}
