import { useRef, useState } from "react";
import { useStore } from "../store/useStore";
import { ToolCatalogModal } from "./ToolCatalogModal";

interface WorkflowCanvasProps {
  onOpenToolCatalog?: () => void;
  isRunning?: boolean;
}
type Point = { x: number; y: number };
type GraphNode = { id: string; title: string; subtitle: string; kind: "trigger" | "agent" | "subagent" | "action"; width: number; height: number; agentId?: string };

const initialPositions: Record<string, Point> = {
  "trigger-input": { x: 60, y: 190 },
  "agent-main": { x: 390, y: 125 },
  "action-execute": { x: 830, y: 130 },
  "action-notify": { x: 830, y: 280 },
};

export function WorkflowCanvas({ onOpenToolCatalog, isRunning = false }: WorkflowCanvasProps) {
  const agents = useStore((s) => s.agents) || [];
  const tools = useStore((s) => s.tools) || [];
  const selectedAgentId = useStore((s) => s.selectedAgentId);
  const selectAgent = useStore((s) => s.selectAgent);
  const activeAgent = agents.find((a) => a.id === selectedAgentId) || agents[0];
  const attachedTools = tools.filter((t) => activeAgent?.tool_ids?.includes(t.id));
  const childAgents = agents.filter((a) => activeAgent?.child_agent_ids?.includes(a.id));

  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState<Point>({ x: 12, y: 8 });
  const [positions, setPositions] = useState<Record<string, Point>>({});
  const [selectedNodeId, setSelectedNodeId] = useState<string>(activeAgent?.id || "trigger-input");
  const [drag, setDrag] = useState<{ id: string | null; startX: number; startY: number; origin: Point; moved: boolean }>({ id: null, startX: 0, startY: 0, origin: { x: 0, y: 0 }, moved: false });
  const [isPanning, setIsPanning] = useState(false);
  const [panStart, setPanStart] = useState<{ x: number; y: number; origin: Point }>({ x: 0, y: 0, origin: pan });
  const [catalogModalOpen, setCatalogModalOpen] = useState(false);
  const canvasRef = useRef<HTMLDivElement>(null);

  const nodes: GraphNode[] = [
    { id: "trigger-input", title: "Task prompt & input", subtitle: "Receives a task from chat or API", kind: "trigger", width: 236, height: 112 },
    ...(activeAgent ? [{ id: activeAgent.id, agentId: activeAgent.id, title: activeAgent.name, subtitle: `${activeAgent.provider} · ${activeAgent.model}`, kind: "agent" as const, width: 310, height: 226 + Math.min(attachedTools.length, 3) * 34 }] : []),
    ...childAgents.map((a) => ({ id: `child-${a.id}`, agentId: a.id, title: a.name, subtitle: `Sub-agent · ${a.model}`, kind: "subagent" as const, width: 240, height: 94 })),
    { id: "action-execute", title: "Synthesize results", subtitle: "Combine outputs into a final response", kind: "action", width: 240, height: 94 },
    { id: "action-notify", title: "Stream & log traces", subtitle: "Execution events and telemetry", kind: "action", width: 240, height: 94 },
  ];
  const defaults: Record<string, Point> = {
    ...initialPositions,
    ...(activeAgent ? { [activeAgent.id]: initialPositions["agent-main"] } : {}),
    ...Object.fromEntries(childAgents.map((a, i) => [`child-${a.id}`, { x: 830, y: 130 + i * 122 }])),
    "action-execute": { x: 830, y: 130 + childAgents.length * 122 },
    "action-notify": { x: 830, y: 250 + childAgents.length * 122 },
  };
  const at = (id: string) => positions[id] || defaults[id] || { x: 830, y: 420 };
  const pos = (id: string, p: Point) => setPositions((old) => ({ ...old, [id]: p }));
  const selectedAgent = agents.find((a) => a.id === selectedNodeId || `child-${a.id}` === selectedNodeId);
  const handlePointerDown = (e: React.PointerEvent, node: GraphNode) => {
    if (e.button !== 0) return;
    e.preventDefault();
    e.stopPropagation();
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    const p = at(node.id);
    setSelectedNodeId(node.id);
    if (node.agentId) selectAgent?.(node.agentId);
    setDrag({ id: node.id, startX: e.clientX, startY: e.clientY, origin: p, moved: false });
  };
  const handlePointerMove = (e: React.PointerEvent) => {
    if (drag.id) {
      const dx = (e.clientX - drag.startX) / zoom;
      const dy = (e.clientY - drag.startY) / zoom;
      if (!drag.moved && Math.abs(dx) + Math.abs(dy) > 3) setDrag((d) => ({ ...d, moved: true }));
      pos(drag.id, { x: Math.max(0, drag.origin.x + dx), y: Math.max(0, drag.origin.y + dy) });
    } else if (isPanning) {
      setPan({ x: panStart.origin.x + e.clientX - panStart.x, y: panStart.origin.y + e.clientY - panStart.y });
    }
  };
  const handlePointerUp = () => { setDrag({ id: null, startX: 0, startY: 0, origin: { x: 0, y: 0 }, moved: false }); setIsPanning(false); };
  const handleWheel = (e: React.WheelEvent) => {
    if (e.ctrlKey || e.metaKey) {
      e.preventDefault();
      setZoom((z) => Math.max(0.45, Math.min(1.65, z + (e.deltaY < 0 ? 0.08 : -0.08))));
    }
  };
  const wire = (from: GraphNode, to: GraphNode) => {
    const a = at(from.id), b = at(to.id);
    return `M ${a.x + from.width} ${a.y + Math.min(from.height / 2, 70)} C ${a.x + from.width + 80} ${a.y + Math.min(from.height / 2, 70)}, ${b.x - 70} ${b.y + to.height / 2}, ${b.x} ${b.y + to.height / 2}`;
  };
  const trigger = nodes[0];
  const agentNode = nodes.find((n) => n.kind === "agent");
  const downstream = nodes.filter((n) => n.kind === "subagent" || n.kind === "action");
  const openCatalog = () => onOpenToolCatalog ? onOpenToolCatalog() : setCatalogModalOpen(true);

  return (
    <div ref={canvasRef} className="workflow-canvas h-full w-full relative overflow-hidden bg-studio-950 bg-grid-pattern" onWheel={handleWheel} onPointerMove={handlePointerMove} onPointerUp={handlePointerUp} onPointerCancel={handlePointerUp} onPointerDown={(e) => {
      if (e.target === canvasRef.current || (e.target as HTMLElement).dataset.canvasBackground === "true") {
        setIsPanning(true); setPanStart({ x: e.clientX, y: e.clientY, origin: pan });
      }
    }}>
      <div className="absolute z-20 top-4 left-4 flex items-center gap-1.5 rounded-xl border border-studio-700/80 bg-studio-900/90 p-1.5 shadow-elevated backdrop-blur-xl">
        <span className="px-2 text-2xs font-mono uppercase tracking-widest text-studio-400">Workflow</span>
        <span className="h-4 w-px bg-studio-700" />
        <button onClick={() => { setZoom(1); setPan({ x: 12, y: 8 }); }} className="rounded-lg px-2.5 py-1.5 text-xs text-studio-300 hover:bg-studio-800 hover:text-white">Fit view</button>
        <button aria-label="Zoom out" onClick={() => setZoom((z) => Math.max(.45, z - .1))} className="rounded-lg px-2.5 py-1.5 text-sm text-studio-300 hover:bg-studio-800">−</button>
        <span className="min-w-12 text-center text-2xs font-mono text-studio-400">{Math.round(zoom * 100)}%</span>
        <button aria-label="Zoom in" onClick={() => setZoom((z) => Math.min(1.65, z + .1))} className="rounded-lg px-2.5 py-1.5 text-sm text-studio-300 hover:bg-studio-800">+</button>
      </div>
      <div className="absolute z-10 top-4 right-4 rounded-xl border border-studio-800 bg-studio-900/85 px-3 py-2 text-xs text-studio-400 backdrop-blur-lg">
        <span className="text-amber-300">⚡ 1 Trigger</span><span className="mx-2 text-studio-700">/</span><span className="text-emerald-300">{agents.length} Agents</span><span className="mx-2 text-studio-700">/</span><span className="text-cyan-300">{attachedTools.length} Tools</span>
      </div>
      <div data-canvas-background="true" className="absolute inset-0" style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`, transformOrigin: "0 0", transition: drag.id || isPanning ? "none" : "transform 100ms ease-out" }}>
        <svg className="absolute overflow-visible pointer-events-none" style={{ width: 1600, height: 1200, left: 0, top: 0 }}>
          <defs><linearGradient id="workflow-wire" x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" stopColor="#6366f1" /><stop offset="100%" stopColor="#34d399" /></linearGradient></defs>
          {agentNode && <path d={wire(trigger, agentNode)} fill="none" stroke="url(#workflow-wire)" strokeWidth="2.2" strokeDasharray={isRunning ? "6 6" : undefined} className={isRunning ? "animate-pulse" : ""} />}
          {agentNode && downstream.map((n) => <path key={n.id} d={wire(agentNode, n)} fill="none" stroke={selectedNodeId === n.id ? "#818cf8" : "#3c4b65"} strokeWidth={selectedNodeId === n.id ? 2.5 : 1.8} strokeDasharray={isRunning ? "5 5" : undefined} />)}
        </svg>
        {nodes.map((node) => {
          const p = at(node.id);
          const isSelected = selectedNodeId === node.id || (!!node.agentId && selectedAgentId === node.agentId);
          const tone = node.kind === "trigger" ? "amber" : node.kind === "agent" || node.kind === "subagent" ? "emerald" : "indigo";
          const border = isSelected ? "border-accent-400 ring-2 ring-accent-500/25 shadow-[0_0_32px_rgba(99,102,241,.14)]" : "border-studio-700/80 hover:border-studio-500";
          return <div key={node.id} role="button" tabIndex={0} aria-label={`Select and drag ${node.title}`} aria-pressed={isSelected} onPointerDown={(e) => handlePointerDown(e, node)} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setSelectedNodeId(node.id); if (node.agentId) selectAgent?.(node.agentId); } }} style={{ position: "absolute", left: p.x, top: p.y, width: node.width, minHeight: node.height, touchAction: "none" }} className={`group rounded-2xl border bg-studio-900/95 shadow-elevated backdrop-blur-xl transition-[border-color,box-shadow] duration-150 ${border} ${drag.id === node.id ? "z-10 cursor-grabbing scale-[1.015]" : "cursor-grab"}`}>
            <div className={`flex items-center gap-3 rounded-t-2xl border-b border-studio-800/80 px-4 py-3 ${node.kind === "agent" ? "bg-emerald-950/35" : "bg-studio-850/70"}`}>
              <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border text-base ${tone === "amber" ? "border-amber-800 bg-amber-950/70 text-amber-300" : tone === "emerald" ? "border-emerald-800 bg-emerald-950/70 text-emerald-300" : "border-indigo-800 bg-indigo-950/70 text-indigo-300"}`}>{node.kind === "trigger" ? "⚡" : node.kind === "agent" || node.kind === "subagent" ? "✳" : "⌘"}</span>
              <div className="min-w-0 flex-1"><div className="text-[10px] font-mono uppercase tracking-[.18em] text-studio-400">{node.kind === "trigger" ? "Entry point" : node.kind === "agent" ? "Orchestrator" : node.kind === "subagent" ? "Sub-agent" : "Pipeline step"}</div><h3 className="mt-0.5 truncate text-sm font-semibold text-studio-100">{node.title}</h3></div>
              <span className={`h-2 w-2 rounded-full ${isRunning && node.kind !== "trigger" ? "bg-amber-300 animate-pulse" : isSelected ? "bg-accent-300" : "bg-studio-600"}`} />
            </div>
            <div className="px-4 py-3">
              <p className="text-xs leading-relaxed text-studio-400">{node.subtitle}</p>
              {node.kind === "agent" && <><div className="mt-3 flex items-center justify-between border-t border-studio-800 pt-2 text-xs"><span className="text-studio-400">Attached capabilities</span><span className="rounded-md border border-emerald-900 bg-emerald-950/40 px-2 py-0.5 font-mono text-emerald-300">{attachedTools.length} tools</span></div>{attachedTools.slice(0,3).map((tool) => <div key={tool.id} className="mt-1.5 flex items-center gap-2 rounded-lg border border-studio-800 bg-studio-950/70 px-2.5 py-2 text-xs text-studio-300"><span className="text-emerald-300">↳</span><span className="truncate">{tool.name}</span><span className="ml-auto text-[10px] text-emerald-400">ready</span></div>)}<button onPointerDown={(e) => e.stopPropagation()} onClick={(e) => { e.stopPropagation(); openCatalog(); }} className="mt-2 w-full rounded-lg border border-dashed border-studio-700 px-3 py-2 text-xs text-studio-300 transition hover:border-accent-400 hover:bg-accent-900/20 hover:text-white">＋ Add capability</button></>}
              {node.kind === "subagent" && <div className="mt-2 text-[11px] font-mono text-emerald-300">↳ linked to orchestrator</div>}
            </div>
            <span className={`absolute -left-1.5 top-1/2 h-3 w-3 -translate-y-1/2 rounded-full border-2 border-studio-900 ${tone === "amber" ? "bg-amber-300" : "bg-emerald-300"}`} />
            <span className="absolute -right-1.5 top-1/2 h-3 w-3 -translate-y-1/2 rounded-full border-2 border-studio-900 bg-accent-300" />
            {isSelected && <span className="absolute -top-2 right-4 rounded-full border border-accent-400/40 bg-studio-950 px-2 py-0.5 text-[9px] font-mono uppercase tracking-wider text-accent-300">Selected · drag to move</span>}
          </div>;
        })}
      </div>
      <div className="absolute bottom-4 left-4 rounded-lg border border-studio-800/80 bg-studio-900/85 px-3 py-2 text-[11px] text-studio-500 backdrop-blur-md">Drag nodes to arrange · Drag empty canvas to pan · Ctrl/⌘ + scroll to zoom</div>
      {selectedAgent && <div className="absolute bottom-4 right-4 max-w-xs rounded-xl border border-accent-500/20 bg-studio-900/90 px-3 py-2 text-xs text-studio-300 shadow-elevated backdrop-blur-xl"><span className="text-accent-300">Inspector target</span><span className="ml-2 font-semibold text-white">{selectedAgent.name}</span></div>}
      {catalogModalOpen && <ToolCatalogModal onClose={() => setCatalogModalOpen(false)} />}
    </div>
  );
}
