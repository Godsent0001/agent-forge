import { describe, expect, it } from "vitest";
import type { ExecutionEvent } from "../types";
import singleAnswer from "./__fixtures__/single_answer.json";
import ceoResearch from "./__fixtures__/ceo_research.json";
import toolErrorRecovered from "./__fixtures__/tool_error_recovered.json";
import longRunning from "./__fixtures__/long_running.json";
import approvalPython from "./__fixtures__/approval_python.json";
import budgetExceeded from "./__fixtures__/budget_exceeded.json";
import { buildSpanTree, formatCost, formatDuration } from "./buildSpanTree";

let seq = 0;
const ev = (over: Partial<ExecutionEvent>): ExecutionEvent => ({
  execution_id: "e1",
  seq: ++seq,
  ts: `2026-10-11T20:00:${String(seq).padStart(2, "0")}Z`,
  type: "span_started",
  data: {},
  ...over,
});

function delegationRun(final: Partial<ExecutionEvent> = {}): ExecutionEvent[] {
  seq = 0;
  return [
    ev({ type: "execution_started" }),
    ev({ type: "span_started", span_id: "root", kind: "agent", name: "CEO", data: { depth: 0 } }),
    ev({ type: "span_started", span_id: "llm1", parent_span_id: "root", kind: "llm_call", data: { model: "m-fast" } }),
    ev({ type: "span_ended", span_id: "llm1", parent_span_id: "root", kind: "llm_call", status: "ok",
         data: { usage: { input_tokens: 100, output_tokens: 20 }, cost_usd: 0.002 } }),
    ev({ type: "span_started", span_id: "tool1", parent_span_id: "root", kind: "tool_call", name: "research_agent" }),
    ev({ type: "span_started", span_id: "sub", parent_span_id: "tool1", kind: "agent", name: "Research" }),
    ev({ type: "span_ended", span_id: "sub", parent_span_id: "tool1", kind: "agent", status: "error" }),
    ev({ type: "span_ended", span_id: "tool1", parent_span_id: "root", kind: "tool_call", status: "error" }),
    ev({ type: "span_ended", span_id: "root", kind: "agent", status: "ok" }),
    ev({ type: "execution_ended", ...final }),
  ];
}

describe("buildSpanTree with FakeRunner fixtures", () => {
  const events = (fixture: unknown) => fixture as ExecutionEvent[];

  it("renders the single-answer root as completed", () => {
    const tree = buildSpanTree(events(singleAnswer));
    expect(tree.roots).toHaveLength(1);
    expect(tree.roots[0].kind).toBe("agent");
    expect(tree.roots[0].status).toBe("ok");
  });

  it("nests CEO research delegation under its tool-call span", () => {
    const tree = buildSpanTree(events(ceoResearch));
    const root = tree.roots[0];
    const delegation = root.children.find((span) => span.kind === "tool_call" && span.label === "research_agent");
    expect(root.status).toBe("ok");
    expect(delegation?.children[0].label).toBe("Research Agent");
    expect(delegation?.children[0].status).toBe("ok");
  });

  it("keeps the root successful when a tool error is recovered", () => {
    const tree = buildSpanTree(events(toolErrorRecovered));
    const failedTool = tree.roots[0].children.find((span) => span.kind === "tool_call");
    expect(tree.roots[0].status).toBe("ok");
    expect(failedTool?.status).toBe("error");
  });

  it("shows cancelled spans for the long-running scenario", () => {
    const tree = buildSpanTree(events(longRunning));
    expect(tree.run?.status).toBe("cancelled");
    expect(tree.roots[0].status).toBe("cancelled");
  });

  it("renders the approval scenario without breaking the trace", () => {
    const tree = buildSpanTree(events(approvalPython));
    expect(tree.roots[0].status).toBe("ok");
    expect(tree.roots[0].children.some((span) => span.kind === "tool_call" && span.label === "python")).toBe(true);
  });

  it("preserves the budget-exceeded run status", () => {
    const tree = buildSpanTree(events(budgetExceeded));
    expect(tree.run?.status).toBe("budget_exceeded");
    expect(tree.roots[0].status).toBe("error");
  });
});

