import { keychain } from "./keychain";
import type { Agent, CatalogShelf, CatalogToolEntry, Project, Tool } from "../types";

let currentApiBase = "http://127.0.0.1:8756";
let portInitPromise: Promise<void> | null = null;

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
          throw new Error("Could not connect to Python backend: " + (err as Error).message);
        }
      } else {
        // Fallback for standalone web preview in dev
        currentApiBase = "http://127.0.0.1:8756";
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
  const res = await fetch(`${currentApiBase}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${options?.method ?? "GET"} ${path} failed: ${res.status} ${body}`);
  }
  return res.json();
}

export interface ExecutionResult {
  id: string;
  project_id: string;
  root_agent_id: string;
  input_task: string;
  final_output: string;
  status: string;
  started_at: string;
  completed_at: string | null;
}

export const api = {
  projects: {
    list: () => request<Project[]>("/projects"),
    create: (name: string, parallel_execution = false) =>
      request<Project>("/projects", { method: "POST", body: JSON.stringify({ name, parallel_execution }) }),
    update: (id: string, patch: { name?: string; parallel_execution?: boolean }) =>
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
    run: (project_id: string, root_agent_id: string, task: string) =>
      request<ExecutionResult>("/executions", {
        method: "POST",
        body: JSON.stringify({ project_id, root_agent_id, task }),
      }),
    get: (id: string) => request<ExecutionResult>(`/executions/${id}`),
  },
  catalog: {
    list: () => request<CatalogToolEntry[]>("/catalog"),
    shelves: () => request<CatalogShelf[]>("/catalog/shelves"),
  },
  settings: {
    getKeys: async () => ({
      anthropic: (await keychain.get("anthropic")) ?? "",
      openai: (await keychain.get("openai")) ?? "",
      google: (await keychain.get("google")) ?? "",
    }),
    setKeys: async (keys: { anthropic?: string; openai?: string; google?: string }) => {
      if (keys.anthropic !== undefined) await keychain.save("anthropic", keys.anthropic);
      if (keys.openai !== undefined) await keychain.save("openai", keys.openai);
      if (keys.google !== undefined) await keychain.save("google", keys.google);

      // Sync keys to python sidecar runtime process
      const currentKeys = {
        anthropic: (await keychain.get("anthropic")) ?? "",
        openai: (await keychain.get("openai")) ?? "",
        google: (await keychain.get("google")) ?? "",
      };
      await request("/settings/keys", {
        method: "POST",
        body: JSON.stringify(currentKeys),
      });
    },
    syncKeysToBackend: async () => {
      const currentKeys = {
        anthropic: (await keychain.get("anthropic")) ?? "",
        openai: (await keychain.get("openai")) ?? "",
        google: (await keychain.get("google")) ?? "",
      };
      return request("/settings/keys", {
        method: "POST",
        body: JSON.stringify(currentKeys),
      });
    },
  },
};
