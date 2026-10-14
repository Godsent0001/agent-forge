import { useEffect, useRef, useState } from "react";
import { useStore } from "../store/useStore";
import { ToolCatalogModal } from "./ToolCatalogModal";
import { Icon } from "./ui/Icon";

interface WorkflowCanvasProps { onOpenToolCatalog?: () => void; isRunning?: boolean; }
type Point = { x: number; y: number };
type GraphNode = {
  id: string; title: string; subtitle: string;
  kind: "trigger" | "agent" | "subagent" | "candidate" | "tool" | "tool-candidate";
  width: number; height: number; agentId?: string; toolId?: string;
};
type WorkflowConnection = { id: string; source: string; target: string };
const initialPositions: Record<string, Point> = {
  "trigger-input": { x: 60, y: 220 },
  "agent-main": { x: 390, y: 190 },
};

export function WorkflowCanvas({ onOpenToolCatalog, isRunning = false }: WorkflowCanvasProps) {
  const agents = useStore((s) => s.agents) || [];
  const tools = useStore((s) => s.tools) || [];
  const projectId = useStore((s) => s.project?.id ?? null);
  const selectedAgentId = useStore((s) => s.selectedAgentId);
  const selectAgent = useStore((s) => s.selectAgent);
  const attachChildToAgent = useStore((s) => s.attachChildToAgent);
  const detachChildFromAgent = useStore((s) => s.detachChildFromAgent);
  const attachToolToAgent = useStore((s) => s.attachToolToAgent);
  const detachToolFromAgent = useStore((s) => s.detachToolFromAgent);
  const activeAgent = agents.find((agent) => agent.id === selectedAgentId) || agents[0];
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
  const [connectionDraft, setConnectionDraft] = useState<{ sourceId: string; sourcePoint: Point; point: Point } | null>(null);
  const [connectionNotice, setConnectionNotice] = useState<string | null>(null);
  const storageKey = projectId && activeAgent ? `agentforge.workflow.connections.${projectId}.${activeAgent.id}` : null;
  const positionStorageKey = storageKey ? `${storageKey}.positions` : null;
  const canvasRef = useRef<HTMLDivElement>(null);
  const [layoutReadyKey, setLayoutReadyKey] = useState<string | null>(null);
  const fittedKey = useRef<string | null>(null);

  const nodes: GraphNode[] = [
    { id: "trigger-input", title: "Task input", subtitle: "Entry point for chat or API requests", kind: "trigger", width: 236, height: 92 },
    ...(activeAgent ? [{
      id: activeAgent.id, agentId: activeAgent.id, title: activeAgent.name,
      subtitle: `${activeAgent.provider} · ${activeAgent.model || "No model"}`,
      kind: "agent" as const, width: 300, height: 158,
    }] : []),
    ...otherAgents.map((agent) => ({
      id: `child-${agent.id}`, agentId: agent.id, title: agent.name,
      subtitle: delegatedIds.includes(agent.id) ? `Delegated · ${agent.model || "No model"}` : `Available · ${agent.model || "No model"}`,
      kind: delegatedIds.includes(agent.id) ? "subagent" as const : "candidate" as const,
      width: 236, height: 92,
    })),
    ...tools.map((tool) => {
      const linkedAgents = agents.filter((agent) => agent.tool_ids?.includes(tool.id));
      return {
        id: `tool-${tool.id}`, toolId: tool.id, title: tool.name,
        subtitle: linkedAgents.length ? `${tool.kind} · Used by ${linkedAgents.length} agent${linkedAgents.length === 1 ? "" : "s"}` : `${tool.kind} · Available capability`,
        kind: linkedAgents.length ? "tool" as const : "tool-candidate" as const,
        width: 236, height: 92,
      };
    }),
  ];

  const nodeIdForAgent = (agentId: string) => agentId === activeAgent?.id ? agentId : `child-${agentId}`;
  // Draw only actual runtime relationships; the task-input edge to the selected root is fixed.
  const connections: WorkflowConnection[] = [
    ...(activeAgent ? [{ id: `trigger-input->${activeAgent.id}`, source: "trigger-input", target: activeAgent.id }] : []),
    ...agents.flatMap((parent) => [
      ...(parent.child_agent_ids ?? [])
        .filter((childId) => agents.some((agent) => agent.id === childId))
        .map((childId) => ({
          id: `${nodeIdForAgent(parent.id)}->${nodeIdForAgent(childId)}`,
          source: nodeIdForAgent(parent.id), target: nodeIdForAgent(childId),
        })),
      ...(parent.tool_ids ?? [])
        .filter((toolId) => tools.some((tool) => tool.id === toolId))
        .map((toolId) => ({
          id: `${nodeIdForAgent(parent.id)}->tool-${toolId}`,
          source: nodeIdForAgent(parent.id), target: `tool-${toolId}`,
        })),
    ]),
  ];

  useEffect(() => {
    if (!positionStorageKey) { setPositions({}); return; }
    let saved: Record<string, Point> = {};
    try {
      const raw = window.localStorage.getItem(positionStorageKey);
      if (raw) {
        const parsed: unknown = JSON.parse(raw);
        if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
          saved = Object.fromEntries(Object.entries(parsed).filter((entry): entry is [string, Point] => {
            const value = entry[1] as Partial<Point> | null;
            return !!value && typeof value.x === "number" && Number.isFinite(value.x) && value.x >= 0 &&
              typeof value.y === "number" && Number.isFinite(value.y) && value.y >= 0;
          }));
        }
      }
    } catch { /* Ignore invalid saved layouts instead of blocking the editor. */ }
    setPositions(saved);
    setLayoutReadyKey(positionStorageKey);
  }, [positionStorageKey]);

  const childPositions = Object.fromEntries(otherAgents.map((agent, index) => [`child-${agent.id}`, { x: 790, y: 90 + index * 132 }]));
  const toolPositions = Object.fromEntries(tools.map((tool, index) => [`tool-${tool.id}`, { x: 1180, y: 90 + index * 116 }]));
  const at = (id: string): Point => positions[id] ||
    (activeAgent && id === activeAgent.id ? initialPositions["agent-main"] : null) ||
    childPositions[id] || toolPositions[id] || initialPositions[id] || { x: 830, y: 420 };
  const pos = (id: string, point: Point) => setPositions((old) => ({ ...old, [id]: point }));
  const selectedAgent = agents.find((agent) => agent.id === selectedNodeId || `child-${agent.id}` === selectedNodeId);
  const nodeById = (id: string) => nodes.find((node) => node.id === id);

  const handlePointerDown = (event: React.PointerEvent, node: GraphNode) => {
    if (event.button !== 0) return;
    event.preventDefault(); event.stopPropagation();
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
    const point = at(node.id);
    setSelectedNodeId(node.id);
    // Select on pointer-up, so dragging a node never reflows the graph mid-drag.
    setDrag({ id: node.id, startX: event.clientX, startY: event.clientY, origin: point, moved: false });
  };
  const beginConnection = (event: React.PointerEvent<HTMLButtonElement>, node: GraphNode) => {
    event.preventDefault(); event.stopPropagation(); event.currentTarget.setPointerCapture(event.pointerId);
    const point = at(node.id);
    setSelectedNodeId(node.id);
    // Do not promote a candidate agent when starting a connection from its output.
    setDrag({ id: null, startX: 0, startY: 0, origin: { x: 0, y: 0 }, moved: false });
    setIsPanning(false);
    setConnectionDraft({ sourceId: node.id, sourcePoint: { x: point.x + node.width, y: point.y + 40 }, point: { x: point.x + node.width, y: point.y + 40 } });
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
    if (drag.id && drag.moved && positionStorageKey && event) {
      const finalPoint = {
        x: Math.max(0, drag.origin.x + (event.clientX - drag.startX) / zoom),
        y: Math.max(0, drag.origin.y + (event.clientY - drag.startY) / zoom),
      };
      const nextPositions = { ...positions, [drag.id]: finalPoint };
      setPositions(nextPositions);
      try { window.localStorage.setItem(positionStorageKey, JSON.stringify(nextPositions)); } catch { /* Keep the layout for this session. */ }
    }
    if (drag.id && !drag.moved) {
      const clickedNode = nodeById(drag.id);
      if (clickedNode?.agentId) selectAgent?.(clickedNode.agentId);
    }
    if (connectionDraft && event) {
      const target = document.elementFromPoint(event.clientX, event.clientY)?.closest<HTMLElement>("[data-port='input']");
      const targetId = target?.dataset.nodeId;
      const source = nodeById(connectionDraft.sourceId);
      const targetNode = targetId ? nodeById(targetId) : undefined;
      if (source && targetNode && targetId !== source.id) {
        if (connections.some((edge) => edge.source === source.id && edge.target === targetNode.id)) {
          setConnectionNotice("These nodes are already connected.");
        } else if (source.agentId && targetNode.agentId) {
          setConnectionNotice("Connecting agents…");
          void attachChildToAgent(source.agentId, targetNode.agentId)
            .then(() => setConnectionNotice("Agent delegation connected."))
            .catch((error: unknown) => setConnectionNotice(error instanceof Error ? error.message : "Could not connect agents."));
        } else if (source.agentId && targetNode.toolId) {
          setConnectionNotice("Attaching tool…");
          void attachToolToAgent(source.agentId, targetNode.toolId)
            .then(() => setConnectionNotice("Tool attached to agent."))
            .catch((error: unknown) => setConnectionNotice(error instanceof Error ? error.message : "Could not attach tool."));
        } else {
          setConnectionNotice("Connect an agent output to another agent or to a tool.");
        }
      }
    }
    setConnectionDraft(null);
    setDrag({ id: null, startX: 0, startY: 0, origin: { x: 0, y: 0 }, moved: false });
    setIsPanning(false);
  };
  const removeConnection = async (connection: WorkflowConnection) => {
    const from = nodeById(connection.source), to = nodeById(connection.target);
    if (from?.agentId && to?.agentId) {
      try { await detachChildFromAgent(from.agentId, to.agentId); setConnectionNotice("Agent delegation removed."); }
      catch (error) { setConnectionNotice(error instanceof Error ? error.message : "Could not remove delegation."); }
    } else if (from?.agentId && to?.toolId) {
      try { await detachToolFromAgent(from.agentId, to.toolId); setConnectionNotice("Tool detached from agent."); }
      catch (error) { setConnectionNotice(error instanceof Error ? error.message : "Could not detach tool."); }
    }
  };
    const handleWheel = (event: React.WheelEvent) => {
    if (event.ctrlKey || event.metaKey) { event.preventDefault(); setZoom((value) => Math.max(0.45, Math.min(1.65, value + (event.deltaY < 0 ? 0.08 : -0.08)))); }
  };
  const wire = (from: GraphNode, to: GraphNode) => {
    const start = at(from.id), end = at(to.id);
    const startX = start.x + from.width, endX = end.x;
    const startY = start.y + 40, endY = end.y + 40;
    if (endX >= startX + 36) return `M ${startX} ${startY} C ${startX + 70} ${startY}, ${endX - 70} ${endY}, ${endX} ${endY}`;
    const liftY = Math.max(16, Math.min(startY, endY) - 54);
    return `M ${startX} ${startY} C ${startX + 54} ${startY}, ${startX + 54} ${liftY}, ${startX} ${liftY} C ${startX - 48} ${liftY}, ${endX - 48} ${liftY}, ${endX} ${endY}`;
  };

  const fitView = () => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect || nodes.length === 0) return;
    const all = nodes.map((node) => ({ point: at(node.id), width: node.width, height: node.height }));
    const minX = Math.min(...all.map(({ point }) => point.x));
    const minY = Math.min(...all.map(({ point }) => point.y));
    const maxX = Math.max(...all.map(({ point, width }) => point.x + width));
    const maxY = Math.max(...all.map(({ point, height }) => point.y + height));
    const contentWidth = Math.max(1, maxX - minX), contentHeight = Math.max(1, maxY - minY);
    const scale = Math.max(0.45, Math.min(1.65, (rect.width - 100) / contentWidth, (rect.height - 140) / contentHeight));
    setZoom(scale);
    setPan({ x: (rect.width - contentWidth * scale) / 2 - minX * scale, y: (rect.height - contentHeight * scale) / 2 - minY * scale });
  };

  // Show the whole graph the first time a workflow is opened (instead of nodes hidden behind panels).
  useEffect(() => {
    if (!positionStorageKey || layoutReadyKey !== positionStorageKey || fittedKey.current === positionStorageKey) return;
    if (nodes.length < 2) return;
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect || rect.width === 0 || rect.height === 0) return;
    fittedKey.current = positionStorageKey;
    fitView();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layoutReadyKey, positionStorageKey, nodes.length]);
  const openCatalog = () => onOpenToolCatalog ? onOpenToolCatalog() : setCatalogModalOpen(true);
  const renderedConnections = connections.filter((edge) => nodeById(edge.source) && nodeById(edge.target));

  return (
    <div ref={canvasRef} data-testid="workflow-canvas" className="workflow-canvas h-full w-full relative overflow-hidden bg-studio-950 bg-grid-pattern"
      onWheel={handleWheel} onPointerMove={handlePointerMove} onPointerUp={handlePointerUp}
      onPointerCancel={() => { setConnectionDraft(null); setDrag({ id: null, startX: 0, startY: 0, origin: { x: 0, y: 0 }, moved: false }); setIsPanning(false); }}
      onPointerDown={(event) => { if (event.target === canvasRef.current || (event.target as HTMLElement).dataset.canvasBackground === "true" || event.target instanceof SVGSVGElement) { setIsPanning(true); setPanStart({ x: event.clientX, y: event.clientY, origin: pan }); } }}>
      <div className="absolute z-20 top-3 left-3 flex items-center gap-1 border border-studio-700/80 bg-studio-900/95 p-1 shadow-studio">
        <span className="px-2 text-2xs font-mono uppercase tracking-wider text-studio-400">Workflow</span><span className="h-4 w-px bg-studio-700" />
        <button onClick={fitView} className="px-2 py-1.5 text-xs text-studio-300 hover:bg-studio-800 hover:text-white">Fit view</button>
        <button aria-label="Zoom out" onClick={() => setZoom((value) => Math.max(0.45, value - 0.1))} className="px-2 py-1.5 text-sm text-studio-300 hover:bg-studio-800">−</button>
        <span className="min-w-10 text-center text-2xs font-mono text-studio-400">{Math.round(zoom * 100)}%</span>
        <button aria-label="Zoom in" onClick={() => setZoom((value) => Math.min(1.65, value + 0.1))} className="px-2 py-1.5 text-sm text-studio-300 hover:bg-studio-800">+</button>

      </div>
      <div className="absolute right-3 top-3 rounded border border-studio-800 bg-studio-900/90 px-2.5 py-1.5 text-2xs text-studio-400"><span className="text-studio-300">{nodes.length} nodes</span><span className="mx-2 text-studio-700">·</span><span className="text-studio-300">{renderedConnections.length} connections</span></div>
      <div data-canvas-background="true" className="absolute inset-0" style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`, transformOrigin: "0 0", transition: drag.id || isPanning || connectionDraft ? "none" : "transform 100ms ease-out" }}>
        <svg aria-label="Workflow connections" className="absolute overflow-visible" style={{ width: 1800, height: 1400, left: 0, top: 0 }}>
          {renderedConnections.map((edge) => {
            const from = nodeById(edge.source)!, to = nodeById(edge.target)!, path = wire(from, to);
            const editable = !!from.agentId && (!!to.agentId || !!to.toolId);
            return <g key={edge.id}>
              {editable && <path d={path} fill="none" stroke="transparent" strokeWidth="14" pointerEvents="stroke" role="button" tabIndex={0}
                aria-label={`Remove connection from ${from.title} to ${to.title}`} className="cursor-pointer outline-none"
                onClick={(event) => { event.stopPropagation(); void removeConnection(edge); }}
                onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); void removeConnection(edge); } }}
              />}
              <path d={path} fill="none" stroke={to.toolId ? "#34d399" : to.kind === "subagent" ? "#60a5fa" : "#52637a"} strokeWidth="2" strokeLinecap="round" pointerEvents="none" />
            </g>;
          })}
                    {connectionDraft && <path d={`M ${connectionDraft.sourcePoint.x} ${connectionDraft.sourcePoint.y} C ${connectionDraft.sourcePoint.x + 50} ${connectionDraft.sourcePoint.y}, ${connectionDraft.point.x - 50} ${connectionDraft.point.y}, ${connectionDraft.point.x} ${connectionDraft.point.y}`} fill="none" stroke="#60a5fa" strokeWidth="2" strokeDasharray="5 4" strokeLinecap="round" pointerEvents="none" />}
        </svg>
        {nodes.map((node) => {
          const point = at(node.id), selected = selectedNodeId === node.id || (!!node.agentId && selectedAgentId === node.agentId);
          const tone = node.kind === "trigger" ? "amber" : node.toolId ? "emerald" : "blue";
          const border = selected ? "border-accent-400 ring-1 ring-accent-500/20" : "border-studio-700 hover:border-studio-500";
          return (
            <div key={node.id} data-node-id={node.id} role="group" aria-label={node.title} tabIndex={-1}
              onPointerDown={(event) => handlePointerDown(event, node)}
              onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setSelectedNodeId(node.id); if (node.agentId) selectAgent?.(node.agentId); } }}
              style={{ position: "absolute", left: point.x, top: point.y, width: node.width, minHeight: node.height, touchAction: "none" }}
              className={`group border bg-studio-900 shadow-studio transition-[border-color] duration-150 ${border} ${drag.id === node.id ? "z-10 cursor-grabbing" : "cursor-grab"}`}>
              <div className="flex items-center gap-3 border-b border-studio-800 bg-studio-850 px-3 py-2.5">
                <span className={`flex h-8 w-8 shrink-0 items-center justify-center border ${tone === "amber" ? "border-amber-800/80 bg-amber-950/40 text-amber-300" : tone === "blue" ? "border-blue-800/80 bg-blue-950/40 text-blue-300" : "border-emerald-800/80 bg-emerald-950/30 text-emerald-300"}`}>{node.kind === "trigger" ? "↳" : node.agentId ? <Icon name="agents" size={17} /> : <Icon name="tools" size={17} />}</span>
                <div className="min-w-0 flex-1"><div className="text-[10px] font-mono uppercase tracking-wider text-studio-500">{node.kind === "trigger" ? "Trigger" : node.kind === "agent" ? "Selected agent" : node.kind === "subagent" ? "Delegated agent" : node.kind === "candidate" ? "Agent" : node.kind === "tool" ? "Tool · attached" : "Tool · available"}</div><h3 className="mt-0.5 truncate text-sm font-semibold text-studio-100">{node.title}</h3></div>
                {isRunning && <span className="h-1.5 w-1.5 rounded-full bg-amber-300 animate-pulse" />}
              </div>
              <div className="px-3 py-2.5">
                <p className="text-xs leading-relaxed text-studio-400">{node.subtitle}</p>
                {node.kind === "agent" && <>
                  <div className="mt-3 flex items-center justify-between border-t border-studio-800 pt-2 text-xs"><span className="text-studio-400">Attached tools</span><span className="font-mono text-studio-300">{attachedTools.length}</span></div>
                  <p className="mt-2 text-[11px] leading-relaxed text-studio-500">Connect this agent to another agent to delegate work, or to a tool to add a capability.</p>
                  <button onPointerDown={(event) => event.stopPropagation()} onClick={(event) => { event.stopPropagation(); openCatalog(); }} className="mt-2 flex w-full items-center gap-2 border border-dashed border-studio-700 px-2 py-1.5 text-xs text-studio-300 hover:border-accent-400 hover:text-white"><Icon name="plus" size={14} /> Browse tools</button>
                </>}
                {node.kind === "candidate" && <div className="mt-2 text-[11px] text-studio-500">Drag an agent output here to delegate</div>}
                {node.kind === "tool-candidate" && <div className="mt-2 text-[11px] text-studio-500">Drag an agent output here to attach</div>}
                {node.kind === "tool" && <div className="mt-2 text-[11px] text-emerald-300/80">Connected to one or more agents</div>}
              </div>
              {node.kind !== "trigger" && <button type="button" data-node-id={node.id} data-port="input" aria-label={`Connect to ${node.title}`} onPointerDown={(event) => event.stopPropagation()} className="absolute -left-2 top-8 z-20 h-4 w-4 rounded-full border-2 border-studio-900 bg-studio-400 transition-colors hover:bg-accent-300 hover:ring-2 hover:ring-accent-500/30 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-300" title="Connection input" />}
              {node.agentId && <button type="button" data-node-id={node.id} data-port="output" aria-label={`Connect from ${node.title}`} onPointerDown={(event) => beginConnection(event, node)} className="absolute -right-2 top-8 z-20 h-4 w-4 rounded-full border-2 border-studio-900 bg-accent-400 transition-colors hover:bg-accent-300 hover:ring-2 hover:ring-accent-500/30 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-300" title="Drag to another agent or tool" />}
            </div>
          );
        })}
      </div>
      <div className="absolute bottom-3 left-3 max-w-[calc(100%-1.5rem)] border border-studio-800 bg-studio-900/95 px-3 py-2 text-[11px] leading-5 text-studio-500">Drag nodes to move · Connect an agent to another agent to delegate, or to a tool to attach it · Click an editable wire to remove it · Ctrl/⌘ + scroll to zoom</div>
      {connectionNotice && <div role="status" className="absolute bottom-3 right-3 flex max-w-sm items-start gap-3 border border-studio-700 bg-studio-900 px-3 py-2 text-xs text-studio-300 shadow-studio"><span>{connectionNotice}</span><button type="button" aria-label="Dismiss message" onClick={() => setConnectionNotice(null)} className="shrink-0 text-studio-500 hover:text-studio-100"><Icon name="close" size={14} /></button></div>}
      {selectedAgent && <div className="absolute bottom-16 right-3 max-w-xs border border-studio-800 bg-studio-900 px-3 py-2 text-xs text-studio-300"><span className="text-studio-500">Selected</span><span className="ml-2 font-semibold text-studio-100">{selectedAgent.name}</span></div>}
      {catalogModalOpen && <ToolCatalogModal onClose={() => setCatalogModalOpen(false)} />}
    </div>
  );
}
