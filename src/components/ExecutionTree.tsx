import { useState } from "react";
import { useExecutionStream } from "../hooks/useExecutionStream";

interface ExecutionTreeProps {
  executionId: string | null;
}

export function ExecutionTree({ executionId }: ExecutionTreeProps) {
  const { events, tree } = useExecutionStream(executionId);
  const [selectedSeq, setSelectedSeq] = useState<number | null>(null);

  if (!executionId) {
    return (
      <div className="h-full flex flex-col items-center justify-center p-6 text-center text-xs select-none">
        <div className="w-10 h-10 rounded-full bg-studio-800 border border-studio-700 flex items-center justify-center mb-2 text-studio-400">
          ⚡
        </div>
        <h3 className="font-semibold text-studio-200 mb-1">Execution Inspector</h3>
        <p className="text-studio-500 text-2xs leading-relaxed max-w-xs">
          Run an agent test or execution to stream real-time events, tool calls, and debug traces.
        </p>
      </div>
    );
  }

  const selectedEvent = events.find((e) => e.seq === selectedSeq) || events[events.length - 1];

  return (
    <div className="h-full flex flex-col text-xs select-none bg-studio-900">
      {/* Inspector Header */}
      <div className="p-3 border-b border-studio-800 bg-studio-850 flex items-center justify-between">
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-semibold text-studio-100 truncate">Run #{executionId.slice(0, 8)}</span>
          <span className="text-2xs font-mono uppercase px-1.5 py-0.5 rounded border bg-emerald-950/60 text-emerald-400 border-emerald-800/80">
            Active Stream
          </span>
        </div>
      </div>

      {/* Execution Event Stream Tree */}
      <div className="flex-1 overflow-auto p-2 space-y-1 border-b border-studio-800 min-h-0">
        <span className="text-2xs font-mono uppercase text-studio-500 block px-1 mb-1">
          Execution Tree Nodes ({tree.length})
        </span>

        {events.map((evt) => {
          const isSelected = selectedEvent?.seq === evt.seq;
          return (
            <div
              key={evt.seq}
              onClick={() => setSelectedSeq(evt.seq)}
              className={`p-2 rounded cursor-pointer border transition-colors ${
                isSelected
                  ? "bg-studio-800 border-studio-600 text-white font-medium"
                  : "bg-studio-950/60 border-studio-800/80 text-studio-300 hover:bg-studio-850"
              }`}
            >
              <div className="flex items-center justify-between mb-0.5">
                <span className="text-2xs font-mono uppercase text-accent-400">{evt.type}</span>
                <span className="text-2xs font-mono text-studio-500">
                  {new Date(evt.ts).toLocaleTimeString()}
                </span>
              </div>
              <div className="text-2xs font-mono text-studio-400 truncate">
                {JSON.stringify(evt.data)}
              </div>
            </div>
          );
        })}
      </div>

      {/* Event Details Panel */}
      {selectedEvent && (
        <div className="h-48 p-3 bg-studio-950 overflow-auto border-t border-studio-800">
          <span className="text-2xs font-mono uppercase text-studio-500 block mb-1">Step Payload Data</span>
          <pre className="text-2xs font-mono text-studio-300 whitespace-pre-wrap break-all leading-relaxed bg-studio-900 p-2 rounded border border-studio-800">
            {JSON.stringify(selectedEvent, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
