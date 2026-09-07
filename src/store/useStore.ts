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
  createAgent: (name: string) => Promise<Agent | undefined>;
  updateAgent: (id: string, patch: Partial<Agent>) => Promise<void>;
  deleteAgent: (id: string) => Promise<void>;
  createTool: (name: string, kind: string) => Promise<void>;
  deleteTool: (id: string) => Promise<void>;
  attachToolToAgent: (agentId: string, toolId: string) => Promise<void>;
  detachToolFromAgent: (agentId: string, toolId: string) => Promise<void>;
  attachChildToAgent: (parentAgentId: string, childAgentId: string) => Promise<void>;
  detachChildFromAgent: (parentAgentId: string, childAgentId: string) => Promise<void>;
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
    return agent;
  },

  updateAgent: async (id, patch) => {
    const updated = await api.agents.update(id, patch);
    set({
      agents: get().agents.map((a) => (a.id === id ? { ...a, ...updated } : a)),
    });
  },

  deleteAgent: async (id) => {
    await api.agents.remove(id);
    const { agents, selectedAgentId } = get();
    const updatedAgents = agents
      .filter((a) => a.id !== id)
      .map((a) => ({
        ...a,
        child_agent_ids: (a.child_agent_ids ?? []).filter((cid) => cid !== id),
      }));
    set({
      agents: updatedAgents,
      selectedAgentId: selectedAgentId === id ? (updatedAgents[0]?.id ?? null) : selectedAgentId,
    });
  },

  createTool: async (name, kind) => {
    const { project, tools } = get();
    if (!project) return;
    const tool = await api.tools.create({ project_id: project.id, name, kind });
    set({ tools: [...tools, tool] });
  },

  deleteTool: async (id) => {
    await api.tools.remove(id);
    const { tools, agents } = get();
    set({
      tools: tools.filter((t) => t.id !== id),
      agents: agents.map((a) => ({
        ...a,
        tool_ids: (a.tool_ids ?? []).filter((tid) => tid !== id),
      })),
    });
  },

  attachToolToAgent: async (agentId, toolId) => {
    await api.agents.attachTool(agentId, toolId);
    set({
      agents: get().agents.map((a) =>
        a.id === agentId && !(a.tool_ids ?? []).includes(toolId)
          ? { ...a, tool_ids: [...(a.tool_ids ?? []), toolId] }
          : a
      ),
    });
  },

  detachToolFromAgent: async (agentId, toolId) => {
    await api.agents.detachTool(agentId, toolId);
    set({
      agents: get().agents.map((a) =>
        a.id === agentId
          ? { ...a, tool_ids: (a.tool_ids ?? []).filter((tid) => tid !== toolId) }
          : a
      ),
    });
  },

  attachChildToAgent: async (parentAgentId, childAgentId) => {
    await api.agents.attachChildAgent(parentAgentId, childAgentId);
    set({
      agents: get().agents.map((a) =>
        a.id === parentAgentId && !(a.child_agent_ids ?? []).includes(childAgentId)
          ? { ...a, child_agent_ids: [...(a.child_agent_ids ?? []), childAgentId] }
          : a
      ),
    });
  },

  detachChildFromAgent: async (parentAgentId, childAgentId) => {
    await api.agents.detachChildAgent(parentAgentId, childAgentId);
    set({
      agents: get().agents.map((a) =>
        a.id === parentAgentId
          ? { ...a, child_agent_ids: (a.child_agent_ids ?? []).filter((cid) => cid !== childAgentId) }
          : a
      ),
    });
  },

  attachToolToSelected: async (toolId) => {
    const { selectedAgentId, attachToolToAgent } = get();
    if (selectedAgentId) {
      await attachToolToAgent(selectedAgentId, toolId);
    }
  },

  attachChildToSelected: async (childAgentId) => {
    const { selectedAgentId, attachChildToAgent } = get();
    if (selectedAgentId) {
      await attachChildToAgent(selectedAgentId, childAgentId);
    }
  },
}));
