import { useEffect, useRef, useState } from "react";
import type { ExecutionEvent, ExecutionNode, ExecutionStatus } from "../types";

const WS_BASE = "ws://127.0.0.1:8756";

/**
 * Reduces the flat event stream into a tree the UI can render live.
 * Mirrors the parent/child shape events already carry (depth +
 * Started/Completed pairs) rather than re-deriving structure elsewhere.
 */
function reduceEvents(events: ExecutionEvent[]): ExecutionNode[] {
  const roots: ExecutionNode[] = [];
  const stack: ExecutionNode[] = [];

  const statusFor = (startType: string): ExecutionStatus =>
    startType.endsWith("Started") ? "running" : "completed";

  for (const event of events) {
    if (event.type.endsWith("Started") && (event.agent_name || event.tool_name)) {
      const node: ExecutionNode = {
        id: `${event.type}-${event.agent_name ?? event.tool_name}-${event.timestamp}`,
        label: event.agent_name ?? event.tool_name ?? "?",
        kind: event.agent_name ? "agent" : "tool",
        status: "running",
        depth: event.depth,
        children: [],
      };
      if (stack.length > 0 && stack[stack.length - 1].depth < event.depth) {
        stack[stack.length - 1].children.push(node);
      } else {
        // Pop back to the right depth before attaching
        while (stack.length > 0 && stack[stack.length - 1].depth >= event.depth) {
          stack.pop();
        }
        if (stack.length > 0) {
          stack[stack.length - 1].children.push(node);
        } else {
          roots.push(node);
        }
      }
      stack.push(node);
    } else if (event.type.endsWith("Completed")) {
      const match = [...stack].reverse().find(
        (n) => n.label === (event.agent_name ?? event.tool_name) && n.status === "running"
      );
      if (match) {
        match.status = event.data?.error ? "error" : "completed";
      }
    }
  }
  return roots;
}

export function useExecutionStream(executionId: string | null) {
  const [events, setEvents] = useState<ExecutionEvent[]>([]);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    setEvents([]);
    if (!executionId) return;

    const ws = new WebSocket(`${WS_BASE}/executions/${executionId}/stream`);
    wsRef.current = ws;

    ws.onmessage = (msg) => {
      const event = JSON.parse(msg.data) as ExecutionEvent;
      setEvents((prev) => [...prev, event]);
    };

    return () => ws.close();
  }, [executionId]);

  return { events, tree: reduceEvents(events) };
}
