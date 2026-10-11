import { useEffect, useRef, useState } from "react";
import { useStore } from "../store/useStore";
import { ToolCatalogModal } from "./ToolCatalogModal";
import { Icon } from "./ui/Icon";

interface WorkflowCanvasProps { onOpenToolCatalog?: () => void; onOpenLogs?: () => void; isRunning?: boolean; }
type Point = { x: number; y: number };
type GraphNode = { id: string; title: string; subtitle: string; kind: "trigger" | "agent" | "subagent" | "candidate" | "action"; width: number; height: number; agentId?: string };
type WorkflowConnection = { id: string; source: string; target: string };
const initialPositions: Record<string, Point> = { "trigger-input": { x: 60, y: 190 }, "agent-main": { x: 390, y: 125 }, "action-execute": { x: 830, y: 130 }, "action-notify": { x: 830, y: 280 } };

export function WorkflowCanvas({ onOpenToolCatalog, onOpenLogs, isRunning = false }: WorkflowCanvasProps) {
  const agents = useStore((s) => s.agents) || [];
  const tools = useStore((s) => s.tools) || [];
  const projectId = useStore((s) => s.project?.id ?? null);
  const selectedAgentId = useStore((s) => s.selectedAgentId);
  const selectAgent = useStore((s) => s.selectAgent);
  const attachChildToAgent = useStore((s) => s.attachChildToAgent);
  const detachChildFromAgent = useStore((s) => s.detachChildFromAgent);
  const activeAgent = agents.find((a) => a.id === selectedAgentId) || agents[0];
  const attachedTools = tools.filter((tool) => activeAgent?.tool_ids?.includes(tool.id));
  const otherAgents = agents.filter((agent) => agent.id !== activeAgent?.id);
  const delegatedIds = activeAgent?.child_agent_ids || [];

  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState<Point>({ x: 12, y: 8 });
  const [positions, setPositions] = useState<Record<string, Point>>({});
  const [selectedNodeId, setSelectedNodeId] = useState<string>(activeAgent?.id || "trigger-input");
  const [drag, setDrag] = useState<{ id: string | null; startX: number; startY: number; origin: Point; moved: boolean }>({ id: null, startX: 0, startY: 0, origin: { x: 0, y: 0 }, moved: false });
  const [isPanning, setIsPanning] = useState(false);
  const [panStart, setPanStart] = useState<{ x: number; y: number; origin: Point }>({ x: 0, y: 0, origin: pan });
  const [catalogModalOpen, setCatalogModalOpen] = useState(false);
  const [connections, setConnections] = useState<WorkflowConnection[]>([]);
  const [connectionDraft, setConnectionDraft] = useState<{ sourceId: string; sourcePoint: Point; point: Point } | null>(null);
  const [connectionNotice, setConnectionNotice] = useState<string | null>(null);
  const storageKey = projectId && activeAgent ? `agentforge.workflow.connections.${projectId}.${activeAgent.id}` : null;
  const loadedKey = useRef<string | null>(null);
  const canvasRef = useRef<HTMLDivElement>(null);

  const nodes: GraphNode[] = [
    { id: "trigger-input", title: "Task input", subtitle: "Receives a task from chat or API", kind: "trigger", width: 236, height: 112 },
    ...(activeAgent ? [{ id: activeAgent.id, agentId: activeAgent.id, title: activeAgent.name, subtitle: `${activeAgent.provider} · ${activeAgent.model || "No model"}`, kind: "agent" as const, width: 300, height: 184 + Math.min(attachedTools.length, 3) * 30 }] : []),
    ...otherAgents.map((agent) => ({
      id: `child-${agent.id}`, agentId: agent.id, title: agent.name,
      subtitle: delegatedIds.includes(agent.id) ? `Delegated · ${agent.model || "No model"}` : "Available to delegate",
      kind: delegatedIds.includes(agent.id) ? "subagent" as const : "candidate" as const,
      width: 236, height: 92,
    })),
    { id: "action-execute", title: "Synthesize results", subtitle: "Combine outputs into a final response", kind: "action", width: 236, height: 92 },
    { id: "action-notify", title: "Execution trace", subtitle: "Emit events and logs", kind: "action", width: 236, height: 92 },
  ];
  const defaults = (): WorkflowConnection[] => [
    ...(activeAgent ? [{ id: `trigger-input->${activeAgent.id}`, source: "trigger-input", target: activeAgent.id }] : []),
    ...(activeAgent ? [{ id: `${activeAgent.id}->action-execute`, source: activeAgent.id, target: "action-execute" }] : []),
    { id: "action-execute->action-notify", source: "action-execute", target: "action-notify" },
    ...otherAgents.filter((agent) => delegatedIds.includes(agent.id)).map((agent) => ({ id: `${activeAgent?.id}->child-${agent.id}`, source: activeAgent?.id ?? "", target: `child-${agent.id}` })),
  ];

  useEffect(() => {
    if (!storageKey) return;
    loadedKey.current = null;
    let saved: WorkflowConnection[] | null = null;
    try {
      const raw = window.localStorage.getItem(storageKey);
      if (raw) {
        const parsed: unknown = JSON.parse(raw);
        if (Array.isArray(parsed) && parsed.every((edge) => edge && typeof edge.source === "string" && typeof edge.target === "string")) saved = parsed.map((edge) => ({ id: `${edge.source}->${edge.target}`, source: edge.source, target: edge.target }));
      }
    } catch { /* Private browsing can disable storage without disabling graph editing. */ }
    setConnections(saved ?? defaults());
    loadedKey.current = storageKey;
  }, [storageKey]);

  useEffect(() => {
    if (!storageKey || loadedKey.current !== storageKey) return;
    try { window.localStorage.setItem(storageKey, JSON.stringify(connections)); } catch { /* Keep in-session edits. */ }
  }, [storageKey, connections]);

  const childPositions = Object.fromEntries(otherAgents.map((agent, index) => [`child-${agent.id}`, { x: 790, y: 125 + index * 116 }]));
  const at = (id: string): Point => positions[id] || (activeAgent && id === activeAgent.id ? initialPositions["agent-main"] : null) || childPositions[id] || initialPositions[id] || { x: 830, y: 420 };
  const pos = (id: string, point: Point) => setPositions((old) => ({ ...old, [id]: point }));
  const selectedAgent = agents.find((agent) => agent.id === selectedNodeId || `child-${agent.id}` === selectedNodeId);
  const nodeById = (id: string) => nodes.find((node) => node.id === id);

  const handlePointerDown = (event: React.PointerEvent, node: GraphNode) => {
    if (event.button !== 0) return;
    event.preventDefault(); event.stopPropagation();
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
    const point = at(node.id);
    setSelectedNodeId(node.id);
    if (node.agentId) selectAgent?.(node.agentId);
    setDrag({ id: node.id, startX: event.clientX, startY: event.clientY, origin: point, moved: false });
  };
  const beginConnection = (event: React.PointerEvent<HTMLButtonElement>, node: GraphNode) => {
    event.preventDefault(); event.stopPropagation(); event.currentTarget.setPointerCapture(event.pointerId);
    const point = at(node.id);
    setSelectedNodeId(node.id);
    setDrag({ id: null, startX: 0, startY: 0, origin: { x: 0, y: 0 }, moved: false });
    setIsPanning(false);
    setConnectionDraft({ sourceId: node.id, sourcePoint: { x: point.x + node.width, y: point.y + Math.min(node.height / 2, 70) }, point: { x: point.x + node.width, y: point.y + Math.min(node.height / 2, 70) } });
  };
  const handlePointerMove = (event: React.PointerEvent) => {
    if (connectionDraft) {
      const rect = canvasRef.current?.getBoundingClientRect();
      if (rect) setConnectionDraft((draft) => draft ? { ...draft, point: { x: (event.clientX - rect.left - pan.x) / zoom, y: (event.clientY - rect.top - pan.y) / zoom } } : draft);
      return;
    }
    if (drag.id) {
      const dx = (event.clientX - drag.startX) / zoom, dy = (event.clientY - drag.startY) / zoom;
      if (!drag.moved && Math.abs(dx) + Math.abs(dy) > 3) setDrag((old) => ({ ...old, moved: true }));
      pos(drag.id, { x: Math.max(0, drag.origin.x + dx), y: Math.max(0, drag.origin.y + dy) });
    } else if (isPanning) setPan({ x: panStart.origin.x + event.clientX - panStart.x, y: panStart.origin.y + event.clientY - panStart.y });
  };
  const handlePointerUp = (event?: React.PointerEvent) => {
    if (connectionDraft && event) {
      const target = document.elementFromPoint(event.clientX, event.clientY)?.closest<HTMLElement>("[data-port='input']");
      const targetId = target?.dataset.nodeId, sourceId = connectionDraft.sourceId;
      if (targetId && targetId !== sourceId && nodeById(sourceId) && nodeById(targetId)) {
        const id = `${sourceId}->${targetId}`;
        if (!connections.some((edge) => edge.source === sourceId && edge.target === targetId)) {
          setConnections((current) => [...current, { id, source: sourceId, target: targetId }]);
          const from = nodeById(sourceId), to = nodeById(targetId);
          if (from?.agentId && to?.agentId && (to.kind === "subagent" || to.kind === "candidate")) {
            void attachChildToAgent(from.agentId, to.agentId).then(() => setConnectionNotice("Delegation updated")).catch((error: unknown) => {
              setConnections((current) => current.filter((edge) => edge.id !== id));
              setConnectionNotice(error instanceof Error ? error.message : "Could not update delegation");
            });
          } else setConnectionNotice("Connection saved");
        }
      }
    }
    setConnectionDraft(null);
    setDrag({ id: null, startX: 0, startY: 0, origin: { x: 0, y: 0 }, moved: false });
    setIsPanning(false);
  };
  const removeConnection = async (connection: WorkflowConnection) => {
    setConnections((current) => current.filter((edge) => edge.id !== connection.id));
    const from = nodeById(connection.source), to = nodeById(connection.target);
    if (from?.agentId && to?.agentId && (to.kind === "subagent" || to.kind === "candidate")) {
      try { await detachChildFromAgent(from.agentId, to.agentId); setConnectionNotice("Delegation removed"); }
      catch (error) { setConnections((current) => [...current, connection]); setConnectionNotice(error instanceof Error ? error.message : "Could not remove delegation"); }
    } else setConnectionNotice("Connection removed");
  };
  const handleWheel = (event: React.WheelEvent) => {
    if (event.ctrlKey || event.metaKey) { event.preventDefault(); setZoom((value) => Math.max(0.45, Math.min(1.65, value + (event.deltaY < 0 ? 0.08 : -0.08)))); }
  };
  const wire = (from: GraphNode, to: GraphNode) => {
    const start = at(from.id), end = at(to.id), startY = start.y + Math.min(from.height / 2, 70), endY = end.y + Math.min(to.height / 2, 70);
    return `M ${start.x + from.width} ${startY} C ${start.x + from.width + 70} ${startY}, ${end.x - 70} ${endY}, ${end.x} ${endY}`;
  };
  const openCatalog = () => onOpenToolCatalog ? onOpenToolCatalog() : setCatalogModalOpen(true);
  const renderedConnections = connections.filter((edge) => nodeById(edge.source) && nodeById(edge.target));

  return (
    <div ref={canvasRef} className="workflow-canvas h-full w-full relative overflow-hidden bg-studio-950 bg-grid-pattern"
      onWheel={handleWheel} onPointerMove={handlePointerMove} onPointerUp={handlePointerUp}
      onPointerCancel={() => { setConnectionDraft(null); setDrag({ id: null, startX: 0, startY: 0, origin: { x: 0, y: 0 }, moved: false }); setIsPanning(false); }}
      onPointerDown={(event) => { if (event.target === canvasRef.current || (event.target as HTMLElement).dataset.canvasBackground === "true") { setIsPanning(true); setPanStart({ x: event.clientX, y: event.clientY, origin: pan }); } }}>
      <div className="absolute z-20 top-3 left-3 flex items-center gap-1 border border-studio-700/80 bg-studio-900/95 p-1 shadow-studio">
        <span className="px-2 text-2xs font-mono uppercase tracking-wider text-studio-400">Workflow</span><span className="h-4 w-px bg-studio-700" />
        <button onClick={() => { setZoom(1); setPan({ x: 12, y: 8 }); }} className="px-2 py-1.5 text-xs text-studio-300 hover:bg-studio-800 hover:text-white">Fit</button>
        <button aria-label="Zoom out" onClick={() => setZoom((value) => Math.max(0.45, value - 0.1))} className="px-2 py-1.5 text-sm text-studio-300 hover:bg-studio-800">−</button>
        <span className="min-w-10 text-center text-2xs font-mono text-studio-400">{Math.round(zoom * 100)}%</span>
        <button aria-label="Zoom in" onClick={() => setZoom((value) => Math.min(1.65, value + 0.1))} className="px-2 py-1.5 text-sm text-studio-300 hover:bg-studio-800">+</button>
        {onOpenLogs && <button onClick={onOpenLogs} className="ml-1 inline-flex items-center gap-1 border-l border-studio-700 px-2 py-1.5 text-xs text-studio-300 hover:bg-studio-800 hover:text-white" title="View logs"><Icon name="logs" size={14} /> View logs</button>}
      </div>
      <div className="absolute right-3 top-3 rounded border border-studio-800 bg-studio-900/90 px-2.5 py-1.5 text-2xs text-studio-400"><span className="text-studio-300">{nodes.length} nodes</span><span className="mx-2 text-studio-700">·</span><span className="text-studio-300">{renderedConnections.length} connections</span></div>
      <div data-canvas-background="true" className="absolute inset-0" style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`, transformOrigin: "0 0", transition: drag.id || isPanning || connectionDraft ? "none" : "transform 100ms ease-out" }}>
        <svg className="absolute overflow-visible pointer-events-none" style={{ width: 1800, height: 1400, left: 0, top: 0 }}>
          {renderedConnections.map((edge) => {
            const from = nodeById(edge.source)!, to = nodeById(edge.target)!;
            return <path key={edge.id} d={wire(from, to)} fill="none" stroke={to.kind === "subagent" ? "#60a5fa" : "#52637a"} strokeWidth="2" strokeLinecap="round" pointerEvents="stroke" onClick={(event) => { event.stopPropagation(); void removeConnection(edge); }} aria-label={`Remove connection from ${from.title} to ${to.title}`} className="cursor-pointer" />;
          })}
          {connectionDraft && <path d={`M ${connectionDraft.sourcePoint.x} ${connectionDraft.sourcePoint.y} C ${connectionDraft.sourcePoint.x + 50} ${connectionDraft.sourcePoint.y}, ${connectionDraft.point.x - 50} ${connectionDraft.point.y}, ${connectionDraft.point.x} ${connectionDraft.point.y}`} fill="none" stroke="#60a5fa" strokeWidth="2" strokeDasharray="5 4" strokeLinecap="round" />}
        </svg>
        {nodes.map((node) => {
          const point = at(node.id), selected = selectedNodeId === node.id || (!!node.agentId && selectedAgentId === node.agentId);
          const tone = node.kind === "trigger" ? "amber" : node.kind === "agent" || node.kind === "subagent" || node.kind === "candidate" ? "blue" : "slate";
          const border = selected ? "border-accent-400 ring-1 ring-accent-500/20" : "border-studio-700 hover:border-studio-500";
          return (
            <div key={node.id} data-node-id={node.id} role="group" aria-label={node.title} tabIndex={-1}
              onPointerDown={(event) => handlePointerDown(event, node)}
              onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setSelectedNodeId(node.id); if (node.agentId) selectAgent?.(node.agentId); } }}
              style={{ position: "absolute", left: point.x, top: point.y, width: node.width, minHeight: node.height, touchAction: "none" }}
              className={`group border bg-studio-900 shadow-studio transition-[border-color] duration-150 ${border} ${drag.id === node.id ? "z-10 cursor-grabbing" : "cursor-grab"}`}>
              <div className="flex items-center gap-3 border-b border-studio-800 bg-studio-850 px-3 py-2.5">
                <span className={`flex h-8 w-8 shrink-0 items-center justify-center border ${tone === "amber" ? "border-amber-800/80 bg-amber-950/40 text-amber-300" : tone === "blue" ? "border-blue-800/80 bg-blue-950/40 text-blue-300" : "border-studio-700 bg-studio-800 text-studio-300"}`}>{node.kind === "trigger" ? "↳" : node.kind === "agent" || node.kind === "subagent" || node.kind === "candidate" ? <Icon name="agents" size={17} /> : <Icon name="workflow" size={17} />}</span>
                <div className="min-w-0 flex-1"><div className="text-[10px] font-mono uppercase tracking-wider text-studio-500">{node.kind === "trigger" ? "Trigger" : node.kind === "agent" ? "Selected agent" : node.kind === "subagent" ? "Delegated agent" : node.kind === "candidate" ? "Agent" : "Step"}</div><h3 className="mt-0.5 truncate text-sm font-semibold text-studio-100">{node.title}</h3></div>
                {isRunning && <span className="h-1.5 w-1.5 rounded-full bg-amber-300 animate-pulse" />}
              </div>
              <div className="px-3 py-2.5">
                <p className="text-xs leading-relaxed text-studio-400">{node.subtitle}</p>
                {node.kind === "agent" && <>
                  <div className="mt-3 flex items-center justify-between border-t border-studio-800 pt-2 text-xs"><span className="text-studio-400">Tools attached</span><span className="font-mono text-studio-300">{attachedTools.length}</span></div>
                  {attachedTools.slice(0,3).map((tool) => <div key={tool.id} className="mt-1.5 flex items-center gap-2 border-l-2 border-studio-600 bg-studio-950 px-2 py-1.5 text-xs text-studio-300"><span className="truncate">{tool.name}</span><span className="ml-auto text-[10px] text-studio-500">{tool.kind}</span></div>)}
                  <button onPointerDown={(event) => event.stopPropagation()} onClick={(event) => { event.stopPropagation(); openCatalog(); }} className="mt-2 flex w-full items-center gap-2 border border-dashed border-studio-700 px-2 py-1.5 text-xs text-studio-300 hover:border-accent-400 hover:text-white"><Icon name="plus" size={14} /> Add capability</button>
                </>}
                {node.kind === "candidate" && <div className="mt-2 text-[11px] text-studio-500">Not delegated</div>}
              </div>
              <button type="button" data-node-id={node.id} data-port="input" aria-label={`Connect to ${node.title}`} className="absolute -left-2 top-1/2 z-20 h-4 w-4 -translate-y-1/2 rounded-full border-2 border-studio-900 bg-studio-400 transition-colors hover:bg-accent-300 hover:ring-2 hover:ring-accent-500/30" title="Connection input" />
              <button type="button" data-node-id={node.id} data-port="output" aria-label={`Connect from ${node.title}`} onPointerDown={(event) => beginConnection(event, node)} className="absolute -right-2 top-1/2 z-20 h-4 w-4 -translate-y-1/2 rounded-full border-2 border-studio-900 bg-accent-400 transition-colors hover:bg-accent-300 hover:ring-2 hover:ring-accent-500/30" title="Drag to another node input" />
            </div>
          );
        })}
      </div>
      <div className="absolute bottom-3 left-3 max-w-[calc(100%-1.5rem)] border border-studio-800 bg-studio-900/95 px-3 py-2 text-[11px] leading-5 text-studio-500">Drag nodes to move · Drag an output dot to an input dot to connect · Click a wire to remove it · Ctrl/⌘ + scroll to zoom</div>
      {connectionNotice && <div role="status" className="absolute bottom-3 right-3 max-w-sm border border-studio-700 bg-studio-900 px-3 py-2 text-xs text-studio-300">{connectionNotice}</div>}
      {selectedAgent && <div className="absolute bottom-16 right-3 max-w-xs border border-studio-800 bg-studio-900 px-3 py-2 text-xs text-studio-300"><span className="text-studio-500">Selected</span><span className="ml-2 font-semibold text-studio-100">{selectedAgent.name}</span></div>}
      {catalogModalOpen && <ToolCatalogModal onClose={() => setCatalogModalOpen(false)} />}
    </div>
  );
}
