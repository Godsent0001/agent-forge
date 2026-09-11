import React, { useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export interface ChatMessage {
  id: string;
  sender: "user" | "agent";
  agentName?: string;
  content: string;
  timestamp: string;
}

interface ChatSectionProps {
  messages: ChatMessage[];
  running: boolean;
}

export function ChatSection({ messages, running }: ChatSectionProps) {
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, running]);

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-4">
      {messages.length === 0 ? (
        <div className="h-full flex flex-col items-center justify-center text-neutral-600 text-sm">
          <span>No chat history yet. Send a prompt to interact with your agent.</span>
        </div>
      ) : (
        messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex flex-col ${
              msg.sender === "user" ? "items-end" : "items-start"
            }`}
          >
            <div className="text-[10px] text-neutral-500 mb-1 px-1">
              {msg.sender === "user" ? "You" : msg.agentName || "Agent"} • {msg.timestamp}
            </div>
            <div
              className={`max-w-[85%] rounded-lg px-4 py-2.5 text-sm leading-relaxed ${
                msg.sender === "user"
                  ? "bg-accent-500 text-white"
                  : "bg-surface-800 border border-white/10 text-neutral-200"
              }`}
            >
              {msg.sender === "user" ? (
                <p className="whitespace-pre-wrap">{msg.content}</p>
              ) : (
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  className="prose prose-invert max-w-none text-sm break-words"
                >
                  {msg.content}
                </ReactMarkdown>
              )}
            </div>
          </div>
        ))
      )}
      {running && (
        <div className="flex items-center gap-2 text-xs text-neutral-500 italic">
          <span className="w-2 h-2 rounded-full bg-status-running animate-pulse" />
          Agent is thinking and executing tasks...
        </div>
      )}
      <div ref={messagesEndRef} />
    </div>
  );
}
