import { useState } from "react";
import { useExecutionStream } from "../hooks/useExecutionStream";
import type { ExecutionEvent, ExecutionStatus } from "../types";

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

  const renderNode = (node: any) => (
    <div key={node.id}>
      <button
        onClick={() => setSelectedLabel(node.label)}
        style={{ paddingLeft: `${12 + node.depth * 16}px` }}
        className={`w-full text-left py-1.5 pr-3 text-sm flex items-center gap-2 rounded-md transition-colors duration-150 my-0.5
          ${selectedLabel === node.label ? "bg-slate-200/80 font-medium text-slate-800" : "hover:bg-slate-100 text-slate-600"}`}
      >
        <span className={`w-2 h-2 rounded-full shrink-0 ${STATUS_DOT[node.status as ExecutionStatus]}`} />
        <span className="truncate">{node.label}</span>
      </button>
      {node.children.map(renderNode)}
    </div>
  );

  return (
    <div className="h-full flex flex-col border-l border-slate-200 bg-surface-900">
      <div className="px-4 py-3 border-b border-slate-200 bg-slate-50/50">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
          Execution Tree
        </h2>
      </div>

      <div className="flex-1 overflow-y-auto py-2 px-2">
        {!executionId && (
          <p className="px-3 py-6 text-xs text-slate-400 text-center">
            Run a task or send a message to inspect execution traces.
          </p>
        )}
        {tree.map(renderNode)}
      </div>

      {selectedLabel && (
        <div className="border-t border-slate-200 p-3 max-h-56 overflow-y-auto bg-slate-50">
          <p className="text-xs font-bold text-slate-700 mb-2">{selectedLabel}</p>
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
    <p className="text-xs text-slate-500 mb-1 truncate">
      <span className="font-medium text-slate-700">{event.type}</span>
      {note && <span> — {note}</span>}
    </p>
  );
}
