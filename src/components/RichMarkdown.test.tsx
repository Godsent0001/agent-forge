import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RichMarkdown } from "./RichMarkdown";

const fence = String.fromCharCode(96).repeat(3);
const markdown = (...lines: string[]) => lines.join(String.fromCharCode(10));

describe("RichMarkdown", () => {
  it("renders Mermaid flowchart nodes and connections as an SVG diagram", () => {
    render(<RichMarkdown content={markdown(fence + "mermaid", "flowchart TD", "  A[Inspect files] --> B[Verify output]", fence)} />);
    expect(screen.getByRole("img", { name: "Rendered Mermaid flowchart" })).toBeTruthy();
    expect(screen.getByText("Inspect files")).toBeTruthy();
    expect(screen.getByText("Verify output")).toBeTruthy();
    expect(screen.getByText(/2 nodes · 1 connections/)).toBeTruthy();
  });

  it("renders Mermaid xychart-beta data as a chart", () => {
    render(<RichMarkdown content={markdown(fence + "mermaid", "xychart-beta", '  title "Monthly sales"', '  x-axis ["Jan", "Feb"]', "  bar [12, 19]", fence)} />);
    expect(screen.getByRole("img", { name: "Monthly sales" })).toBeTruthy();
    expect(screen.getByText("Monthly sales")).toBeTruthy();
  });

  it("renders Mermaid sequence diagrams", () => {
    render(<RichMarkdown content={markdown(fence + "mermaid", "sequenceDiagram", "  participant U as User", "  participant A as Agent", "  U->>A: Inspect file", "  A-->>U: Verify output", fence)} />);
    expect(screen.getByRole("img", { name: "Rendered Mermaid sequence diagram" })).toBeTruthy();
    expect(screen.getByText(/2 participants · 2 messages/)).toBeTruthy();
  });

  it("renders structured chart JSON from a chart code fence", () => {
    render(<RichMarkdown content={markdown(fence + "chart", '{"type":"line","title":"Revenue","labels":["Q1","Q2"],"values":[10,15]}', fence)} />);
    expect(screen.getByRole("img", { name: "Revenue" })).toBeTruthy();
    expect(screen.getByText("Revenue")).toBeTruthy();
  });
});
