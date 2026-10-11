import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";

const { agents, tools, selectAgent, attachChildToAgent, detachChildFromAgent, attachToolToAgent, detachToolFromAgent } = vi.hoisted(() => ({
  agents: [
    { id: "agent-a", project_id: "project-1", name: "Alpha", description: "", provider: "google", model: "gemini-test", system_prompt: "", tool_use_schema: "", memory_enabled: false, created_at: "", tool_ids: [] as string[], child_agent_ids: [] as string[] },
    { id: "agent-b", project_id: "project-1", name: "Beta", description: "", provider: "openai", model: "gpt-test", system_prompt: "", tool_use_schema: "", memory_enabled: false, created_at: "", tool_ids: [] as string[], child_agent_ids: [] as string[] },
  ],
  tools: [{
    id: "tool-search", project_id: "project-1", name: "Search API", description: "Search documentation",
    kind: "http", input_schema: {}, output_schema: {}, config: {},
  }],
  selectAgent: vi.fn(),
  attachChildToAgent: vi.fn(),
  detachChildFromAgent: vi.fn(),
  attachToolToAgent: vi.fn(),
  detachToolFromAgent: vi.fn(),
}));

vi.mock("../store/useStore", () => ({
  useStore: (selector: (state: any) => any) => selector({
    agents, tools, selectedAgentId: "agent-a", project: { id: "project-1" },
    selectAgent, attachChildToAgent, detachChildFromAgent, attachToolToAgent, detachToolFromAgent,
  }),
}));
vi.mock("./ToolCatalogModal", () => ({ ToolCatalogModal: () => null }));
import { WorkflowCanvas } from "./WorkflowCanvas";

