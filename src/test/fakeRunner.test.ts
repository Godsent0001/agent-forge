import { describe, it, expect } from "vitest";

export interface FakeExecutionEvent {
  id: string;
  execution_id: string;
  event_type: "run_start" | "agent_start" | "tool_start" | "tool_end" | "run_end" | "error";
  payload: Record<string, any>;
  timestamp: string;
}

export function generateFakeExecutionStream(executionId: string): FakeExecutionEvent[] {
  const now = new Date().toISOString();
  return [
    {
      id: "evt-1",
      execution_id: executionId,
      event_type: "run_start",
      payload: { message: "Starting agent execution run" },
      timestamp: now,
    },
    {
      id: "evt-2",
      execution_id: executionId,
      event_type: "agent_start",
      payload: { agent_name: "Primary Developer Agent", provider: "anthropic" },
      timestamp: now,
    },
    {
      id: "evt-3",
      execution_id: executionId,
      event_type: "tool_start",
      payload: { tool_name: "CodeSearch", query: "find React components" },
      timestamp: now,
    },
    {
      id: "evt-4",
      execution_id: executionId,
      event_type: "tool_end",
      payload: { tool_name: "CodeSearch", result_count: 5 },
      timestamp: now,
    },
    {
      id: "evt-5",
      execution_id: executionId,
      event_type: "run_end",
      payload: { status: "success", output: "Execution completed successfully." },
      timestamp: now,
    },
  ];
}

describe("Fake Runner Test Scenarios", () => {
  it("should generate deterministic execution event stream for UI testing", () => {
    const events = generateFakeExecutionStream("test-run-123");
    expect(events.length).toBe(5);
    expect(events[0].event_type).toBe("run_start");
    expect(events[events.length - 1].event_type).toBe("run_end");
  });
});
