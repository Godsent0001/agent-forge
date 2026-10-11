import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";

const { agents, tools, selectAgent, attachChildToAgent, detachChildFromAgent } = vi.hoisted(() => ({
  agents: [
    { id: "agent-a", project_id: "project-1", name: "Alpha", description: "", provider: "google", model: "gemini-test", system_prompt: "", tool_use_schema: "", memory_enabled: false, created_at: "", tool_ids: [], child_agent_ids: [] },
    { id: "agent-b", project_id: "project-1", name: "Beta", description: "", provider: "openai", model: "gpt-test", system_prompt: "", tool_use_schema: "", memory_enabled: false, created_at: "", tool_ids: [], child_agent_ids: [] },
  ],
  tools: [] as Array<{ id: string; name: string; kind: string }>,
  selectAgent: vi.fn(),
  attachChildToAgent: vi.fn().mockResolvedValue(undefined),
  detachChildFromAgent: vi.fn().mockResolvedValue(undefined),
}));

vi.mock("../store/useStore", () => ({
  useStore: (selector: (state: any) => any) => selector({
    agents, tools, selectedAgentId: "agent-a", project: { id: "project-1" },
    selectAgent, attachChildToAgent, detachChildFromAgent,
  }),
}));
vi.mock("./ToolCatalogModal", () => ({ ToolCatalogModal: () => null }));
import { WorkflowCanvas } from "./WorkflowCanvas";

describe("WorkflowCanvas editing", () => {
  beforeEach(() => {
    window.localStorage.clear();
    agents[0].child_agent_ids = [];
    vi.clearAllMocks();
    attachChildToAgent.mockResolvedValue(undefined);
    detachChildFromAgent.mockResolvedValue(undefined);
    if (!HTMLElement.prototype.setPointerCapture) Object.defineProperty(HTMLElement.prototype, "setPointerCapture", { configurable: true, value: vi.fn() });
    if (!document.elementFromPoint) Object.defineProperty(document, "elementFromPoint", { configurable: true, value: () => null });
  });
  afterEach(() => vi.restoreAllMocks());

  it("connects an agent output to another agent input and persists delegation", async () => {
    vi.spyOn(document, "elementFromPoint").mockImplementation(() => screen.getByRole("button", { name: "Connect to Beta" }));
    render(<WorkflowCanvas />);

    fireEvent.pointerDown(screen.getByRole("button", { name: "Connect from Alpha" }), { pointerId: 1, button: 0, clientX: 690, clientY: 230 });
    fireEvent.pointerMove(screen.getByTestId("workflow-canvas"), { pointerId: 1, clientX: 790, clientY: 130 });
    fireEvent.pointerUp(screen.getByTestId("workflow-canvas"), { pointerId: 1, clientX: 790, clientY: 130 });

    expect(await screen.findByRole("button", { name: "Remove connection from Alpha to Beta" })).toBeInTheDocument();
    await waitFor(() => expect(attachChildToAgent).toHaveBeenCalledWith("agent-a", "agent-b"));
    expect(window.localStorage.getItem("agentforge.workflow.connections.project-1.agent-a")).toContain("agent-a->child-agent-b");
    expect(screen.getByRole("status")).toHaveTextContent("Delegation updated");
  });

  it("reconciles stored editor links with actual delegated agents", async () => {
    agents[0].child_agent_ids = ["agent-b"];
    window.localStorage.setItem("agentforge.workflow.connections.project-1.agent-a", JSON.stringify([]));
    render(<WorkflowCanvas />);

    expect(await screen.findByRole("button", { name: "Remove connection from Alpha to Beta" })).toBeInTheDocument();
  });

  it("does not change the primary agent when starting a connection from a candidate", async () => {
    vi.spyOn(document, "elementFromPoint").mockImplementation(() => screen.getByRole("button", { name: "Connect to Alpha" }));
    render(<WorkflowCanvas />);

    fireEvent.pointerDown(screen.getByRole("button", { name: "Connect from Beta" }), { pointerId: 3, button: 0, clientX: 1026, clientY: 130 });
    fireEvent.pointerMove(screen.getByTestId("workflow-canvas"), { pointerId: 3, clientX: 500, clientY: 230 });
    fireEvent.pointerUp(screen.getByTestId("workflow-canvas"), { pointerId: 3, clientX: 500, clientY: 230 });

    expect(selectAgent).not.toHaveBeenCalled();
    expect(await screen.findByRole("button", { name: "Remove connection from Beta to Alpha" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Editor link saved");
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

  it("removes a saved agent connection using the wire itself", async () => {
    window.localStorage.setItem("agentforge.workflow.connections.project-1.agent-a", JSON.stringify([
      { id: "agent-a->child-agent-b", source: "agent-a", target: "child-agent-b" },
    ]));
    render(<WorkflowCanvas />);

    fireEvent.click(await screen.findByRole("button", { name: "Remove connection from Alpha to Beta" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Remove connection from Alpha to Beta" })).not.toBeInTheDocument());
    expect(detachChildFromAgent).toHaveBeenCalledWith("agent-a", "agent-b");
  });
});
