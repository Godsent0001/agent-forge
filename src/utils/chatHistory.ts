import type { ChatMessage } from "../types";
import { MAX_CHAT_HISTORY_TURNS } from "../config/chat";
import { isSimulatedText } from "./simulated";

export interface RunHistoryMessage {
  role: "user" | "assistant";
  content: string;
}

/**
 * Convert displayed chat to model history. UI-only tool cards and fake demo replies
 * are excluded so they cannot be mistaken for real model turns.
 */
export function buildRunHistory(
  messages: ChatMessage[],
  limit = MAX_CHAT_HISTORY_TURNS,
): RunHistoryMessage[] {
  if (!Number.isFinite(limit) || limit <= 0) return [];
  return messages
    .filter((message) => message.sender === "user" || message.sender === "agent")
    .filter((message) => message.sender !== "agent" || !isSimulatedText(message.text))
    .slice(-Math.floor(limit))
    .map((message) => ({
      role: message.sender === "user" ? "user" as const : "assistant" as const,
      content: message.text,
    }));
}
