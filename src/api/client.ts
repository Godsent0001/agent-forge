import { keychain } from "./keychain";
import { providersNeedingKeys } from "../config/providers";
import type { ChatMessage as RunChatMessage } from "../contracts";
import type {
  Agent,
  AgentLesson,
  AgentMemory,
  CatalogShelf,
  CatalogToolEntry,
  ConversationMessageRecord,
  ConversationSummary,
  Project,
  Tool,
} from "../types";

let currentApiBase = "";
let portInitPromise: Promise<void> | null = null;
let apiTokenPromise: Promise<string> | null = null;

export function getApiToken(): Promise<string> {
  if (!apiTokenPromise) {
    apiTokenPromise = (async () => {
      if (typeof window !== "undefined" && window.electronAPI) {
        return window.electronAPI.getApiToken();
      }
      return import.meta.env.VITE_DEV_TOKEN || "";
    })();
  }
  return apiTokenPromise;
}

function ensurePortInitialized(): Promise<void> {
  if (!portInitPromise) {
    portInitPromise = (async () => {
      try {
        if (typeof window !== "undefined" && window.electronAPI) {
          const port = await window.electronAPI.getBackendPort();
          if (!port) throw new Error("The local runtime did not provide a listening port");
          currentApiBase = `http://127.0.0.1:${port}`;
          return;
        }

        // Browser-only development must name its runtime explicitly rather than
        // silently assuming a fixed port. Electron always supplies a dynamic port.
        const origin = typeof window !== "undefined" ? window.location.origin : "";
        const configuredBase = import.meta.env.VITE_API_BASE?.trim();
        const isViteDevOrigin = origin === "http://localhost:5173" || origin === "http://127.0.0.1:5173";
        if (configuredBase) {
          currentApiBase = configuredBase.replace(/\/+$/, "");
        } else if (isViteDevOrigin) {
          throw new Error("Set VITE_API_BASE in .env.local for browser-only development (for example, http://127.0.0.1:8000).");
        } else if (origin) {
          currentApiBase = origin;
        } else {
          throw new Error("The AgentForge API base URL is not configured.");
        }
      } catch (error) {
        portInitPromise = null;
        throw error;
      }
    })();
  }
  return portInitPromise;
}
// The runtime listens on a new port after an automatic restart; follow it.
if (typeof window !== "undefined") {
  window.electronAPI?.onBackendRestarted?.((port) => {
    currentApiBase = `http://127.0.0.1:${port}`;
  });
}

export function setApiBase(base: string) {
  currentApiBase = base;
}

