import { describe, expect, it } from "vitest";
import { reduceEvents } from "./useExecutionStream";
import type { ExecutionEvent } from "../types";

const event = (overrides: Partial<ExecutionEvent>): ExecutionEvent => ({
  execution_id: "exec-1",
  seq: 1,
  ts: "2026-10-07T00:00:00Z",
  type: "span_started",
  span_id: "span-1",
  parent_span_id: null,
  kind: "agent",
  name: "Agent",
  data: {},
  ...overrides,
});

describe("reduceEvents", () => {
  it("builds a parent-id tree for agent and tool spans", () => {
    const tree = reduceEvents([
      event({ seq: 1, span_id: "agent-1", kind: "agent", name: "CEO" }),
      event({
        seq: 2,
        span_id: "tool-1",
        parent_span_id: "agent-1",
        kind: "tool_call",
        name: "web_search",
      }),
      event({
        seq: 3,
        type: "span_ended",
        span_id: "tool-1",
        parent_span_id: "agent-1",
        kind: "tool_call",
        name: "web_search",
        status: "ok",
      }),
      event({
        seq: 4,
        type: "span_ended",
        span_id: "agent-1",
        kind: "agent",
        name: "CEO",
        status: "ok",
      }),
    ]);

    expect(tree).toHaveLength(1);
    expect(tree[0]).toMatchObject({
      id: "agent-1",
      label: "CEO",
      status: "completed",
    });
    expect(tree[0].children).toHaveLength(1);
    expect(tree[0].children[0]).toMatchObject({
      id: "tool-1",
      label: "web_search",
      kind: "tool_call",
      status: "completed",
    });
  });

  it("keeps duplicate labels distinct by span id", () => {
    const tree = reduceEvents([
      event({ seq: 1, span_id: "root-1", name: "Research" }),
      event({ seq: 2, span_id: "root-2", name: "Research" }),
    ]);

    expect(tree.map((node) => node.id)).toEqual(["root-1", "root-2"]);
  });
});
