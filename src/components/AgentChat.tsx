import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { useStore } from "../store/useStore";
import type { ChatMessage } from "../types";
import { ArtifactViewer } from "./ArtifactViewer";
import { executionToolMessages } from "../utils/executionToolMessages";
import { Button } from "./ui/Button";
import { Icon } from "./ui/Icon";
import { LogoMark } from "./ui/LogoMark";
import { isSimulatedText } from "../utils/simulated";

export function AgentChat({ onRunExecution }: { onRunExecution: (execId: string) => void }) {
  const selectedAgentId = useStore((s) => s.selectedAgentId);
  const agent = useStore((s) => s.agents.find((a) => a.id === s.selectedAgentId));
  const project = useStore((s) => s.project);
  const chatMessages = useStore((s) => s.chatMessages);
  const addChatMessage = useStore((s) => s.addChatMessage);
  const agentCount = useStore((s) => s.agents.length);
  const createAgent = useStore((s) => s.createAgent);
  const clearChat = useStore((s) => s.clearChat);
  const pendingTask = useStore((s) => s.pendingTask);
  const consumePendingTask = useStore((s) => s.consumePendingTask);

  const [promptInput, setPromptInput] = useState("");
  const [isProcessing, setIsProcessing] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const [activeExecutionId, setActiveExecutionId] = useState<string | null>(null);
  const [isCancelling, setIsCancelling] = useState(false);
  const [chatNotice, setChatNotice] = useState<string | null>(null);
  const [isCreatingAgent, setIsCreatingAgent] = useState(false);
  const [createAgentError, setCreateAgentError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const agentMessages = agent ? chatMessages[agent.id] || [] : [];

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [agentMessages, isProcessing, agent?.id]);

  // Tasks queued elsewhere (Run workflow dialog) go through exactly the same path as typing in the composer,
  // so they appear in this agent's chat history and trace like any other message.
  useEffect(() => {
    if (!pendingTask || !agent || pendingTask.agentId !== agent.id || isProcessing) return;
    const text = consumePendingTask();
    if (text) void sendTask(text);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingTask, agent?.id, isProcessing]);

  const lastAgentMessage = [...agentMessages].reverse().find((m) => m.sender === "agent");
  const simulatedReply = !!lastAgentMessage && isSimulatedText(lastAgentMessage.text);

  const exportChat = () => {
    if (!agent) return;
    const lines = agentMessages.map((m) => {
      if (m.sender === "user") return `**You** (${m.timestamp})\n\n${m.text}`;
      if (m.sender === "tool") return `**Tool · ${m.toolName}** (${m.timestamp}, ${m.toolStatus})\n\n${m.toolInput ? `Input: ${m.toolInput}\n\n` : ""}${m.toolOutput}`;
      return `**${m.agentName || agent.name}** (${m.timestamp})\n\n${m.text}`;
    });
    const markdown = `# Chat with ${agent.name}\n\n${lines.join("\n\n---\n\n")}\n`;
    const url = URL.createObjectURL(new Blob([markdown], { type: "text/markdown" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `agentforge-chat-${agent.name.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}.md`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const handleClearChat = () => {
    if (!agent) return;
    if (window.confirm(`Clear the saved conversation with ${agent.name}? This cannot be undone.`)) clearChat(agent.id);
  };

  const handleCreateFirstAgent = async () => {
    if (isCreatingAgent) return;
    setIsCreatingAgent(true);
    setCreateAgentError(null);
    try {
      await createAgent("Assistant");
    } catch (e) {
      setCreateAgentError(e instanceof Error ? e.message : "Could not create the agent.");
    } finally {
      setIsCreatingAgent(false);
    }
  };

  if (!selectedAgentId || !agent || !project) {
    const hasAgents = agentCount > 0;
    return (
      <div className="h-full w-full flex-1 flex items-center justify-center bg-studio-950 p-6 select-none">
        <div className="text-center max-w-sm">
          <div className="mx-auto mb-4 flex h-11 w-11 items-center justify-center rounded-xl border border-studio-700 bg-studio-900 text-accent-400">
            <Icon name={hasAgents ? "chat" : "agents"} size={20} />
          </div>
          <p className="font-semibold text-studio-100 text-base">
            {hasAgents ? "Pick an agent to chat with" : "Create your first agent"}
          </p>
          <p className="mt-2 text-sm leading-6 text-studio-400">
            {hasAgents
              ? "Choose an agent from the explorer on the left to start a conversation."
              : "Agents are the building blocks of a workflow. Start with one, then give it tools or let it delegate to other agents."}
          </p>
          {!hasAgents && (
            <>
              <Button
                className="mt-5"
                variant="primary"
                size="md"
                icon={<Icon name="plus" size={14} />}
                onClick={handleCreateFirstAgent}
                disabled={isCreatingAgent}
              >
                {isCreatingAgent ? "Creating…" : "Create agent"}
              </Button>
              {createAgentError && (
                <p role="alert" className="mt-3 text-xs text-red-300">
                  {createAgentError}
                </p>
              )}
            </>
          )}
        </div>
      </div>
    );
  }

  const handleSendMessage = () => void sendTask(promptInput, true);

  const sendTask = async (rawText: string, fromComposer = false) => {
    if (!rawText.trim() || isProcessing || !agent || !project) return;
    if (!agent.model?.trim()) {
      setChatError("Pick a model in Config before starting a chat.");
      return;
    }

    const userText = rawText.trim();
    if (fromComposer) setPromptInput("");
    setChatError(null);
    setChatNotice(null);

    const userMsg: ChatMessage = {
      id: Date.now().toString(),
      sender: "user",
      text: userText,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };
    addChatMessage(agent.id, userMsg);
    setIsProcessing(true);

    try {
      // C-1 defines history as structured user/assistant turns. Tool spans stay in the
      // execution log, and demo placeholders must never become real-model context.
      const history = agentMessages
        .filter((message) => message.sender === "user" || message.sender === "agent")
        .filter((message) => message.sender !== "agent" || !isSimulatedText(message.text))
        .slice(-20)
        .map((message) => ({
          role: message.sender === "user" ? "user" as const : "assistant" as const,
          content: message.text,
        }));

      const execution = await api.executions.run(project.id, agent.id, userText, history);
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
        setChatNotice("Run stopped before it finished.");
        return;
      }

      if (completedExecution.status !== "completed") {
        throw new Error(
          completedExecution.error ||
            (completedExecution.status === "budget_exceeded"
              ? "The run hit its budget limit before finishing."
              : "The run did not complete. Open the activity panel to see which step failed."),
        );
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
        executionId: execution.id,
      };
      addChatMessage(agent.id, agentMsg);
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
    <div className="h-full w-full flex-1 flex flex-col bg-studio-950 min-w-0 text-studio-100">
      {/* Header bar showing active agent */}
      <div className="px-6 py-4 border-b border-studio-800 bg-studio-900/95 flex items-center justify-between shadow-studio shrink-0 min-w-0 select-none">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-8 h-8 rounded-md border border-studio-600 bg-studio-800 text-accent-400 flex items-center justify-center shrink-0">
            <Icon name="agents" size={16} />
          </div>
          <div className="min-w-0">
            <h3 className="font-semibold text-studio-100 text-sm leading-tight truncate">{agent.name}</h3>
            <p className="text-2xs font-mono text-studio-400 truncate mt-0.5">
              {agent.provider} / {agent.model || "No model selected"}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {agentMessages.length > 0 && (
            <>
              <button
                type="button"
                onClick={exportChat}
                className="rounded px-2 py-1 text-2xs font-mono text-studio-400 transition-colors hover:bg-studio-800 hover:text-studio-100"
                title="Download this conversation as Markdown"
              >
                Export
              </button>
              <button
                type="button"
                onClick={handleClearChat}
                className="rounded px-2 py-1 text-2xs font-mono text-studio-400 transition-colors hover:bg-studio-800 hover:text-red-300"
                title="Delete the saved conversation"
              >
                Clear
              </button>
            </>
          )}
          {agent.child_agent_ids && agent.child_agent_ids.length > 0 && (
            <span className="text-2xs font-mono px-2 py-0.5 rounded border border-studio-700 bg-studio-850 text-studio-300 font-medium shrink-0">
              {agent.child_agent_ids.length} delegated
            </span>
          )}
          {agent.tool_ids && agent.tool_ids.length > 0 && (
            <span className="text-2xs font-mono px-2 py-0.5 rounded border border-studio-700 bg-studio-850 text-studio-300 font-medium shrink-0">
              {agent.tool_ids.length} tools
            </span>
          )}
        </div>
      </div>

      {/* Chat Messages scroll area */}
      {simulatedReply && (
        <div role="note" className="shrink-0 border-b border-amber-900/50 bg-amber-950/30 px-6 py-2 text-2xs leading-relaxed text-amber-300">
          <span className="font-semibold">Demo runner active.</span> Replies marked “Simulated” are placeholders from the built-in test runner, not real model output.
          Start the app with <span className="font-mono">npm run dev:live</span> to use real models.
        </div>
      )}

      <div role="log" aria-label={`Conversation with ${agent.name}`} className="flex-1 overflow-y-auto p-6 space-y-4 min-h-0">
        {agentMessages.length === 0 && (
          <div className="h-full flex flex-col items-center justify-center text-center px-6 py-10 text-studio-400 select-none">
            <LogoMark size={48} className="mb-5 drop-shadow-lg" />
            <p className="font-semibold text-studio-100 text-base">What are we working on?</p>
            <p className="mt-2 max-w-md text-sm text-studio-400 leading-6">
              Give {agent.name} a task. Its configured model, tools, and delegated agents will be used as needed.
            </p>
            <div className="mt-6 flex max-w-xl flex-wrap justify-center gap-2">
              {[
                { label: "Plan a feature", prompt: "Help me plan an implementation. Ask any essential clarifying questions, then give me a concise step-by-step plan." },
                { label: "Investigate a failure", prompt: "Help me investigate a bug. Start by identifying the information you need, then work through likely causes systematically." },
                { label: "Review a design", prompt: "Review my proposed approach for correctness, edge cases, and simpler alternatives. Ask me to share the approach if I have not provided it." },
              ].map((starter) => (
                <button
                  key={starter.label}
                  type="button"
                  onClick={() => setPromptInput(starter.prompt)}
                  className="rounded-md border border-studio-700 bg-studio-900 px-3 py-2 text-xs text-studio-300 transition-colors hover:border-studio-500 hover:bg-studio-800 hover:text-studio-100"
                >
                  {starter.label}
                </button>
              ))}
            </div>
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
              {msg.sender === "agent" && isSimulatedText(msg.text) && (
                <span className="rounded border border-amber-800/70 bg-amber-950/40 px-1.5 text-[10px] font-mono uppercase text-amber-300">Simulated</span>
              )}
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
                className={`max-w-3xl rounded-2xl px-4 py-3 shadow-studio border ${
                  msg.sender === "user"
                    ? "bg-accent-600 text-white border-accent-500/80 rounded-br-md"
                    : "bg-studio-900 text-studio-100 border-studio-750 rounded-bl-md"
                }`}
              >
                {msg.sender === "user" ? (
                  <p className="whitespace-pre-wrap text-sm leading-6">{msg.text}</p>
                ) : (
                  <ArtifactViewer content={msg.text} />
                )}
              </div>
            )}

            {msg.sender === "agent" && msg.executionId && (
              <button
                type="button"
                onClick={() => onRunExecution(msg.executionId as string)}
                className="mt-1 ml-1 rounded px-1.5 py-0.5 text-2xs font-mono text-studio-500 transition-colors hover:bg-studio-800 hover:text-accent-400"
              >
                View run log
              </button>
            )}
          </div>
        ))}

        {isProcessing && (
          <div role="status" aria-live="polite" className="flex items-center gap-2 text-studio-300 text-sm py-3 px-4 bg-studio-900 border border-studio-700 rounded-md w-fit font-mono">
            <span className="h-2 w-2 rounded-full bg-amber-300 animate-pulse" /> {agent.name} is running the task…
          </div>
        )}

        {chatNotice && (
          <div role="status" className="rounded-md border border-studio-700 bg-studio-900 px-4 py-3 text-sm text-studio-300">
            {chatNotice}
          </div>
        )}

        {chatError && (
          <div role="alert" className="rounded-md border border-red-800 bg-red-950/60 px-4 py-3 text-sm text-red-300">
            <span className="font-semibold">Something went wrong.</span> {chatError}
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Multi-Line Prompt Bar */}
      <div className="p-4 border-t border-studio-800 bg-studio-900 shrink-0">
        <div className="max-w-4xl mx-auto flex items-end gap-3 bg-studio-950 border border-studio-700 rounded-xl p-2.5 shadow-studio focus-within:border-accent-500/70 transition-colors">
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
            aria-label={`Task for ${agent.name}`}
            placeholder={`Message ${agent.name}…  (Enter to send, Shift+Enter for a new line)`}
            disabled={isProcessing}
            className="flex-1 bg-transparent text-sm text-studio-100 placeholder:text-studio-500 focus:outline-none resize-none py-2 px-3 min-h-[40px] max-h-40 overflow-y-auto"
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
              <span>Send</span> <Icon name="chevron-right" size={14} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
