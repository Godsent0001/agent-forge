export interface Project {
  id: string;
  name: string;
  parallel_execution: boolean;
  created_at: string;
}

export interface Tool {
  id: string;
  project_id: string;
  name: string;
  description: string;
  kind: string;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  config: Record<string, unknown>;
}

export interface ChatMessage {
  id: string;
  sender: "user" | "agent";
  agentName?: string;
  text: string;
  timestamp: string;
}

export interface Agent {
  id: string;
  project_id: string;
  name: string;
  description: string;
  provider: string;
  model: string;
  system_prompt: string;
  tool_use_schema: string;
  memory_enabled: boolean;
  learned_experience?: string;
  created_at: string;
  // Client-side only, populated from link endpoints — not sent to the API directly.
  tool_ids?: string[];
  child_agent_ids?: string[];
}

export type ExecutionStatus =
  | "idle"
  | "running"
  | "completed"
  | "error"
  | "cancelled"
  | "budget_exceeded"
  | "interrupted";

export interface ExecutionEvent {
  execution_id: string;
  seq: number;
  ts: string;
  type: string;
  span_id?: string | null;
  parent_span_id?: string | null;
  kind?: "agent" | "llm_call" | "tool_call" | null;
  name?: string | null;
  status?: "ok" | "error" | "cancelled" | null;
  data: Record<string, unknown>;
}

export interface ExecutionNode {
  id: string;
  label: string;
  kind: "agent" | "llm_call" | "tool_call";
  status: ExecutionStatus;
  depth: number;
  children: ExecutionNode[];
}

export type CatalogStatus = "real" | "stub";

export interface CatalogToolEntry {
  kind: string;
  name: string;
  description: string;
  status: CatalogStatus;
  shelf?: string;
}

export interface CatalogShelf {
  shelf: string;
  label: string;
  tools: CatalogToolEntry[];
}