export async function getApiBase(): Promise<string> {
  await ensurePortInitialized();
  return currentApiBase;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  await ensurePortInitialized();
  const token = await getApiToken();
  const headers = new Headers(options?.headers);
  if (!headers.has("Content-Type") && options?.body) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", "Bearer " + token);
  const res = await fetch(`${currentApiBase}${path}`, {
    ...options,
    headers,
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    try {
      const parsed = JSON.parse(body) as { detail?: unknown };
      if (typeof parsed.detail === "string") throw new Error(parsed.detail);
    } catch (error) {
      if (error instanceof Error && error.message !== body) throw error;
    }
    throw new Error(`${options?.method ?? "GET"} ${path} failed: ${res.status} ${body}`);
  }
  return res.json();
}

async function requestAttachmentBlob(path: string): Promise<Blob> {
  await ensurePortInitialized();
  const token = await getApiToken();
  const headers = new Headers();
  if (token) headers.set("Authorization", "Bearer " + token);
  const response = await fetch(`${currentApiBase}${path}`, { headers });
  if (!response.ok) {
    const body = await response.text().catch(() => "");
    try {
      const parsed = JSON.parse(body) as { detail?: unknown };
      if (typeof parsed.detail === "string") throw new Error(parsed.detail);
    } catch (error) {
      if (error instanceof Error && error.message !== body) throw error;
    }
    throw new Error(`GET ${path} failed: ${response.status} ${body}`);
  }
  return response.blob();
}

export interface ExecutionArtifact {
  artifact_id: string;
  project_id: string;
  artifact_type: string;
  name: string;
  media_type: string;
  version: number;
  sha256: string;
  size_bytes: number;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ExecutionResult {
  id: string;
  project_id?: string;
  root_agent_id?: string | null;
  input_task?: string;
  final_output: string;
  status: string;
  totals?: Record<string, unknown>;
  error?: string | null;
  started_at: string;
  ended_at: string | null;
  completed_at?: string | null;
}

export interface ExecutionSummary {
  id: string;
  task_preview: string;
  status: string;
  started_at: string;
  ended_at: string | null;
  totals: Record<string, unknown>;
}

export interface SystemCheck {
  name: string;
  ok: boolean;
  detail: string;
  fix: string | null;
}

export interface UsageTotals {
  runs: number;
  completed_runs: number;
  failed_runs: number;
  llm_calls: number;
  tool_calls: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number | null;
}

export interface UsageBucket {
  date?: string | null;
  agent_id?: string | null;
  agent_name?: string | null;
  model?: string | null;
  runs: number;
  llm_calls: number;
  tool_calls: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number | null;
}

export interface UsageReport {
  project_id: string;
  days: number;
  totals: UsageTotals;
  by_day: UsageBucket[];
  by_agent: UsageBucket[];
  by_model: UsageBucket[];
}

export const api = {
  projects: {
    list: () => request<Project[]>("/projects"),
    create: (name: string, parallel_execution = false) =>
      request<Project>("/projects", { method: "POST", body: JSON.stringify({ name, parallel_execution }) }),
    update: (id: string, patch: { name?: string; parallel_execution?: boolean; settings?: Record<string, unknown> }) =>
      request<Project>(`/projects/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
    workspace: (id: string) => request<{
      project_id: string; workspace_path: string; file_count: number; total_bytes: number;
      files: { path: string; size_bytes: number }[];
    }>(`/projects/${encodeURIComponent(id)}/workspace`),
    readWorkspaceFile: (id: string, path: string) =>
      requestAttachmentBlob(`/projects/${encodeURIComponent(id)}/workspace/file?path=${encodeURIComponent(path)}`),
    openWorkspace: (id: string) =>
      request<{ opened: boolean; workspace_path: string }>(`/projects/${encodeURIComponent(id)}/workspace/open`, { method: "POST" }),
    downloadWorkspace: (id: string) =>
      requestAttachmentBlob(`/projects/${encodeURIComponent(id)}/workspace.zip`),
  },
  attachments: {
    list: (projectId: string, limit = 100) =>
      request<{ items: import("../types").ProjectAttachment[]; next_cursor: string | null }>(
        `/v2/projects/${encodeURIComponent(projectId)}/attachments?limit=${limit}`,
      ),
    upload: async (projectId: string, file: File) => {
      await ensurePortInitialized();
      const token = await getApiToken();
      const form = new FormData();
      form.append("file", file, file.name);
      const headers = new Headers();
      if (token) headers.set("Authorization", "Bearer " + token);
      const response = await fetch(
        `${currentApiBase}/v2/projects/${encodeURIComponent(projectId)}/attachments`,
        { method: "POST", headers, body: form },
      );
      if (!response.ok) {
        const body = await response.text().catch(() => "");
        try {
          const parsed = JSON.parse(body) as { detail?: unknown };
          if (typeof parsed.detail === "string") throw new Error(parsed.detail);
        } catch (error) {
          if (error instanceof Error && error.message !== body) throw error;
        }
        throw new Error(`Upload failed: ${response.status} ${body}`);
      }
      return response.json() as Promise<import("../types").ProjectAttachment>;
    },
    scan: (projectId: string, attachmentId: string) =>
      request<import("../types").ProjectAttachment & { scan_result: string }>(
        `/v2/projects/${encodeURIComponent(projectId)}/attachments/${encodeURIComponent(attachmentId)}/scan`,
        { method: "POST" },
      ),
    remove: (projectId: string, attachmentId: string) =>
      request<{ deleted: boolean }>(
        `/v2/projects/${encodeURIComponent(projectId)}/attachments/${encodeURIComponent(attachmentId)}`,
        { method: "DELETE" },
      ),
    download: (projectId: string, attachmentId: string) =>
      requestAttachmentBlob(
        `/v2/projects/${encodeURIComponent(projectId)}/attachments/${encodeURIComponent(attachmentId)}/content`,
      ),
  },
  agents: {
    list: (project_id: string) => request<Agent[]>(`/agents?project_id=${project_id}`),
    create: (payload: Partial<Agent> & { project_id: string; name: string }) =>
      request<Agent>("/agents", { method: "POST", body: JSON.stringify(payload) }),
    update: (id: string, payload: Partial<Agent>) =>
      request<Agent>(`/agents/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
    remove: (id: string) => request<{ deleted: string }>(`/agents/${id}`, { method: "DELETE" }),
    attachTool: (agent_id: string, tool_id: string) =>
      request("/agents/attach-tool", { method: "POST", body: JSON.stringify({ agent_id, tool_id }) }),
    detachTool: (agent_id: string, tool_id: string) =>
      request("/agents/detach-tool", { method: "POST", body: JSON.stringify({ agent_id, tool_id }) }),
    attachChildAgent: (parent_agent_id: string, child_agent_id: string, description = "") =>
      request("/agents/attach-child-agent", {
        method: "POST",
        body: JSON.stringify({ parent_agent_id, child_agent_id, description }),
      }),
    detachChildAgent: (parent_agent_id: string, child_agent_id: string) =>
      request("/agents/detach-child-agent", {
        method: "POST",
        body: JSON.stringify({ parent_agent_id, child_agent_id }),
      }),
  },
  tools: {
    list: (project_id: string) => request<Tool[]>(`/tools?project_id=${project_id}`),
    create: (payload: Partial<Tool> & { project_id: string; name: string; kind: string }) =>
      request<Tool>("/tools", { method: "POST", body: JSON.stringify(payload) }),
    remove: (id: string) => request<{ deleted: string }>(`/tools/${id}`, { method: "DELETE" }),
  },

  memory: {
    list: (agentId: string, status?: "active" | "superseded" | "archived") =>
      request<AgentMemory[]>(`/v2/agents/${encodeURIComponent(agentId)}/memory${status ? `?status=${status}` : ""}`),
    create: (agentId: string, payload: { text: string; kind: AgentMemory["kind"]; pinned?: boolean }) =>
      request<AgentMemory>(`/v2/agents/${encodeURIComponent(agentId)}/memory`, {
        method: "POST", body: JSON.stringify(payload),
      }),
    update: (agentId: string, memoryId: string, payload: { text?: string; kind?: AgentMemory["kind"]; pinned?: boolean; status?: AgentMemory["status"] }) =>
      request<AgentMemory>(`/v2/agents/${encodeURIComponent(agentId)}/memory/${encodeURIComponent(memoryId)}`, {
        method: "PATCH", body: JSON.stringify(payload),
      }),
    remove: (agentId: string, memoryId: string) =>
      request<{ deleted: boolean }>(`/v2/agents/${encodeURIComponent(agentId)}/memory/${encodeURIComponent(memoryId)}`, { method: "DELETE" }),
    clear: (agentId: string) =>
      request<{ deleted: number }>(`/v2/agents/${encodeURIComponent(agentId)}/memory`, { method: "DELETE" }),
  },
  lessons: {
    list: (agentId: string, status?: "active" | "archived") =>
      request<AgentLesson[]>(`/v2/agents/${encodeURIComponent(agentId)}/lessons${status ? `?status=${status}` : ""}`),
    create: (agentId: string, payload: { text: string; evidence_execution_id?: string; score?: number }) =>
      request<AgentLesson>(`/v2/agents/${encodeURIComponent(agentId)}/lessons`, {
        method: "POST", body: JSON.stringify(payload),
      }),
    update: (agentId: string, lessonId: string, payload: { text?: string; status?: AgentLesson["status"]; score?: number }) =>
      request<AgentLesson>(`/v2/agents/${encodeURIComponent(agentId)}/lessons/${encodeURIComponent(lessonId)}`, {
        method: "PATCH", body: JSON.stringify(payload),
      }),
    remove: (agentId: string, lessonId: string) =>
      request<{ deleted: boolean }>(`/v2/agents/${encodeURIComponent(agentId)}/lessons/${encodeURIComponent(lessonId)}`, { method: "DELETE" }),
  },
  conversations: {
    list: (projectId: string, agentId?: string, limit = 50) => {
      const params = new URLSearchParams({ project_id: projectId, limit: String(limit) });
      if (agentId) params.set("agent_id", agentId);
      return request<ConversationSummary[]>(`/v2/conversations?${params.toString()}`);
    },
    create: (projectId: string, agentId: string, title = "New conversation") =>
      request<ConversationSummary>("/v2/conversations", {
        method: "POST",
        body: JSON.stringify({ project_id: projectId, agent_id: agentId, title }),
      }),
    remove: (conversationId: string) =>
      request<{ deleted: boolean }>(`/v2/conversations/${encodeURIComponent(conversationId)}`, { method: "DELETE" }),
    messages: (conversationId: string) =>
      request<ConversationMessageRecord[]>(
        `/v2/conversations/${encodeURIComponent(conversationId)}/messages`,
      ),
    appendMessage: (
      conversationId: string,
      payload: { role: "user" | "assistant"; content: string; execution_id?: string },
    ) =>
      request<ConversationMessageRecord>(
        `/v2/conversations/${encodeURIComponent(conversationId)}/messages`,
        { method: "POST", body: JSON.stringify(payload) },
      ),
    editUserMessage: (messageId: string, content: string) =>
      request<ConversationMessageRecord>(
        `/v2/messages/${encodeURIComponent(messageId)}`,
        { method: "PATCH", body: JSON.stringify({ content }) },
      ),
    feedback: (messageId: string, value: -1 | 1, note?: string) =>
      request<{ ok: boolean; value: -1 | 1 }>(
        `/v2/messages/${encodeURIComponent(messageId)}/feedback`,
        { method: "PUT", body: JSON.stringify({ value, note }) },
      ),
  },
  artifacts: {
    list: (executionId: string) =>
      request<ExecutionArtifact[]>(
        `/v2/executions/${encodeURIComponent(executionId)}/artifacts`,
      ),
    download: (executionId: string, artifactId: string, version?: number) =>
      requestAttachmentBlob(
        `/v2/executions/${encodeURIComponent(executionId)}/artifacts/${encodeURIComponent(artifactId)}${version ? `?version=${version}` : ""}`,
      ),
  },
  executions: {
    run: (
      project_id: string,
      root_agent_id: string,
      task: string,
      history: RunChatMessage[] = [],
      attachment_ids: string[] = [],
    ) =>
      request<{ id: string; status: "running" }>("/v2/executions", {
        method: "POST",
        body: JSON.stringify({ project_id, root_agent_id, task, history, attachment_ids }),
      }),
    get: (id: string) => request<ExecutionResult>(`/v2/executions/${id}`),
    getEvents: (id: string, after_seq = 0) =>
      request<import("../types").ExecutionEvent[]>(
        `/v2/executions/${id}/events?after_seq=${after_seq}`,
      ),
    list: (project_id: string, limit = 10) =>
      request<ExecutionSummary[]>(
        `/v2/executions?project_id=${encodeURIComponent(project_id)}&limit=${limit}`,
      ),
    cancel: (id: string) =>
      request<{ status: string }>(`/v2/executions/${id}/cancel`, {
        method: "POST",
      }),
    resolveApproval: (executionId: string, approvalId: string, decision: "allow_once" | "allow_run" | "deny") =>
      request<{ status: string; decision: string }>(
        `/v2/executions/${encodeURIComponent(executionId)}/approvals/${encodeURIComponent(approvalId)}`,
        { method: "POST", body: JSON.stringify({ decision }) },
      ),
  },
  catalog: {
    list: () => request<CatalogToolEntry[]>("/catalog"),
    shelves: (pack?: "video" | "none") => request<CatalogShelf[]>(`/catalog/shelves${pack ? `?pack=${pack}` : ""}`),
  },
  settings: {
    /**
     * Which providers have a stored key. Only a masked hint (last 4 characters) is returned,
     * so the full key never has to live in React state.
     */
    /** Status only. The renderer never reads decrypted provider key material. */
    getKeyStatus: async (): Promise<Record<string, { saved: boolean; hint: string }>> => {
      const status: Record<string, { saved: boolean; hint: string }> = {};
      if (typeof window !== "undefined" && window.electronAPI) {
        for (const provider of providersNeedingKeys()) status[provider.keyId] = await keychain.status(provider.keyId);
        return status;
      }
      let runtime: Record<string, boolean> = {};
      try { runtime = await api.settings.runtimeKeyStatus(); } catch { /* runtime may not be running */ }
      for (const provider of providersNeedingKeys()) {
        const hint = await keychain.status(provider.keyId);
        status[provider.keyId] = { saved: runtime[provider.keyId] === true || hint.saved, hint: hint.hint };
      }
      return status;
    },
    /** Electron persists keys in main and sends them to the sidecar from main—not from React. */
    setKeys: async (keys: Record<string, string | undefined>) => {
      if (typeof window !== "undefined" && window.electronAPI) {
        for (const [slot, value] of Object.entries(keys)) {
          if (!value) continue;
          const result = await keychain.save(slot, value.trim());
          if (!result.ok && result.reason === "encryption-unavailable") throw new Error("ENCRYPTION_UNAVAILABLE");
          if (!result.ok) throw new Error("KEY_STORAGE_FAILED");
          if (result.applied === false) throw new Error("KEY_SAVED_NOT_APPLIED");
        }
        return;
      }
      const values = Object.fromEntries(Object.entries(keys).filter(([, value]) => Boolean(value)).map(([slot, value]) => [slot, value!.trim()]));
      if (Object.keys(values).length === 0) return;
      await request("/settings/keys", { method: "POST", body: JSON.stringify(values) });
      for (const [slot, value] of Object.entries(values)) keychain.rememberDevKey(slot, value);
    },
    removeKey: async (slot: string) => {
      const result = await keychain.remove(slot);
      if (!result.ok) throw new Error("KEY_STORAGE_FAILED");
      if (typeof window !== "undefined" && window.electronAPI) {
        if (result.applied === false) throw new Error("KEY_REMOVED_NOT_APPLIED");
      } else {
        await request("/settings/keys", { method: "POST", body: JSON.stringify({ [slot]: "" }) });
        keychain.rememberDevKey(slot, "");
      }
    },
    /** Only the Electron main process can read saved keys when restoring runtime state. */
    syncKeysToBackend: () => keychain.syncToRuntime(),
    /** Which key slots the runtime reports as active (a slot it doesn't know about is simply absent). */
    runtimeKeyStatus: () => request<Record<string, boolean>>("/settings/keys"),
    getEmbeddingModel: () => request<{ model: string }>("/settings/embedding-model"),
    setEmbeddingModel: (model: string) =>
      request<{ status: string; model: string }>("/settings/embedding-model", {
        method: "POST",
        body: JSON.stringify({ model }),
      }),
  },
  system: {
    check: () => request<SystemCheck[]>("/v2/system/check"),
  },
  usage: {
    get: (projectId: string, days = 7) =>
      request<UsageReport>(`/v2/usage?project_id=${encodeURIComponent(projectId)}&days=${days}`),
  },
};
