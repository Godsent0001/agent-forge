import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { fetchProjects, loadProject, syncKeysToBackend, createProject } = vi.hoisted(() => ({
  fetchProjects: vi.fn(),
  loadProject: vi.fn(),
  syncKeysToBackend: vi.fn(),
  createProject: vi.fn(),
}));

vi.mock("./api/client", () => ({
  getApiBase: vi.fn().mockResolvedValue("http://127.0.0.1:8000"),
  api: {
    settings: { syncKeysToBackend },
    projects: { create: createProject },
  },
}));

vi.mock("./store/useStore", () => ({
  useStore: (selector: (state: unknown) => unknown) =>
    selector({
      fetchProjects,
      loadProject,
      project: { id: "project-1", name: "Test Project" },
      projects: [],
      agents: [],
      tools: [],
      selectedAgentId: null,
      chatMessages: {},
      pendingTask: null,
      selectAgent: vi.fn(),
      queueTask: vi.fn(),
      consumePendingTask: vi.fn(() => null),
      addChatMessage: vi.fn(),
      setChatMessages: vi.fn(),
      clearChat: vi.fn(),
      switchProject: vi.fn(),
      createProject: vi.fn(),
      updateProjectSettings: vi.fn(),
      createAgent: vi.fn(),
      updateAgent: vi.fn(),
      deleteAgent: vi.fn(),
      createTool: vi.fn(),
      deleteTool: vi.fn(),
      attachToolToAgent: vi.fn(),
      detachToolFromAgent: vi.fn(),
      attachChildToAgent: vi.fn(),
      detachChildFromAgent: vi.fn(),
      attachToolToSelected: vi.fn(),
      attachChildToSelected: vi.fn(),
    }),
}));

vi.mock("./components/TopBar", () => ({
  TopBar: ({ onTabChange }: { onTabChange: (tab: "canvas" | "chat" | "config") => void }) => (
    <div data-testid="top-bar">
      Top bar
      <button onClick={() => onTabChange("canvas")}>Editor</button>
      <button onClick={() => onTabChange("chat")}>Chat</button>
      <button onClick={() => onTabChange("config")}>Agent</button>
    </div>
  ),
}));

vi.mock("./components/AgentTree", () => ({
  AgentTree: () => <aside data-testid="agent-tree">Agent tree</aside>,
}));

vi.mock("./components/ExecutionTree", () => ({
  ExecutionTree: ({ executionId }: { executionId: string | null }) => (
    <aside data-testid="execution-tree">{executionId ?? "No execution"}</aside>
  ),
}));

vi.mock("./components/AgentChat", () => ({
  AgentChat: ({ onRunExecution }: { onRunExecution: (id: string) => void }) => (
    <main data-testid="agent-chat">
      Agent chat
      <button onClick={() => onRunExecution("execution-123")}>Simulate chat run</button>
    </main>
  ),
}));

vi.mock("./components/AgentEditor", () => ({
  AgentEditor: () => <main data-testid="agent-editor">Agent editor</main>,
}));

vi.mock("./components/WorkflowCanvas", () => ({
  WorkflowCanvas: () => <main data-testid="workflow-canvas">Workflow canvas</main>,
}));

vi.mock("./components/PropertiesPanel", () => ({
  PropertiesPanel: () => <aside data-testid="properties-panel">Properties panel</aside>,
}));

vi.mock("./components/AgentWorkspacePanel", () => ({
  AgentWorkspacePanel: () => <aside data-testid="agent-workspace">Agent Workspace</aside>,
}));

import App from "./App";

describe("App bootstrap and workspace layout", () => {
  beforeEach(() => {
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 1024 });
    vi.clearAllMocks();
    fetchProjects.mockResolvedValue([
      {
        id: "project-1",
        name: "Test Project",
      },
    ]);
    loadProject.mockResolvedValue(undefined);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
      }),
    );
  });

  it("boots into a single-row three-panel workspace after the sidecar is healthy", async () => {
    render(<App />);

    await waitFor(() => expect(screen.getByTestId("agent-chat")).toBeInTheDocument());

    expect(screen.getByTestId("agent-tree")).toBeInTheDocument();
    expect(screen.getByTestId("agent-chat")).toBeInTheDocument();
    expect(screen.getByTestId("properties-panel")).toBeInTheDocument();
    expect(screen.queryByTestId("execution-tree")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Model & delegation" }));
    expect(screen.queryByTestId("properties-panel")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Model & delegation" }));
    expect(screen.getByTestId("properties-panel")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Activity" }));
    expect(screen.getByTestId("execution-tree")).toHaveTextContent("No execution");
    fireEvent.click(screen.getByRole("button", { name: "Activity" }));
    expect(screen.queryByTestId("execution-tree")).not.toBeInTheDocument();
    expect(fetchProjects).toHaveBeenCalledTimes(1);
    expect(loadProject).toHaveBeenCalledTimes(1);
  });

  it("keeps Editor and Chat separate and toggles editor inspector and logs from the side rail", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("agent-chat")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Editor" }));
    expect(screen.getByTestId("workflow-canvas")).toBeInTheDocument();
    expect(screen.queryByTestId("agent-chat")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Inspector" }));
    expect(screen.queryByTestId("properties-panel")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Inspector" }));
    expect(screen.getByTestId("properties-panel")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "View logs" }));
    expect(screen.getByTestId("execution-tree")).toHaveTextContent("No execution");
    fireEvent.click(screen.getByRole("button", { name: "View logs" }));
    expect(screen.queryByTestId("execution-tree")).not.toBeInTheDocument();
  });

  it("starts compact viewports with chat unobstructed and opens settings on demand", async () => {
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 390 });
    render(<App />);

    await waitFor(() => expect(screen.getByTestId("agent-chat")).toBeInTheDocument());
    expect(screen.queryByTestId("properties-panel")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Model & delegation" }));
    expect(screen.getByTestId("properties-panel")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Model & delegation" }));
    expect(screen.queryByTestId("properties-panel")).not.toBeInTheDocument();
  });

  it("opens the workspace from the side rail and keeps it available on the Agent screen", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("agent-chat")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Agent Workspace" }));
    expect(screen.getByTestId("agent-workspace")).toBeInTheDocument();
    expect(screen.queryByTestId("properties-panel")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Agent Workspace" }));
    expect(screen.queryByTestId("agent-workspace")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Agent" }));
    fireEvent.click(screen.getByRole("button", { name: "Agent Workspace" }));
    expect(screen.getByTestId("agent-workspace")).toBeInTheDocument();
  });

  it("opens the live Activity inspector when a chat execution starts", async () => {
    render(<App />);

    await waitFor(() => expect(screen.getByTestId("agent-chat")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Simulate chat run" }));

    expect(await screen.findByTestId("execution-tree")).toHaveTextContent("execution-123");
    expect(screen.queryByTestId("properties-panel")).not.toBeInTheDocument();
  });
});
