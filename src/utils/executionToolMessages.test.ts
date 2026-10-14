import { describe, expect, it } from "vitest";
import { executionToolMessages } from "./executionToolMessages";
import type { ExecutionEvent } from "../types";

const event = (overrides: Partial<ExecutionEvent>): ExecutionEvent => ({
  execution_id: "exec-1",
  seq: 1,
  ts: "2026-10-07T00:00:00Z",
  type: "span_started",
  span_id: "span-1",
  parent_span_id: "root-1",
  kind: "tool_call",
  name: "web_search",
  data: { args: "latest AgentForge docs" },
  ...overrides,
});

describe("executionToolMessages", () => {
  it("pairs a tool span start with its completed result", () => {
    const messages = executionToolMessages([
      event({
        seq: 2,
        type: "span_started",
        span_id: "tool-1",
        name: "web_search",
        data: { args: "latest AgentForge docs" },
      }),
      event({
        seq: 3,
        type: "span_ended",
        span_id: "tool-1",
        name: "web_search",
        status: "ok",
        data: { result_preview: "Found the docs." },
      }),
    ]);

    expect(messages).toHaveLength(1);
    expect(messages[0]).toMatchObject({
      sender: "tool",
      toolName: "web_search",
      toolInput: "latest AgentForge docs",
      toolOutput: "Found the docs.",
      toolStatus: "ok",
    });
  });

  it("keeps completed tool calls ordered by event sequence", () => {
    const messages = executionToolMessages([
      event({ seq: 4, type: "span_ended", span_id: "tool-2", name: "python", status: "ok", data: { result_preview: "second" } }),
      event({ seq: 2, type: "span_started", span_id: "tool-2", name: "python", data: { args: "2 + 2" } }),
      event({ seq: 3, type: "span_started", span_id: "tool-1", name: "web_search", data: { args: "docs" } }),
      event({ seq: 5, type: "span_ended", span_id: "tool-1", name: "web_search", status: "error", data: { result_preview: "network failed" } }),
    ]);

    expect(messages.filter((m) => m.sender === "tool").map((m) => m.toolName)).toEqual(["python", "web_search"]);
    const failed = messages.find((m) => m.sender === "tool" && m.toolName === "web_search");
    expect(failed?.sender).toBe("tool");
    if (failed?.sender === "tool") {
      expect(failed.toolStatus).toBe("error");
    }
  });
});
