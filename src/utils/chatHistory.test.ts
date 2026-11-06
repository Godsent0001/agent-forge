import { describe, expect, it } from "vitest";
import type { ChatMessage } from "../types";
import { buildRunHistory } from "./chatHistory";

const user = (id: string, text: string): ChatMessage => ({
  id, sender: "user", text, timestamp: "12:00",
});
const assistant = (id: string, text: string): ChatMessage => ({
  id, sender: "agent", text, timestamp: "12:01",
});
const tool = (id: string, text: string): ChatMessage => ({
  id, sender: "tool", toolName: "python", toolInput: "", toolOutput: text,
  toolStatus: "ok", text, timestamp: "12:02",
});

describe("buildRunHistory", () => {
  it("uses structured role/content turns and excludes tool cards", () => {
    expect(buildRunHistory([
      user("u1", "Find sources"),
      assistant("a1", "Here are sources"),
      tool("t1", "internal tool output"),
      user("u2", "Summarize them"),
    ])).toEqual([
      { role: "user", content: "Find sources" },
      { role: "assistant", content: "Here are sources" },
      { role: "user", content: "Summarize them" },
    ]);
  });

  it("preserves an unanswered user request so transcript questions can inspect it", () => {
    expect(buildRunHistory([
      user("u1", "Old request that was interrupted"),
    ])).toEqual([{ role: "user", content: "Old request that was interrupted" }]);
  });

  it("never includes simulated demo replies in real model context", () => {
    const history = buildRunHistory([
      user("u1", "hello"),
      assistant("a1", "FakeRunner completed: this is a simulated reply."),
      assistant("a2", "A genuine prior model answer."),
    ]);
    expect(history).toEqual([
      { role: "user", content: "hello" },
      { role: "assistant", content: "A genuine prior model answer." },
    ]);
  });

  it("limits history to the most recent ten turns by default", () => {
    const messages: ChatMessage[] = Array.from({ length: 14 }, (_, index) =>
      index % 2 === 0
        ? user("u" + index, "user " + index)
        : assistant("a" + index, "assistant " + index),
    );
    const history = buildRunHistory(messages);
    expect(history).toHaveLength(10);
    expect(history[0].content).toBe("user 4");
    expect(history[9].content).toBe("assistant 13");
  });

  it("returns no history for a non-positive limit", () => {
    expect(buildRunHistory([user("u1", "hello")], 0)).toEqual([]);
  });
});
