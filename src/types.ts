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
  created_at: string;
  // Client-side only, populated from link endpoints — not sent to the API directly.
  tool_ids?: string[];
  child_agent_ids?: string[];
}

export type ExecutionStatus = "idle" | "running" | "completed" | "error";

export interface ExecutionEvent {
  type: string;
  agent_name: string | null;
  tool_name: string | null;
  depth: number;
  data: Record<string, unknown>;
  timestamp: string;
}

export interface ExecutionNode {
  id: string;
  label: string;
  kind: "agent" | "tool";
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
