import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const fetchProjects = vi.fn();
const loadProject = vi.fn();

vi.mock("./api/client", () => ({
  getApiBase: vi.fn().mockResolvedValue("http://127.0.0.1:8000"),
  api: {
    settings: { syncKeysToBackend: vi.fn().mockResolvedValue(undefined) },
    projects: { create: vi.fn() },
  },
}));

vi.mock("./store/useStore", () => ({
  useStore: (selector: (state: unknown) => unknown) =>
    selector({ fetchProjects, loadProject }),
}));

vi.mock("./components/TopBar", () => ({
  TopBar: () => <div data-testid="top-bar">Top bar</div>,
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
  AgentChat: () => <main data-testid="agent-chat">Agent chat</main>,
}));

vi.mock("./components/AgentEditor", () => ({
  AgentEditor: () => <main data-testid="agent-editor">Agent editor</main>,
}));

import App from "./App";

describe("App bootstrap and workspace layout", () => {
  beforeEach(() => {
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
    expect(screen.getByTestId("execution-tree")).toHaveTextContent("No execution");
    expect(fetchProjects).toHaveBeenCalledTimes(1);
    expect(loadProject).toHaveBeenCalledTimes(1);
  });
});
