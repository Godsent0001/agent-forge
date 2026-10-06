export type EventType =
  | "execution_started"
  | "span_started"
  | "span_ended"
  | "approval_requested"
  | "approval_resolved"
  | "execution_ended";

export type SpanKind = "agent" | "llm_call" | "tool_call";
export type SpanStatus = "ok" | "error" | "cancelled";
export type RunStatus =
  | "running"
  | "completed"
  | "error"
  | "cancelled"
  | "budget_exceeded"
  | "interrupted";

export interface RunEvent {
  execution_id: string;
  seq: number;
  ts: string;
  type: EventType;
  span_id?: string | null;
  parent_span_id?: string | null;
  kind?: SpanKind | null;
  name?: string | null;
  status?: SpanStatus | null;
  data: Record<string, unknown>;
}

export interface Totals {
  llm_calls: number;
  tool_calls: number;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cost_usd: number | null;
}
