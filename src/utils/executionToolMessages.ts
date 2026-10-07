import type { ChatMessage, ExecutionEvent } from "../types";

function eventText(value: unknown): string {
  return typeof value === "string" ? value : value == null ? "" : JSON.stringify(value);
}

export function executionToolMessages(
  events: ExecutionEvent[],
  timestamp = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
): ChatMessage[] {
  const starts = new Map<string, ExecutionEvent>();

  for (const event of events) {
    if (event.type === "span_started" && event.span_id && event.kind === "tool_call") {
      starts.set(event.span_id, event);
    }
  }

  return events
    .filter(
      (event) =>
        event.type === "span_ended" &&
        event.span_id &&
        event.kind === "tool_call",
    )
    .sort((a, b) => a.seq - b.seq)
    .map((ended) => {
      const started = starts.get(ended.span_id!);
      const toolName =
        ended.name ??
        started?.name ??
        eventText(ended.data?.tool_name) ??
        "Tool";
      const input = eventText(started?.data?.args);
      const output =
        eventText(ended.data?.result_preview) ||
        eventText(ended.data?.output_preview) ||
        (ended.status === "cancelled" ? "Tool execution cancelled." : "Tool returned no preview.");

      return {
        id: `tool-${ended.span_id}`,
        sender: "tool",
        toolName,
        toolInput: input,
        toolOutput: output,
        toolStatus: ended.status ?? "error",
        text: output,
        timestamp,
      };
    });
}
