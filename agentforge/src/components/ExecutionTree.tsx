import { useState } from "react";
import { useExecutionStream } from "../hooks/useExecutionStream";
import type { ExecutionEvent, ExecutionNode, ExecutionStatus } from "../types";

const STATUS_DOT: Record<ExecutionStatus, string> = {
  idle: "bg-status-idle",
  running: "bg-status-running animate-pulse",
  completed: "bg-status-success",
  error: "bg-status-error",
};

export function ExecutionTree({ executionId }: { executionId: string | null }) {
  const { events, tree } = useExecutionStream(executionId);
  const [selectedLabel, setSelectedLabel] = useState<string | null>(null);

  const selectedEvents = selectedLabel
    ? events.filter((e) => (e.agent_name ?? e.tool_name) === selectedLabel)
    : [];

  const renderNode = (node: ExecutionNode) => (
    <div key={node.id}>
      <button
        onClick={() => setSelectedLabel(node.label)}
        style={{ paddingLeft: `${12 + node.depth * 16}px` }}
        className={`w-full text-left py-1 pr-3 text-sm flex items-center gap-2 rounded-md
          transition-colors duration-150
          ${selectedLabel === node.label ? "bg-white/5" : "hover:bg-white/5"}`}
      >
        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${STATUS_DOT[node.status]}`} />
        <span className="truncate text-neutral-300">{node.label}</span>
      </button>
      {node.children.map(renderNode)}
    </div>
  );

  return (
    <div className="h-full flex flex-col border-l border-white/5 bg-surface-900">
      <div className="px-4 py-3 border-b border-white/5">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-neutral-500">
          Execution
        </h2>
      </div>

      <div className="flex-1 overflow-y-auto py-2">
        {!executionId && (
          <p className="px-4 py-6 text-sm text-neutral-600">
            Run an agent to see live execution here.
          </p>
        )}
        {tree.map(renderNode)}
      </div>

      {selectedLabel && (
        <div className="border-t border-white/5 p-3 max-h-56 overflow-y-auto">
          <p className="text-xs font-semibold text-neutral-400 mb-2">{selectedLabel}</p>
          {selectedEvents.map((e, i) => (
            <EventLine key={i} event={e} />
          ))}
        </div>
      )}
    </div>
  );
}

function EventLine({ event }: { event: ExecutionEvent }) {
  const note =
    (event.data?.task as string | undefined) ??
    (event.data?.result as string | undefined) ??
    (event.data?.note as string | undefined) ??
    "";
  return (
    <p className="text-xs text-neutral-500 mb-1 truncate">
      <span className="text-neutral-400">{event.type}</span>
      {note && <span> — {note}</span>}
    </p>
  );
}
