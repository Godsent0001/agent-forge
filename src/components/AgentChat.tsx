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
      <div className="h-full flex items-center justify-center text-slate-500 text-sm bg-surface-950">
        Select an agent from the left hierarchy to start a conversation.
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
    <div className="h-full flex flex-col bg-surface-950">
      {/* Header bar showing active agent */}
      <div className="px-6 py-3 border-b border-slate-200 bg-surface-900 flex items-center justify-between shadow-sm">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-full bg-accent-100 text-accent-500 flex items-center justify-center font-bold text-lg border border-accent-300">
            🤖
          </div>
          <div>
            <h3 className="font-bold text-slate-800 text-base leading-tight">{agent.name}</h3>
            <p className="text-xs text-slate-500 truncate max-w-md">
              {agent.description || `${agent.provider} / ${agent.model}`}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {agent.child_agent_ids && agent.child_agent_ids.length > 0 && (
            <span className="text-xs px-2.5 py-1 rounded-full bg-slate-100 border border-slate-200 text-slate-600 font-medium">
              🔗 {agent.child_agent_ids.length} Child Agent(s)
            </span>
          )}
        </div>
      </div>

      {/* Chat Messages scroll area */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        {agentMessages.length === 0 && (
          <div className="h-full flex flex-col items-center justify-center text-center p-8 text-slate-400 space-y-2">
            <span className="text-4xl">💬</span>
            <p className="font-medium text-slate-600 text-sm">Start chatting with {agent.name}</p>
            <p className="text-xs max-w-sm">
              Type a prompt or task below. {agent.name} will execute its reasoning, tools, and child agents to respond.
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
                <p className="whitespace-pre-wrap text-sm leading-relaxed">{msg.text}</p>
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

      {/* Explicit Prompt Bar */}
      <div className="p-4 border-t border-slate-200 bg-surface-900">
        <div className="flex items-center gap-2 max-w-4xl mx-auto bg-white border border-slate-300 rounded-xl px-3 py-2 shadow-sm focus-within:ring-2 focus-within:ring-accent-500 focus-within:border-accent-500 transition-all">
          <input
            value={promptInput}
            onChange={(e) => setPromptInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSendMessage()}
            placeholder={`Prompt ${agent.name} with a task or message…`}
            disabled={isProcessing}
            className="flex-1 bg-transparent text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none"
          />
          <button
            onClick={handleSendMessage}
            disabled={!promptInput.trim() || isProcessing}
            className="bg-accent-500 hover:bg-accent-400 disabled:opacity-40 text-white text-xs font-bold px-4 py-2 rounded-lg transition-colors flex items-center gap-1 shrink-0"
          >
            <span>Send</span> ➔
          </button>
        </div>
      </div>
    </div>
  );
}
