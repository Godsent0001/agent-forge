import { keychain } from "./keychain";
import { providersNeedingKeys } from "../config/providers";
import type { ChatMessage as RunChatMessage } from "../contracts";
import type { Agent, CatalogShelf, CatalogToolEntry, Project, Tool } from "../types";

let currentApiBase = "http://127.0.0.1:8000";
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
      if (window.electronAPI) {
        try {
          const port = await window.electronAPI.getBackendPort();
          if (port) {
            currentApiBase = `http://127.0.0.1:${port}`;
          }
        } catch (err) {
          console.error("Failed to acquire Python backend port from Electron:", err);
          portInitPromise = null;
          throw new Error("Could not connect to Python backend: " + (err as Error).message);
        }
      } else {
        // Standalone browser development / AI Studio web environment
        currentApiBase = typeof window !== "undefined" && window.location.origin ? window.location.origin : "http://127.0.0.1:3000";
      }
    })();
  }
  return portInitPromise;
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

export const api = {
  projects: {
    list: () => request<Project[]>("/projects"),
    create: (name: string, parallel_execution = false) =>
      request<Project>("/projects", { method: "POST", body: JSON.stringify({ name, parallel_execution }) }),
    update: (id: string, patch: { name?: string; parallel_execution?: boolean; settings?: Record<string, unknown> }) =>
      request<Project>(`/projects/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
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
  executions: {
    run: (project_id: string, root_agent_id: string, task: string, history: RunChatMessage[] = []) =>
      request<{ id: string; status: "running" }>("/v2/executions", {
        method: "POST",
        body: JSON.stringify({ project_id, root_agent_id, task, history }),
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
    getKeyStatus: async (): Promise<Record<string, { saved: boolean; hint: string }>> => {
      const status: Record<string, { saved: boolean; hint: string }> = {};
      for (const provider of providersNeedingKeys()) {
        const value = await keychain.get(provider.keyId);
        status[provider.keyId] = { saved: !!value, hint: value ? `••••${value.slice(-4)}` : "" };
      }
      return status;
    },
    /** Saves the given keys (by key slot) to the keychain, then pushes all stored keys to the runtime. */
    setKeys: async (keys: Record<string, string | undefined>) => {
      for (const [slot, value] of Object.entries(keys)) {
        if (value) await keychain.save(slot, value);
      }
      await api.settings.syncKeysToBackend();
    },
    removeKey: async (slot: string) => {
      await keychain.remove(slot);
      // An explicit empty string clears the variable in the runtime process.
      await request("/settings/keys", { method: "POST", body: JSON.stringify({ [slot]: "" }) });
    },
    /** Pushes every stored key to the runtime (called at startup, since the runtime keeps keys in memory only). */
    syncKeysToBackend: async () => {
      const stored: Record<string, string> = {};
      for (const provider of providersNeedingKeys()) {
        const value = await keychain.get(provider.keyId);
        if (value) stored[provider.keyId] = value;
      }
      if (Object.keys(stored).length === 0) return { status: "ok" };
      return request("/settings/keys", { method: "POST", body: JSON.stringify(stored) });
    },
    /** Which key slots the runtime reports as active (a slot it doesn't know about is simply absent). */
    runtimeKeyStatus: () => request<Record<string, boolean>>("/settings/keys"),
  },
};
