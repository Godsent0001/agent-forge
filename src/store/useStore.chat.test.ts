import { beforeEach, describe, expect, it } from "vitest";
import { CHAT_STORAGE_KEY, useStore } from "./useStore";
import type { ChatMessage } from "../types";

const user = (id: string, text: string): ChatMessage => ({ id, sender: "user", text, timestamp: "10:00" });

describe("chat history persistence", () => {
  beforeEach(() => {
    localStorage.clear();
    useStore.setState({ chatMessages: {}, pendingTask: null });
  });

  it("saves messages to local storage so they survive a restart", () => {
    useStore.getState().addChatMessage("a1", user("m1", "hello"));
    const saved = JSON.parse(localStorage.getItem(CHAT_STORAGE_KEY) as string);
    expect(saved.state.chatMessages.a1).toHaveLength(1);
    expect(saved.state.chatMessages.a1[0].text).toBe("hello");
  });

  it("persists only conversations, never the queued task or backend data", () => {
    useStore.getState().queueTask("a1", "do a thing");
    useStore.getState().addChatMessage("a1", user("m1", "hi"));
    const saved = JSON.parse(localStorage.getItem(CHAT_STORAGE_KEY) as string);
    expect(Object.keys(saved.state)).toEqual(["chatMessages"]);
  });

  it("clears one agent's conversation without touching others", () => {
    const { addChatMessage, clearChat } = useStore.getState();
    addChatMessage("a1", user("m1", "one"));
    addChatMessage("a2", user("m2", "two"));
    clearChat("a1");
    expect(useStore.getState().chatMessages.a1).toBeUndefined();
    expect(useStore.getState().chatMessages.a2).toHaveLength(1);
    const saved = JSON.parse(localStorage.getItem(CHAT_STORAGE_KEY) as string);
    expect(saved.state.chatMessages.a1).toBeUndefined();
  });

  it("caps what is stored per agent", () => {
    const { addChatMessage } = useStore.getState();
    for (let i = 0; i < 320; i++) addChatMessage("a1", user(`m${i}`, `msg ${i}`));
    const saved = JSON.parse(localStorage.getItem(CHAT_STORAGE_KEY) as string);
    expect(saved.state.chatMessages.a1).toHaveLength(300);
    expect(saved.state.chatMessages.a1.at(-1).text).toBe("msg 319");
    expect(useStore.getState().chatMessages.a1).toHaveLength(320); // in-memory view is not truncated mid-session
  });

  it("hands a queued task to the chat exactly once", () => {
    const { queueTask, consumePendingTask } = useStore.getState();
    queueTask("a1", "Draft the teaser");
    expect(useStore.getState().pendingTask).toEqual({ agentId: "a1", text: "Draft the teaser" });
    expect(consumePendingTask()).toBe("Draft the teaser");
    expect(consumePendingTask()).toBeNull();
  });
});
