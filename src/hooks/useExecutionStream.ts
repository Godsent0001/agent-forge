import { useEffect, useRef, useState } from "react";
import { api, getApiBase, getApiToken } from "../api/client";
import type { ExecutionEvent, ExecutionNode, ExecutionStatus } from "../types";

export function reduceEvents(events: ExecutionEvent[]): ExecutionNode[] {
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
  const eventsRef = useRef<ExecutionEvent[]>([]);

  useEffect(() => {
    setEvents([]);
    eventsRef.current = [];
    if (!executionId) return;

    let cancelled = false;
    let runEnded = false;
    let pollInterval: ReturnType<typeof setInterval> | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let reconnectDelay = 500;

    const lastSeq = () => {
      const current = eventsRef.current;
      return current.length ? current[current.length - 1].seq : 0;
    };
    const addEvents = (incoming: ExecutionEvent[]) => {
      if (!incoming.length || runEnded) return;
      const unique = new Map<number, ExecutionEvent>();
      for (const event of [...eventsRef.current, ...incoming]) unique.set(event.seq, event);
      const ordered = [...unique.values()].sort((a, b) => a.seq - b.seq);
      eventsRef.current = ordered;
      setEvents(ordered);

      if (ordered.some((event) => event.type === "execution_ended")) {
        runEnded = true;
        stopPolling();
        if (reconnectTimer) clearTimeout(reconnectTimer);
        reconnectTimer = null;
        const socket = wsRef.current;
        if (socket && socket.readyState < WebSocket.CLOSING) socket.close();
      }
    };
    const pollOnce = async () => {
      if (cancelled) return;
      try {
        const latest = await api.executions.getEvents(executionId, lastSeq());
        if (!cancelled) addEvents(latest);
      } catch (err) {
        console.error("Error reconciling execution events:", err);
      }
    };
    const startPolling = () => {
      if (pollInterval || cancelled || runEnded) return;
      void pollOnce();
      pollInterval = setInterval(() => void pollOnce(), 1000);
    };
    const stopPolling = () => {
      if (!pollInterval) return;
      clearInterval(pollInterval);
      pollInterval = null;
    };
    const scheduleReconnect = () => {
      if (cancelled || runEnded) return;
      startPolling();
      if (reconnectTimer) return;
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        void connect();
      }, reconnectDelay);
      reconnectDelay = Math.min(reconnectDelay * 2, 10000);
    };
    const connect = async () => {
      try {
        const apiBase = await getApiBase();
        const token = await getApiToken();
        if (cancelled) return;
        const wsBase = apiBase.replace(/^http/, "ws");
        const params = new URLSearchParams({ after_seq: String(lastSeq()) });
        if (token) params.set("token", token);
        const ws = new WebSocket(
          wsBase + "/v2/executions/" + encodeURIComponent(executionId) +
          "/stream?" + params.toString(),
        );
        wsRef.current = ws;
        ws.onopen = () => {
          reconnectDelay = 500;
          stopPolling();
        };
        ws.onmessage = (msg) => {
          try {
            addEvents([JSON.parse(msg.data) as ExecutionEvent]);
          } catch (err) {
            console.error("Error parsing execution websocket message:", err);
          }
        };
        ws.onerror = () => ws.close();
        ws.onclose = () => {
          if (wsRef.current === ws) wsRef.current = null;
          scheduleReconnect();
        };
      } catch (err) {
        console.error("Unable to connect to execution stream:", err);
        scheduleReconnect();
      }
    };

    void connect();
    return () => {
      cancelled = true;
      stopPolling();
      if (reconnectTimer) clearTimeout(reconnectTimer);
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [executionId]);
  return { events, tree: reduceEvents(events) };
}
