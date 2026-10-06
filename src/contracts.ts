// Mirrors docs/CONTRACTS.md and python-runtime/app/contracts/*.py. Change them together (PR label `contract`).
// Dates are ISO-8601 UTC strings. API responses never include embedding vectors.

// ---- C-1 run -------------------------------------------------------------
export interface ChatMessage { role: "user" | "assistant"; content: string }
export interface AttachmentRef { path: string; mime?: string | null; name?: string | null }
export interface BudgetSpec {
  max_llm_calls: number; max_total_tokens: number; max_cost_usd: number | null; max_seconds: number;
}
export interface MemoryOptions {
  episodic: boolean; intents: boolean; embedding_model: string | null;
  recall_budget_tokens: number; max_items_per_agent: number;
}
export interface RunOptions {
  budget: BudgetSpec; parallel_tools: boolean; max_depth: number; max_iterations: number;
  scenario?: string | null; memory: MemoryOptions; timezone: string;
  llm_aliases: Record<string, string>;
}
/** Body of POST /v2/executions (the platform fills execution_id). */
export interface StartRunBody {
  project_id: string; root_agent_id: string; task: string;
  history?: ChatMessage[]; attachments?: AttachmentRef[]; options?: Partial<RunOptions>;
}
export interface Totals {
  llm_calls: number; tool_calls: number;
  input_tokens: number; output_tokens: number; cache_read_tokens: number;
  cost_usd: number | null;
}
export type RunStatus = "running" | "completed" | "error" | "cancelled"
  | "budget_exceeded" | "interrupted";

// ---- C-2 events ----------------------------------------------------------
export type EventType = "execution_started" | "span_started" | "span_ended"
  | "approval_requested" | "approval_resolved" | "execution_ended";
export type SpanKind = "agent" | "llm_call" | "tool_call";
export type SpanStatus = "ok" | "error" | "cancelled";

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

// ---- C-6 memory, intents, insights ----------------------------------------
export type MemoryKind = "fact" | "preference" | "decision";
export type MemorySource = "user_stated" | "user_edited" | "inferred";
export type MemoryStatus = "active" | "superseded" | "archived";
export interface MemoryItem {
  id: string; agent_id: string; text: string; kind: MemoryKind;
  source_type: MemorySource; source_execution_id: string | null; evidence: string;
  created_at: string; last_used_at: string | null; use_count: number;
  pinned: boolean; status: MemoryStatus; expires_at: string | null;
}
export type IntentTrigger = "next_run" | "at_time";
export type IntentMode = "remind" | "auto_run";
export type IntentStatus = "active" | "fired" | "cancelled" | "expired";
export interface Intent {
  id: string; agent_id: string; text: string; trigger: IntentTrigger;
  due_at: string | null; repeat: "none" | "daily" | "weekly"; mode: IntentMode;
  status: IntentStatus; evidence: string; source_execution_id: string | null;
  created_at: string; last_fired_at: string | null;
}
export type InsightStatus = "pending" | "accepted" | "dismissed";
export interface Insight {
  id: string; agent_id: string; text: string; kind: "pattern" | "suggestion";
  evidence_execution_ids: string[]; status: InsightStatus;
  maintenance_run_id: string | null; created_at: string;
}

// ---- C-8 platform-only shapes -------------------------------------------
export interface Notification {
  id: string; kind: "intent_due" | "insight_ready" | "maintenance_failed";
  title: string; body: string; ref_id: string | null; created_at: string; read_at: string | null;
}
export interface MaintenanceRun {
  id: string; kind: "dream" | "embed_backfill"; started_at: string; ended_at: string | null;
  status: "running" | "ok" | "error"; cost_usd: number | null; detail: Record<string, unknown>;
}
export interface ModelInfo {
  provider: string; model: string; tier: string; kind: "chat" | "embedding";
  context_window: number | null; supports_tools: boolean; supports_vision: boolean;
  price_in: number | null; price_out: number | null;
}
