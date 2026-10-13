export interface Project {
  id: string;
  name: string;
  parallel_execution: boolean;
  settings?: Record<string, unknown>;
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

export interface ConversationSummary {
  id: string;
  project_id: string;
  agent_id: string;
  title: string;
  created_at: string;
}

export interface ConversationMessageRecord {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  execution_id: string | null;
  created_at: string;
  feedback_value: -1 | 1 | null;
  feedback_note: string | null;
}

export type ChatMessage =
  | {
      id: string;
      sender: "user";
      text: string;
      timestamp: string;
    }
  | {
      id: string;
      sender: "agent";
      agentName?: string;
      text: string;
      timestamp: string;
      /** The run that produced this reply, so its trace/log can be reopened later. */
      executionId?: string;
      /** Persisted conversation message id, used for feedback actions. */
      messageRecordId?: string;
      feedbackValue?: -1 | 1 | null;
      feedbackNote?: string | null;
      executionStatus?: "completed" | "error" | "cancelled" | "budget_exceeded" | "interrupted";
      usage?: {
        inputTokens: number;
        outputTokens: number;
        costUsd: number | null;
        durationSeconds: number | null;
      };
    }
  | {
      id: string;
      sender: "tool";
      toolName: string;
      toolInput: string;
      toolOutput: string;
      toolStatus: "ok" | "error" | "cancelled";
      text: string;
      timestamp: string;
      /** The run that produced this tool result, so artifacts resolve within that workspace. */
      executionId?: string;
    };

export type MemoryKind = "fact" | "preference" | "decision";
export type MemorySourceType = "user_stated" | "user_edited" | "inferred";
export type MemoryStatus = "active" | "superseded" | "archived";

export interface AgentMemory {
  id: string;
  agent_id: string;
  text: string;
  kind: MemoryKind;
  source_type: MemorySourceType;
  source_execution_id: string | null;
  created_at: string;
  last_used_at: string | null;
  use_count: number;
  pinned: boolean;
  status: MemoryStatus;
  expires_at: string | null;
}

export interface AgentLesson {
  id: string;
  agent_id: string;
  text: string;
  evidence_execution_id: string | null;
  status: "active" | "archived";
  score: number;
  created_at: string;
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
  lessons_enabled?: boolean;
  learned_experience?: string;
  created_at: string;
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
  pack?: string | null;
}

export interface CatalogShelf {
  shelf: string;
  label: string;
  tools: CatalogToolEntry[];
}
