import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RichMarkdown } from "./RichMarkdown";

describe("RichMarkdown", () => {
  it("renders Mermaid flowchart nodes and connections as an SVG diagram", () => {
    render(<RichMarkdown content={"\x60\x60\x60mermaid\nflowchart TD\n  A[Inspect files] --> B[Verify output]\n\x60\x60\x60"} />);
    expect(screen.getByRole("img", { name: "Rendered Mermaid flowchart" })).toBeTruthy();
    expect(screen.getByText("Inspect files")).toBeTruthy();
    expect(screen.getByText("Verify output")).toBeTruthy();
    expect(screen.getByText(/2 nodes · 1 connections/)).toBeTruthy();
  });

  it("renders Mermaid xychart-beta data as a chart", () => {
    render(<RichMarkdown content={"\x60\x60\x60mermaid\nxychart-beta\n  title \"Monthly sales\"\n  x-axis [\"Jan\", \"Feb\"]\n  bar [12, 19]\n\x60\x60\x60"} />);
    expect(screen.getByRole("img", { name: "Monthly sales" })).toBeTruthy();
    expect(screen.getByText("Monthly sales")).toBeTruthy();
  });

  it("renders structured chart JSON from a chart code fence", () => {
    render(<RichMarkdown content={"\x60\x60\x60chart\n{\"type\":\"line\",\"title\":\"Revenue\",\"labels\":[\"Q1\",\"Q2\"],\"values\":[10,15]}\n\x60\x60\x60"} />);
    expect(screen.getByRole("img", { name: "Revenue" })).toBeTruthy();
    expect(screen.getByText("Revenue")).toBeTruthy();
  });
});
