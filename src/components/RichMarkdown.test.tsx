import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RichMarkdown } from "./RichMarkdown";

const fence = String.fromCharCode(96).repeat(3);
const markdown = (...lines: string[]) => lines.join(String.fromCharCode(10));

describe("RichMarkdown", () => {
  it("renders Mermaid flowchart nodes and connections as an SVG diagram", () => {
    render(<RichMarkdown content={markdown(fence + "mermaid", "flowchart TD", "  A[Inspect files] --> B[Verify output]", fence)} />);
    expect(screen.getByRole("group", { name: "Rendered Mermaid flowchart" })).toBeTruthy();
    expect(screen.getByText("Inspect files")).toBeTruthy();
    expect(screen.getByText("Verify output")).toBeTruthy();
    expect(screen.getByText(/2 nodes · 1 connections/)).toBeTruthy();
  });

  it("renders Mermaid xychart-beta data as a chart", () => {
    render(<RichMarkdown content={markdown(fence + "mermaid", "xychart-beta", '  title "Monthly sales"', '  x-axis ["Jan", "Feb"]', "  bar [12, 19]", fence)} />);
    expect(screen.getByRole("group", { name: "Monthly sales" })).toBeTruthy();
    expect(screen.getByText("Monthly sales")).toBeTruthy();
  });

  it("renders Mermaid sequence diagrams", () => {
    render(<RichMarkdown content={markdown(fence + "mermaid", "sequenceDiagram", "  participant U as User", "  participant A as Agent", "  U->>A: Inspect file", "  A-->>U: Verify output", fence)} />);
    expect(screen.getByRole("group", { name: "Rendered Mermaid sequence diagram" })).toBeTruthy();
    expect(screen.getByText(/2 participants · 2 messages/)).toBeTruthy();
  });



  it("copies code blocks and confirms the copy action", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    render(<RichMarkdown content={markdown(fence + "typescript", "const answer = 42;", fence)} />);
    fireEvent.click(screen.getByRole("button", { name: "Copy block" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("const answer = 42;"));
    expect((await screen.findByRole("status")).textContent).toBe("Copied");
  });

  it("provides copy controls for rendered Mermaid diagrams", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    const source = markdown(fence + "mermaid", "flowchart TD", "A[Start] --> B[Finish]", fence);
    render(<RichMarkdown content={source} />);
    fireEvent.click(screen.getByRole("button", { name: "Copy block" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("flowchart TD\\nA[Start] --> B[Finish]"));
  });

  it("renders structured chart JSON from a chart code fence", () => {
    render(<RichMarkdown content={markdown(fence + "chart", '{"type":"line","title":"Revenue","labels":["Q1","Q2"],"values":[10,15]}', fence)} />);
    expect(screen.getByRole("group", { name: "Revenue" })).toBeTruthy();
    expect(screen.getByText("Revenue")).toBeTruthy();
  });
});
