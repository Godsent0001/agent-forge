import { useEffect, useRef, useState } from "react";
import { api, getApiBase } from "../api/client";
import type { ExecutionEvent, ExecutionNode, ExecutionStatus } from "../types";

function reduceEvents(events: ExecutionEvent[]): ExecutionNode[] {
  const nodes = new Map<string, ExecutionNode>();
  const roots: ExecutionNode[] = [];

  for (const event of events) {
    if (event.type === "span_started" && event.span_id && event.kind && event.name) {
      const node: ExecutionNode = {
        id: event.span_id,
        label: event.name,
        kind: event.kind,
        status: "running",
        depth: Number(event.data?.depth ?? 0),
        children: [],
      };
      nodes.set(event.span_id, node);
      if (event.parent_span_id && nodes.has(event.parent_span_id)) {
        nodes.get(event.parent_span_id)!.children.push(node);
      } else {
        roots.push(node);
      }
      continue;
    }

    if (event.type === "span_ended" && event.span_id) {
      const node = nodes.get(event.span_id);
      if (!node) continue;
      const status: ExecutionStatus =
        event.status === "ok"
          ? "completed"
          : event.status === "cancelled"
            ? "cancelled"
            : "error";
      node.status = status;
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

    let cancelled = false;
    let pollInterval: ReturnType<typeof setInterval> | null = null;

    const addEvents = (incoming: ExecutionEvent[]) => {
      setEvents((prev) => {
        const lastSeq = prev.length ? prev[prev.length - 1].seq : 0;
        const fresh = incoming.filter((event) => event.seq > lastSeq);
        return fresh.length ? [...prev, ...fresh] : prev;
      });
    };

    const startPolling = () => {
      if (pollInterval) return;
      pollInterval = setInterval(async () => {
        if (cancelled) return;
        try {
          const lastSeq = eventsRef.current.length ? eventsRef.current[eventsRef.current.length - 1].seq : 0;
          const latest = await api.executions.getEvents(executionId, lastSeq);
          if (!cancelled) addEvents(latest);
        } catch (err) {
          console.error("Error reconciling execution events:", err);
        }
      }, 1000);
    };

    const eventsRef = { current: [] as ExecutionEvent[] };
    const trackedAddEvents = (incoming: ExecutionEvent[]) => {
      addEvents(incoming);
      eventsRef.current = [...eventsRef.current, ...incoming].sort((a, b) => a.seq - b.seq);
    };

    getApiBase().then((apiBase) => {
      if (cancelled) return;
      const wsBase = apiBase.replace(/^http/, "ws");
      const ws = new WebSocket(
        `${wsBase}/v2/executions/${executionId}/stream?after_seq=0`,
      );
      wsRef.current = ws;

      ws.onmessage = (msg) => {
        try {
          trackedAddEvents([JSON.parse(msg.data) as ExecutionEvent]);
        } catch (err) {
          console.error("Error parsing execution websocket message:", err);
        }
      };

      ws.onerror = () => startPolling();
      ws.onclose = () => startPolling();
    });

    return () => {
      cancelled = true;
      if (pollInterval) clearInterval(pollInterval);
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [executionId]);

  return { events, tree: reduceEvents(events) };
}
