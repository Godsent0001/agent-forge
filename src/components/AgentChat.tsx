import { useState } from "react";
import { api } from "../api/client";
import { useStore } from "../store/useStore";
import { ArtifactViewer } from "./ArtifactViewer";

interface ChatMessage {
  id: string;
  sender: "user" | "agent";
  agentName?: string;
  text: string;
  timestamp: string;
}

export function AgentChat({ onRunExecution }: { onRunExecution: (execId: string) => void }) {
  const selectedAgentId = useStore((s) => s.selectedAgentId);
  const agent = useStore((s) => s.agents.find((a) => a.id === s.selectedAgentId));
  const project = useStore((s) => s.project);

  const [messages, setMessages] = useState<Record<string, ChatMessage[]>>({});
  const [promptInput, setPromptInput] = useState("");
  const [isProcessing, setIsProcessing] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);

  if (!selectedAgentId || !agent || !project) {
    return (
      <div className="h-full flex items-center justify-center text-slate-500 text-sm bg-surface-950 p-6">
        <div className="text-center max-w-sm space-y-2">
          <span className="text-3xl block">💬</span>
          <p className="font-semibold text-slate-700">No Agent Selected</p>
          <p className="text-xs text-slate-500">
            Select an agent from the left explorer sidebar to start a interactive chat session.
          </p>
        </div>
      </div>
    );
  }

  const agentMessages = messages[agent.id] || [];

  const handleSendMessage = async () => {
    if (!promptInput.trim() || isProcessing) return;

    const userText = promptInput.trim();
    setPromptInput("");
    setChatError(null);

    const userMsg: ChatMessage = {
      id: Date.now().toString(),
      sender: "user",
      text: userText,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    setMessages((prev) => ({
      ...prev,
      [agent.id]: [...(prev[agent.id] || []), userMsg],
    }));

    setIsProcessing(true);

    try {
      const execution = await api.executions.run(project.id, agent.id, userText);
      onRunExecution(execution.id);

      // Poll for completion to append agent output into chat
      let completedExecution = execution;
      for (let i = 0; i < 60; i++) {
        await new Promise((r) => setTimeout(r, 1000));
        completedExecution = await api.executions.get(execution.id);
        if (completedExecution.status === "completed" || completedExecution.status === "error") {
          break;
        }
      }

      const agentMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        sender: "agent",
        agentName: agent.name,
        text: completedExecution.final_output || "Task processed with no explicit final output.",
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };

      setMessages((prev) => ({
        ...prev,
        [agent.id]: [...(prev[agent.id] || []), agentMsg],
      }));
    } catch (e) {
      setChatError(e instanceof Error ? e.message : "Failed to get agent response");
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div className="h-full flex flex-col bg-surface-950 min-w-0">
      {/* Header bar showing active agent */}
      <div className="px-6 py-3 border-b border-slate-200 bg-surface-900 flex items-center justify-between shadow-sm shrink-0 min-w-0">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-9 h-9 rounded-full bg-accent-100 text-accent-600 flex items-center justify-center font-bold text-lg border border-accent-300 shrink-0">
            🤖
          </div>
          <div className="min-w-0">
            <h3 className="font-bold text-slate-800 text-sm leading-tight truncate">{agent.name}</h3>
            <p className="text-xs text-slate-500 truncate">
              {agent.description || `${agent.provider} / ${agent.model}`}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {agent.child_agent_ids && agent.child_agent_ids.length > 0 && (
            <span className="text-[11px] px-2 py-0.5 rounded-full bg-slate-100 border border-slate-200 text-slate-600 font-medium shrink-0">
              🔗 {agent.child_agent_ids.length} Sub-agent(s)
            </span>
          )}
        </div>
      </div>

      {/* Chat Messages scroll area */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4 min-h-0">
        {agentMessages.length === 0 && (
          <div className="h-full flex flex-col items-center justify-center text-center p-8 text-slate-400 space-y-2">
            <span className="text-4xl">💬</span>
            <p className="font-semibold text-slate-700 text-sm">Start chatting with {agent.name}</p>
            <p className="text-xs text-slate-500 max-w-sm">
              Type a prompt or task below. {agent.name} will execute its reasoning, tools, and sub-agents to respond.
            </p>
          </div>
        )}

        {agentMessages.map((msg) => (
          <div
            key={msg.id}
            className={`flex flex-col ${msg.sender === "user" ? "items-end" : "items-start"}`}
          >
            <div className="flex items-center gap-2 mb-1 px-1">
              <span className="text-[11px] font-bold text-slate-500">
                {msg.sender === "user" ? "You" : msg.agentName || "Agent"}
              </span>
              <span className="text-[10px] text-slate-400">{msg.timestamp}</span>
            </div>

            <div
              className={`max-w-2xl rounded-2xl p-4 shadow-sm border ${
                msg.sender === "user"
                  ? "bg-accent-500 text-white border-accent-600 rounded-tr-none"
                  : "bg-white text-slate-800 border-slate-200 rounded-tl-none"
              }`}
            >
              {msg.sender === "user" ? (
                <p className="whitespace-pre-wrap text-xs sm:text-sm leading-relaxed">{msg.text}</p>
              ) : (
                <ArtifactViewer content={msg.text} />
              )}
            </div>
          </div>
        ))}

        {isProcessing && (
          <div className="flex items-center gap-2 text-slate-500 text-xs py-2 px-3 bg-white border border-slate-200 rounded-xl w-fit shadow-sm animate-pulse">
            <span>🤖</span> {agent.name} is reasoning and executing tools…
          </div>
        )}

        {chatError && (
          <div className="p-3 bg-red-50 border border-red-200 text-red-600 rounded-xl text-xs font-medium">
            Error: {chatError}
          </div>
        )}
      </div>

      {/* Multi-Line Prompt Bar */}
      <div className="p-4 border-t border-slate-200 bg-surface-900 shrink-0">
        <div className="max-w-4xl mx-auto flex items-end gap-2 bg-white border border-slate-300 rounded-xl p-2 shadow-sm focus-within:ring-2 focus-within:ring-accent-500 focus-within:border-accent-500 transition-all">
          <textarea
            value={promptInput}
            onChange={(e) => setPromptInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSendMessage();
              }
            }}
            rows={Math.min(5, Math.max(1, promptInput.split("\n").length))}
            placeholder={`Prompt ${agent.name}… (Shift+Enter for new line, Enter to send)`}
            disabled={isProcessing}
            className="flex-1 bg-transparent text-xs sm:text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none resize-none py-1.5 px-2 min-h-[38px] max-h-32 overflow-y-auto"
          />
          <button
            onClick={handleSendMessage}
            disabled={!promptInput.trim() || isProcessing}
            className="bg-accent-500 hover:bg-accent-400 active:scale-95 disabled:opacity-40 text-white text-xs font-bold px-4 py-2 rounded-lg transition-all flex items-center gap-1 shrink-0 h-9"
          >
            <span>Send</span> ➔
          </button>
        </div>
      </div>
    </div>
  );
}