describe("buildSpanTree", () => {
  it("returns an empty result for no events", () => {
    expect(buildSpanTree([])).toEqual({ roots: [], run: null, spanCount: 0 });
  });

  it("nests agent -> tool_call -> sub-agent and keeps llm_call as a sibling", () => {
    const { roots, spanCount } = buildSpanTree(delegationRun());
    expect(spanCount).toBe(4);
    expect(roots).toHaveLength(1);
    const root = roots[0];
    expect(root.children.map((c) => c.kind)).toEqual(["llm_call", "tool_call"]);
    expect(root.children[1].children[0].label).toBe("Research");
  });

  it("does NOT report the run as failed just because a nested span failed", () => {
    const { run } = buildSpanTree(delegationRun({ data: { status: "completed" } }));
    expect(run?.status).toBe("completed");
    expect(run?.failedSpans).toBe(2);
  });

  it("uses the declared execution_ended status (error / cancelled / budget)", () => {
    expect(buildSpanTree(delegationRun({ data: { status: "error", error: "boom" } })).run).toMatchObject({
      status: "error",
      error: "boom",
    });
    expect(buildSpanTree(delegationRun({ data: { status: "budget_exceeded" } })).run?.status).toBe("budget_exceeded");
  });

  it("falls back to the root span when execution_ended has no status", () => {
    expect(buildSpanTree(delegationRun()).run?.status).toBe("completed");
  });

  it("is running until execution_ended arrives", () => {
    const partial = delegationRun().slice(0, 4);
    expect(buildSpanTree(partial).run?.status).toBe("running");
  });

  it("sums tokens and cost from llm_call spans when totals are not declared", () => {
    const { run } = buildSpanTree(delegationRun());
    expect(run?.totals).toMatchObject({ inputTokens: 100, outputTokens: 20, llmCalls: 1, toolCalls: 1 });
    expect(run?.totals.costUsd).toBeCloseTo(0.002);
  });

  it("prefers totals declared by the platform", () => {
    const { run } = buildSpanTree(
      delegationRun({ data: { status: "completed", totals: { llm_calls: 9, tool_calls: 4, input_tokens: 5, output_tokens: 6, cost_usd: null } } }),
    );
    expect(run?.totals).toEqual({ llmCalls: 9, toolCalls: 4, inputTokens: 5, outputTokens: 6, costUsd: null });
  });

  it("never throws on orphans, duplicates, or out-of-order events", () => {
    seq = 0;
    const events = [
      ev({ type: "span_started", span_id: "child", parent_span_id: "missing", kind: "tool_call", name: "t" }),
      ev({ type: "span_started", span_id: "child", parent_span_id: "missing", kind: "tool_call", name: "t" }),
      ev({ type: "span_ended", span_id: "ghost", kind: "agent", status: "ok" }),
    ];
    const tree = buildSpanTree([...events].reverse());
    expect(tree.roots).toHaveLength(1);
    expect(tree.roots[0].orphan).toBe(true);
  });

  it("labels well-known llm_call names", () => {
    seq = 0;
    const { roots } = buildSpanTree([
      ev({ span_id: "a", kind: "agent", name: "A" }),
      ev({ span_id: "m", parent_span_id: "a", kind: "llm_call", name: "memory_extract" }),
    ]);
    expect(roots[0].children[0].label).toBe("Memory extraction");
  });
});

describe("formatters", () => {
  it("formats durations", () => {
    expect(formatDuration(null)).toBe("");
    expect(formatDuration(420)).toBe("420 ms");
    expect(formatDuration(2500)).toBe("2.5 s");
    expect(formatDuration(75_000)).toBe("1m 15s");
  });
  it("formats cost", () => {
    expect(formatCost(null)).toBe("—");
    expect(formatCost(0)).toBe("$0");
    expect(formatCost(0.0004)).toBe("<$0.001");
    expect(formatCost(0.0049)).toBe("$0.005");
    expect(formatCost(0.1234)).toBe("$0.123");
    expect(formatCost(3.456)).toBe("$3.46");
  });
});