describe("WorkflowCanvas editing", () => {
  beforeEach(() => {
    window.localStorage.clear();
    agents.forEach((agent) => { agent.child_agent_ids = []; agent.tool_ids = []; });
    vi.clearAllMocks();
    attachChildToAgent.mockImplementation(async (parentId: string, childId: string) => {
      const parent = agents.find((agent) => agent.id === parentId);
      if (parent && !parent.child_agent_ids.includes(childId)) parent.child_agent_ids.push(childId);
    });
    detachChildFromAgent.mockImplementation(async (parentId: string, childId: string) => {
      const parent = agents.find((agent) => agent.id === parentId);
      if (parent) parent.child_agent_ids = parent.child_agent_ids.filter((id: string) => id !== childId);
    });
    attachToolToAgent.mockImplementation(async (agentId: string, toolId: string) => {
      const agent = agents.find((item) => item.id === agentId);
      if (agent && !agent.tool_ids.includes(toolId)) agent.tool_ids.push(toolId);
    });
    detachToolFromAgent.mockImplementation(async (agentId: string, toolId: string) => {
      const agent = agents.find((item) => item.id === agentId);
      if (agent) agent.tool_ids = agent.tool_ids.filter((id: string) => id !== toolId);
    });
    if (!HTMLElement.prototype.setPointerCapture) Object.defineProperty(HTMLElement.prototype, "setPointerCapture", { configurable: true, value: vi.fn() });
    if (!document.elementFromPoint) Object.defineProperty(document, "elementFromPoint", { configurable: true, value: () => null });
  });
  afterEach(() => vi.restoreAllMocks());

  it("pans the canvas when dragging empty space beneath the connection layer", () => {
    render(<WorkflowCanvas />);
    const canvas = screen.getByTestId("workflow-canvas");
    const connectionLayer = screen.getByLabelText("Workflow connections");

    fireEvent.pointerDown(connectionLayer, { pointerId: 10, button: 0, clientX: 50, clientY: 50 });
    fireEvent.pointerMove(canvas, { pointerId: 10, clientX: 100, clientY: 100 });
    fireEvent.pointerUp(canvas, { pointerId: 10, clientX: 100, clientY: 100 });

    const graphSurface = canvas.querySelector("[data-canvas-background='true']");
    expect(graphSurface?.getAttribute("style")).toContain("translate(62px, 58px)");
  });

  it("connects an agent output to another agent input through real delegation state", async () => {
    vi.spyOn(document, "elementFromPoint").mockImplementation(() => screen.getByRole("button", { name: "Connect to Beta" }));
    render(<WorkflowCanvas />);

    fireEvent.pointerDown(screen.getByRole("button", { name: "Connect from Alpha" }), { pointerId: 1, button: 0, clientX: 690, clientY: 230 });
    fireEvent.pointerMove(screen.getByTestId("workflow-canvas"), { pointerId: 1, clientX: 790, clientY: 130 });
    fireEvent.pointerUp(screen.getByTestId("workflow-canvas"), { pointerId: 1, clientX: 790, clientY: 130 });

    await waitFor(() => expect(attachChildToAgent).toHaveBeenCalledWith("agent-a", "agent-b"));
    expect(await screen.findByRole("button", { name: "Remove connection from Alpha to Beta" })).toBeInTheDocument();
    expect(agents[0].child_agent_ids).toContain("agent-b");
    expect(screen.getByRole("status")).toHaveTextContent("Agent delegation connected.");
  });

  it("draws relationships from the agent model rather than saved decorative edges", async () => {
    agents[0].child_agent_ids = ["agent-b"];
    window.localStorage.setItem("agentforge.workflow.connections.project-1.agent-a", JSON.stringify([]));
    render(<WorkflowCanvas />);
    expect(await screen.findByRole("button", { name: "Remove connection from Alpha to Beta" })).toBeInTheDocument();
  });

  it("does not switch the primary agent when connecting from a candidate", async () => {
    vi.spyOn(document, "elementFromPoint").mockImplementation(() => screen.getByRole("button", { name: "Connect to Alpha" }));
    render(<WorkflowCanvas />);

    fireEvent.pointerDown(screen.getByRole("button", { name: "Connect from Beta" }), { pointerId: 3, button: 0, clientX: 1026, clientY: 130 });
    fireEvent.pointerMove(screen.getByTestId("workflow-canvas"), { pointerId: 3, clientX: 500, clientY: 230 });
    fireEvent.pointerUp(screen.getByTestId("workflow-canvas"), { pointerId: 3, clientX: 500, clientY: 230 });

    await waitFor(() => expect(attachChildToAgent).toHaveBeenCalledWith("agent-b", "agent-a"));
    expect(selectAgent).not.toHaveBeenCalled();
    expect(await screen.findByRole("button", { name: "Remove connection from Beta to Alpha" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Agent delegation connected.");
  });

  it("moves a node and persists its layout across mounts", async () => {
    const { unmount } = render(<WorkflowCanvas />);
    const beta = screen.getByRole("group", { name: "Beta" });

    fireEvent.pointerDown(beta, { pointerId: 2, button: 0, clientX: 800, clientY: 150 });
    fireEvent.pointerMove(screen.getByTestId("workflow-canvas"), { pointerId: 2, clientX: 910, clientY: 220 });
    fireEvent.pointerUp(screen.getByTestId("workflow-canvas"), { pointerId: 2, clientX: 910, clientY: 220 });

    await waitFor(() => {
      const stored = window.localStorage.getItem("agentforge.workflow.connections.project-1.agent-a.positions");
      expect(stored).toContain('"x":900');
      expect(stored).toContain('"y":160');
    });
    unmount();

    render(<WorkflowCanvas />);
    await waitFor(() => expect(screen.getByRole("group", { name: "Beta" })).toHaveStyle({ left: "900px", top: "160px" }));
  });

  it("connects an agent to a project tool to attach a real capability", async () => {
    vi.spyOn(document, "elementFromPoint").mockImplementation(() => screen.getByRole("button", { name: "Connect to Search API" }));
    render(<WorkflowCanvas />);

    fireEvent.pointerDown(screen.getByRole("button", { name: "Connect from Alpha" }), { pointerId: 4, button: 0, clientX: 690, clientY: 230 });
    fireEvent.pointerMove(screen.getByTestId("workflow-canvas"), { pointerId: 4, clientX: 1190, clientY: 130 });
    fireEvent.pointerUp(screen.getByTestId("workflow-canvas"), { pointerId: 4, clientX: 1190, clientY: 130 });

    await waitFor(() => expect(attachToolToAgent).toHaveBeenCalledWith("agent-a", "tool-search"));
    expect(agents[0].tool_ids).toContain("tool-search");
    expect(await screen.findByRole("button", { name: "Remove connection from Alpha to Search API" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Tool attached to agent.");
  });

  it("removes an agent relationship by clicking its wire", async () => {
    agents[0].child_agent_ids = ["agent-b"];
    render(<WorkflowCanvas />);

    fireEvent.click(await screen.findByRole("button", { name: "Remove connection from Alpha to Beta" }));
    await waitFor(() => expect(detachChildFromAgent).toHaveBeenCalledWith("agent-a", "agent-b"));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Remove connection from Alpha to Beta" })).not.toBeInTheDocument());
  });

  it("detaches a tool by clicking the wire to that tool", async () => {
    agents[0].tool_ids = ["tool-search"];
    render(<WorkflowCanvas />);

    fireEvent.click(await screen.findByRole("button", { name: "Remove connection from Alpha to Search API" }));
    await waitFor(() => expect(detachToolFromAgent).toHaveBeenCalledWith("agent-a", "tool-search"));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Remove connection from Alpha to Search API" })).not.toBeInTheDocument());
  });
});
