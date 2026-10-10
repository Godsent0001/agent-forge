import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { useStore } from "../store/useStore";
import type { ChatMessage } from "../types";
import { ArtifactViewer } from "./ArtifactViewer";
import { executionToolMessages } from "../utils/executionToolMessages";

export function AgentChat({ onRunExecution }: { onRunExecution: (execId: string) => void }) {
  const selectedAgentId = useStore((s) => s.selectedAgentId);
  const agent = useStore((s) => s.agents.find((a) => a.id === s.selectedAgentId));
  const project = useStore((s) => s.project);
  const chatMessages = useStore((s) => s.chatMessages);
  const addChatMessage = useStore((s) => s.addChatMessage);

  const [promptInput, setPromptInput] = useState("");
  const [isProcessing, setIsProcessing] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const [activeExecutionId, setActiveExecutionId] = useState<string | null>(null);
  const [isCancelling, setIsCancelling] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const agentMessages = agent ? chatMessages[agent.id] || [] : [];

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [agentMessages, isProcessing, agent?.id]);

  if (!selectedAgentId || !agent || !project) {
    return (
      <div className="h-full flex items-center justify-center text-studio-400 text-sm bg-studio-950 p-6 select-none">
        <div className="text-center max-w-sm space-y-2">
          <span className="text-3xl block">💬</span>
          <p className="font-semibold text-studio-200">No Agent Selected</p>
          <p className="text-xs text-studio-500">
            Select an agent from the left explorer sidebar or canvas to start an interactive testing session.
          </p>
        </div>
      </div>
    );
  }

  const handleSendMessage = async () => {
    if (!promptInput.trim() || isProcessing || !agent || !project) return;
    if (!agent.model?.trim()) {
      setChatError("Pick a model in Config before starting a chat.");
      return;
    }

    const userText = promptInput.trim();
    setPromptInput("");
    setChatError(null);

    const userMsg: ChatMessage = {
      id: Date.now().toString(),
      sender: "user",
      text: userText,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };
    addChatMessage(agent.id, userMsg);
    setIsProcessing(true);

    try {
      const historyTurns = agentMessages
        .slice(-10)
        .map((m) => {
          if (m.sender === "user") return `User: ${m.text}`;
          if (m.sender === "tool") return `Tool (${m.toolName}) result: ${m.toolOutput}`;
          return `Assistant: ${m.text}`;
        })
        .join("\n\n");

      const fullTask = historyTurns
        ? `[RECENT CONVERSATION HISTORY]\n${historyTurns}\n\n[CURRENT USER INSTRUCTION]\n${userText}`
        : userText;

      const execution = await api.executions.run(project.id, agent.id, fullTask);
      setActiveExecutionId(execution.id);
      onRunExecution(execution.id);

      let completedExecution = await api.executions.get(execution.id);
      for (let i = 0; i < 300; i++) {
        await new Promise((r) => setTimeout(r, 800));
        completedExecution = await api.executions.get(execution.id);
        if (["completed", "error", "cancelled", "budget_exceeded", "interrupted"].includes(completedExecution.status)) {
          break;
        }
      }

      const executionEvents = await api.executions.getEvents(execution.id);
      const toolMessages = executionToolMessages(executionEvents);
      for (const toolMessage of toolMessages) {
        addChatMessage(agent.id, toolMessage);
      }

      if (completedExecution.status === "cancelled") {
        setChatError("Execution cancelled.");
        return;
      }

      if (completedExecution.status !== "completed") {
        throw new Error("Execution did not complete. Check the execution tree for details.");
      }

      const agentMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        sender: "agent",
        agentName: agent.name,
        text:
          completedExecution.final_output ||
          completedExecution.error ||
          "Task processed with no explicit final output.",
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };
      addChatMessage(agent.id, agentMsg);
      useStore.getState().updateAgent(agent.id, {});
    } catch (e) {
      setChatError(e instanceof Error ? e.message : "Failed to get agent response");
    } finally {
      setIsProcessing(false);
      setIsCancelling(false);
      setActiveExecutionId(null);
    }
  };

  const handleCancelExecution = async () => {
    if (!activeExecutionId || isCancelling) return;
    setIsCancelling(true);
    setChatError(null);
    try {
      await api.executions.cancel(activeExecutionId);
    } catch (e) {
      setIsCancelling(false);
      setChatError(e instanceof Error ? e.message : "Failed to stop execution");
    }
  };

  return (
    <div className="h-full flex flex-col bg-studio-950 min-w-0 text-studio-100">
      {/* Header bar showing active agent */}
      <div className="px-6 py-3 border-b border-studio-800 bg-studio-900 flex items-center justify-between shadow-studio shrink-0 min-w-0 select-none">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-8 h-8 rounded-md bg-accent-950 text-accent-400 flex items-center justify-center font-bold text-base border border-accent-800/80 shrink-0">
            🤖
          </div>
          <div className="min-w-0">
            <h3 className="font-semibold text-studio-100 text-sm leading-tight truncate">{agent.name}</h3>
            <p className="text-2xs font-mono text-studio-400 truncate mt-0.5">
              {agent.provider} / {agent.model || "No model selected"}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {agent.child_agent_ids && agent.child_agent_ids.length > 0 && (
            <span className="text-2xs font-mono px-2 py-0.5 rounded bg-blue-950/60 border border-blue-800 text-blue-300 font-medium shrink-0">
              🔗 {agent.child_agent_ids.length} Sub-agent(s)
            </span>
          )}
          {agent.tool_ids && agent.tool_ids.length > 0 && (
            <span className="text-2xs font-mono px-2 py-0.5 rounded bg-emerald-950/60 border border-emerald-800 text-emerald-300 font-medium shrink-0">
              🛠 {agent.tool_ids.length} Tools
            </span>
          )}
        </div>
      </div>

      {/* Chat Messages scroll area */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4 min-h-0">
        {agentMessages.length === 0 && (
          <div className="h-full flex flex-col items-center justify-center text-center p-8 text-studio-400 space-y-2 select-none">
            <span className="text-3xl">💬</span>
            <p className="font-semibold text-studio-200 text-sm">Interactive Test Console</p>
            <p className="text-xs text-studio-500 max-w-sm">
              Type a task or test prompt below. {agent.name} will execute its reasoning, invoke attached tools, and output trace logs.
            </p>
          </div>
        )}

        {agentMessages.map((msg) => (
          <div
            key={msg.id}
            className={`flex flex-col ${msg.sender === "user" ? "items-end" : "items-start"}`}
          >
            <div className="flex items-center gap-2 mb-1 px-1">
              <span className="text-2xs font-mono font-semibold text-studio-400">
                {msg.sender === "user"
                  ? "You"
                  : msg.sender === "tool"
                  ? `Tool · ${msg.toolName}`
                  : msg.agentName || "Agent"}
              </span>
              <span className="text-2xs font-mono text-studio-600">{msg.timestamp}</span>
            </div>

            {msg.sender === "tool" ? (
              <div className="max-w-2xl w-full rounded-md border border-emerald-800/60 bg-emerald-950/30 p-3 shadow-studio">
                <div className="flex items-center justify-between gap-3 mb-2">
                  <span className="text-2xs font-mono font-semibold text-emerald-300">Tool Execution Result</span>
                  <span
                    className={`text-2xs font-mono font-semibold uppercase px-1.5 py-0.2 rounded border ${
                      msg.toolStatus === "ok"
                        ? "text-emerald-300 border-emerald-700 bg-emerald-950"
                        : msg.toolStatus === "cancelled"
                        ? "text-amber-300 border-amber-700 bg-amber-950"
                        : "text-red-300 border-red-700 bg-red-950"
                    }`}
                  >
                    {msg.toolStatus}
                  </span>
                </div>
                {msg.toolInput && (
                  <p className="text-2xs text-studio-400 mb-2 break-words font-mono">
                    <span className="text-studio-500">Input args:</span> {msg.toolInput}
                  </p>
                )}
                <pre className="whitespace-pre-wrap break-words text-xs text-emerald-200/90 font-mono leading-relaxed bg-studio-950/60 p-2 rounded border border-studio-800">
                  {msg.toolOutput}
                </pre>
              </div>
            ) : (
              <div
                className={`max-w-2xl rounded-lg p-3.5 shadow-studio border ${
                  msg.sender === "user"
                    ? "bg-accent-600 text-white border-accent-500/80 rounded-tr-none"
                    : "bg-studio-900 text-studio-100 border-studio-750 rounded-tl-none"
                }`}
              >
                {msg.sender === "user" ? (
                  <p className="whitespace-pre-wrap text-xs sm:text-sm leading-relaxed">{msg.text}</p>
                ) : (
                  <ArtifactViewer content={msg.text} />
                )}
              </div>
            )}
          </div>
        ))}

        {isProcessing && (
          <div className="flex items-center gap-2 text-accent-400 text-xs py-2 px-3 bg-studio-900 border border-studio-700 rounded-md w-fit shadow-studio animate-pulse font-mono">
            <span>⚙️</span> {agent.name} is reasoning and executing tools…
          </div>
        )}

        {chatError && (
          <div className="p-3 bg-red-950/60 border border-red-800 text-red-300 rounded-md text-xs font-medium">
            Error: {chatError}
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Multi-Line Prompt Bar */}
      <div className="p-4 border-t border-studio-800 bg-studio-900 shrink-0">
        <div className="max-w-4xl mx-auto flex items-end gap-2 bg-studio-800 border border-studio-700 rounded-md p-2 shadow-studio focus-within:border-accent-500 transition-colors">
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
            className="flex-1 bg-transparent text-xs sm:text-sm text-studio-100 placeholder:text-studio-500 focus:outline-none resize-none py-1.5 px-2 min-h-[38px] max-h-32 overflow-y-auto"
          />
          {isProcessing ? (
            <button
              onClick={handleCancelExecution}
              disabled={!activeExecutionId || isCancelling}
              className="bg-red-900 hover:bg-red-800 active:bg-red-950 disabled:opacity-40 text-red-200 text-xs font-semibold px-4 py-2 rounded transition-colors flex items-center gap-1 shrink-0 h-9 border border-red-700 cursor-pointer"
              aria-label="Stop execution"
            >
              <span>{isCancelling ? "Stopping…" : "Stop"}</span>
            </button>
          ) : (
            <button
              onClick={handleSendMessage}
              disabled={!promptInput.trim()}
              className="bg-accent-600 hover:bg-accent-500 active:bg-accent-700 disabled:opacity-40 text-white text-xs font-semibold px-4 py-2 rounded transition-colors flex items-center gap-1 shrink-0 h-9 shadow-studio cursor-pointer"
            >
              <span>Run Test</span> ➔
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
