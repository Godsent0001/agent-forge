import { create } from "zustand";
import { api } from "../api/client";
import type { Agent, Project, Tool } from "../types";

interface StoreState {
  projects: Project[];
  project: Project | null;
  agents: Agent[];
  tools: Tool[];
  selectedAgentId: string | null;

  fetchProjects: () => Promise<Project[]>;
  switchProject: (projectId: string) => Promise<void>;
  createProject: (name: string) => Promise<void>;
  updateProjectSettings: (patch: { name?: string; parallel_execution?: boolean }) => Promise<void>;
  loadProject: (project: Project) => Promise<void>;
  selectAgent: (id: string | null) => void;
  createAgent: (name: string) => Promise<void>;
  updateAgent: (id: string, patch: Partial<Agent>) => Promise<void>;
  createTool: (name: string, kind: string) => Promise<void>;
  attachToolToSelected: (toolId: string) => Promise<void>;
  attachChildToSelected: (childAgentId: string) => Promise<void>;
}

export const useStore = create<StoreState>((set, get) => ({
  projects: [],
  project: null,
  agents: [],
  tools: [],
  selectedAgentId: null,

  fetchProjects: async () => {
    const projects = await api.projects.list();
    set({ projects });
    return projects;
  },

  switchProject: async (projectId) => {
    const projects = get().projects;
    const proj = projects.find((p) => p.id === projectId);
    if (proj) {
      await get().loadProject(proj);
    }
  },

  createProject: async (name) => {
    const newProj = await api.projects.create(name);
    const projects = [...get().projects, newProj];
    set({ projects });
    await get().loadProject(newProj);
  },

  updateProjectSettings: async (patch) => {
    const { project, projects } = get();
    if (!project) return;
    const updated = await api.projects.update(project.id, patch);
    set({
      project: updated,
      projects: projects.map((p) => (p.id === updated.id ? updated : p)),
    });
  },

  loadProject: async (project) => {
    set({ project, selectedAgentId: null });
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
