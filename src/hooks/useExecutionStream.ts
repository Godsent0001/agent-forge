import { useEffect, useRef, useState } from "react";
import { api, getApiBase } from "../api/client";
import type { ExecutionEvent, ExecutionNode } from "../types";

/**
 * Reduces the flat event stream into a tree the UI can render live.
 * Mirrors the parent/child shape events already carry (depth +
 * Started/Completed pairs) rather than re-deriving structure elsewhere.
 */
function reduceEvents(events: ExecutionEvent[]): ExecutionNode[] {
  const roots: ExecutionNode[] = [];
  const stack: ExecutionNode[] = [];

  
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

    let activeWs: WebSocket | null = null;
    let cancelled = false;
    let pollInterval: any = null;

    const addEvents = (incoming: ExecutionEvent[]) => {
      setEvents((prev) => {
        const existingKeys = new Set(prev.map((e) => `${e.type}-${e.agent_name}-${e.tool_name}-${e.timestamp}`));
        const newEvents = incoming.filter((e) => !existingKeys.has(`${e.type}-${e.agent_name}-${e.tool_name}-${e.timestamp}`));
        if (newEvents.length === 0) return prev;
        return [...prev, ...newEvents];
      });
    };

    const fetchInitial = async () => {
      try {
        const initial = await api.executions.getEvents(executionId);
        if (!cancelled && initial.length > 0) {
          addEvents(initial);
        }
      } catch (err) {
        console.error("Error fetching execution events:", err);
      }
    };

    fetchInitial();

    getApiBase().then((apiBase) => {
      if (cancelled) return;
      const wsBase = apiBase.replace(/^http/, "ws");
      const ws = new WebSocket(`${wsBase}/executions/${executionId}/stream`);
      activeWs = ws;
      wsRef.current = ws;

      ws.onmessage = (msg) => {
        try {
          const event = JSON.parse(msg.data) as ExecutionEvent;
          addEvents([event]);
        } catch (err) {
          console.error("Error parsing execution websocket message:", err);
        }
      };
    });

    // Periodically reconcile until execution is finished
    pollInterval = setInterval(async () => {
      if (cancelled) return;
      try {
        const latest = await api.executions.getEvents(executionId);
        if (!cancelled && latest.length > 0) {
          addEvents(latest);
          if (latest.some((e) => e.type === "ExecutionCompleted")) {
            clearInterval(pollInterval);
          }
        }
      } catch {
        // ignore polling errors
      }
    }, 1000);

    return () => {
      cancelled = true;
      if (pollInterval) clearInterval(pollInterval);
      if (activeWs) {
        activeWs.close();
      }
    };
  }, [executionId]);

  return { events, tree: reduceEvents(events) };
}
