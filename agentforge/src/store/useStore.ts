import { create } from "zustand";
import { api } from "../api/client";
import type { Agent, Project, Tool } from "../types";

interface StoreState {
  project: Project | null;
  agents: Agent[];
  tools: Tool[];
  selectedAgentId: string | null;

  loadProject: (project: Project) => Promise<void>;
  selectAgent: (id: string | null) => void;
  createAgent: (name: string) => Promise<void>;
  updateAgent: (id: string, patch: Partial<Agent>) => Promise<void>;
  createTool: (name: string, kind: string) => Promise<void>;
  attachToolToSelected: (toolId: string) => Promise<void>;
  attachChildToSelected: (childAgentId: string) => Promise<void>;
}

export const useStore = create<StoreState>((set, get) => ({
  project: null,
  agents: [],
  tools: [],
  selectedAgentId: null,

  loadProject: async (project) => {
    set({ project });
    const [agents, tools] = await Promise.all([
      api.agents.list(project.id),
      api.tools.list(project.id),
    ]);
    set({ agents, tools });
  },

  selectAgent: (id) => set({ selectedAgentId: id }),

  createAgent: async (name) => {
    const { project, agents } = get();
    if (!project) return;
    const agent = await api.agents.create({ project_id: project.id, name });
    set({ agents: [...agents, agent], selectedAgentId: agent.id });
  },

  updateAgent: async (id, patch) => {
    const updated = await api.agents.update(id, patch);
    set({ agents: get().agents.map((a) => (a.id === id ? updated : a)) });
  },

  createTool: async (name, kind) => {
    const { project, tools } = get();
    if (!project) return;
    const tool = await api.tools.create({ project_id: project.id, name, kind });
    set({ tools: [...tools, tool] });
  },

  attachToolToSelected: async (toolId) => {
    const { selectedAgentId, agents } = get();
    if (!selectedAgentId) return;
    await api.agents.attachTool(selectedAgentId, toolId);
    set({
      agents: agents.map((a) =>
        a.id === selectedAgentId
          ? { ...a, tool_ids: [...(a.tool_ids ?? []), toolId] }
          : a
      ),
    });
  },

  attachChildToSelected: async (childAgentId) => {
    const { selectedAgentId, agents } = get();
    if (!selectedAgentId) return;
    // Errors (cycle/depth violations) surface as thrown exceptions from the
    // API client — callers (AgentEditor) are responsible for catching and
    // showing them, since this is a case where "premium UI" means a clear
    // inline error, not a silent no-op or an alert().
    await api.agents.attachChildAgent(selectedAgentId, childAgentId);
    set({
      agents: agents.map((a) =>
        a.id === selectedAgentId
          ? { ...a, child_agent_ids: [...(a.child_agent_ids ?? []), childAgentId] }
          : a
      ),
    });
  },
}));
