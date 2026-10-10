import { useState } from "react";
import { useExecutionStream } from "../hooks/useExecutionStream";
import { api } from "../api/client";
import { Button } from "./ui/Button";

interface ExecutionTreeProps {
  executionId: string | null;
  onSelectStep?: (spanId: string) => void;
}

export function ExecutionTree({ executionId }: ExecutionTreeProps) {
  const { events, tree } = useExecutionStream(executionId);
  const [selectedSeq, setSelectedSeq] = useState<number | null>(null);
  const [filterKind, setFilterKind] = useState<"all" | "agent" | "tool_call">("all");
  const [copied, setCopied] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);

  if (!executionId) {
    return (
      <div className="h-full flex flex-col items-center justify-center p-6 text-center text-xs select-none bg-studio-900">
        <div className="w-10 h-10 rounded-full bg-studio-800 border border-studio-700 flex items-center justify-center mb-2 text-studio-400">
          ⚡
        </div>
        <h3 className="font-semibold text-studio-200 mb-1">Execution Debugger</h3>
        <p className="text-studio-500 text-2xs leading-relaxed max-w-xs">
          Trigger an agent workflow or test execution to inspect runtime events, spans, and tool call traces.
        </p>
      </div>
    );
  }

  const isError = events.some((e) => e.status === "error");
  const isRunning = events.length > 0 && !events.some((e) => e.type === "execution_ended");

  const filteredEvents = events.filter((e) => {
    if (filterKind === "all") return true;
    return e.kind === filterKind;
  });

  const selectedEvent = events.find((e) => e.seq === selectedSeq) || events[events.length - 1];

  const handleCancelRun = async () => {
    if (!executionId || isCancelling) return;
    setIsCancelling(true);
    try {
      await api.executions.cancel(executionId);
    } catch (err) {
      console.error("Cancel failed:", err);
    } finally {
      setIsCancelling(false);
    }
  };

  const handleCopyPayload = () => {
    if (!selectedEvent) return;
    navigator.clipboard.writeText(JSON.stringify(selectedEvent, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="h-full flex flex-col text-xs select-none bg-studio-900 overflow-hidden min-w-0">
      {/* Inspector Header */}
      <div className="p-3 border-b border-studio-800 bg-studio-850 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-semibold text-studio-100 truncate">
            Run #{executionId.slice(0, 8)}
          </span>
          <span
            className={`text-2xs font-mono uppercase px-1.5 py-0.5 rounded border ${
              isRunning
                ? "bg-amber-950/60 text-amber-300 border-amber-800/80 animate-pulse"
                : isError
                ? "bg-red-950/60 text-red-300 border-red-800/80"
                : "bg-emerald-950/60 text-emerald-300 border-emerald-800/80"
            }`}
          >
            {isRunning ? "Running" : isError ? "Failed" : "Completed"}
          </span>
        </div>

        {isRunning && (
          <Button
            size="xs"
            variant="danger"
            onClick={handleCancelRun}
            disabled={isCancelling}
          >
            {isCancelling ? "Cancelling…" : "Cancel Run"}
          </Button>
        )}
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center gap-1 p-1.5 border-b border-studio-800 bg-studio-950/80 shrink-0">
        <button
          onClick={() => setFilterKind("all")}
          className={`px-2 py-0.5 text-2xs font-mono rounded transition-colors ${
            filterKind === "all"
              ? "bg-studio-800 text-white font-medium"
              : "text-studio-500 hover:text-studio-300"
          }`}
        >
          All ({events.length})
        </button>
        <button
          onClick={() => setFilterKind("agent")}
          className={`px-2 py-0.5 text-2xs font-mono rounded transition-colors ${
            filterKind === "agent"
              ? "bg-studio-800 text-blue-300 font-medium"
              : "text-studio-500 hover:text-studio-300"
          }`}
        >
          Agents
        </button>
        <button
          onClick={() => setFilterKind("tool_call")}
          className={`px-2 py-0.5 text-2xs font-mono rounded transition-colors ${
            filterKind === "tool_call"
              ? "bg-studio-800 text-emerald-300 font-medium"
              : "text-studio-500 hover:text-studio-300"
          }`}
        >
          Tools
        </button>
      </div>

      {/* Execution Event Stream List */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1 border-b border-studio-800 min-h-0">
        <span className="text-2xs font-mono uppercase text-studio-500 block px-1 mb-1">
          Execution Tree Nodes ({tree.length} roots · {filteredEvents.length} events)
        </span>

        {filteredEvents.map((evt) => {
          const isSelected = selectedEvent?.seq === evt.seq;
          const isErr = evt.status === "error";
          const isOk = evt.status === "ok";

          return (
            <div
              key={evt.seq}
              onClick={() => setSelectedSeq(evt.seq)}
              className={`p-2 rounded cursor-pointer border transition-colors ${
                isSelected
                  ? "bg-studio-800 border-accent-500 text-white font-medium"
                  : "bg-studio-950/60 border-studio-800/80 text-studio-300 hover:bg-studio-850"
              }`}
            >
              <div className="flex items-center justify-between mb-0.5">
                <div className="flex items-center gap-1.5 truncate">
                  <span
                    className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                      isErr
                        ? "bg-red-400"
                        : isOk
                        ? "bg-emerald-400"
                        : "bg-amber-400 animate-pulse"
                    }`}
                  />
                  <span className="text-2xs font-mono uppercase text-accent-400 truncate">
                    {evt.type}
                  </span>
                </div>
                <span className="text-2xs font-mono text-studio-500 tabular-nums">
                  {new Date(evt.ts).toLocaleTimeString([], { hour12: false })}
                </span>
              </div>

              <div className="text-2xs font-mono text-studio-300 flex items-center justify-between">
                <span className="truncate">
                  {evt.name || evt.kind || "step"}
                </span>
                <span className="text-studio-600 text-2xs">seq #{evt.seq}</span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Event Details Panel */}
      {selectedEvent && (
        <div className="h-56 p-3 bg-studio-950 overflow-y-auto border-t border-studio-800 flex flex-col shrink-0">
          <div className="flex items-center justify-between mb-1.5 shrink-0">
            <span className="text-2xs font-mono uppercase text-studio-400 font-semibold">
              Step #{selectedEvent.seq} Payload
            </span>
            <button
              onClick={handleCopyPayload}
              className="text-2xs font-mono text-studio-400 hover:text-white px-1.5 py-0.5 rounded hover:bg-studio-800 transition-colors"
            >
              {copied ? "Copied! ✓" : "Copy JSON"}
            </button>
          </div>
          <pre className="flex-1 overflow-auto text-2xs font-mono text-emerald-300/90 leading-relaxed bg-studio-900 p-2 rounded border border-studio-800 whitespace-pre-wrap break-all">
            {JSON.stringify(selectedEvent, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
