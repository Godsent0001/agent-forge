import { useEffect, useRef, useState } from "react";
import { ProjectAttachmentsPanel } from "./ProjectAttachmentsPanel";
import { api } from "../api/client";
import { useStore } from "../store/useStore";
import type { ChatMessage, ConversationMessageRecord, ConversationSummary } from "../types";
import { ArtifactViewer } from "./ArtifactViewer";
import { ApprovalDialog } from "./run/ApprovalDialog";
import { executionToolMessages } from "../utils/executionToolMessages";
import { Button } from "./ui/Button";
import { Icon } from "./ui/Icon";
import { LogoMark } from "./ui/LogoMark";
import { isSimulatedText } from "../utils/simulated";
import { buildRunHistory } from "../utils/chatHistory";
import { useExecutionStream } from "../hooks/useExecutionStream";

function fromStoredMessage(record: ConversationMessageRecord, agentName: string): ChatMessage {
  const timestamp = new Date(record.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  if (record.role === "user") {
    return { id: record.id, sender: "user", text: record.content, timestamp };
  }
  return {
    id: record.id,
    sender: "agent",
    agentName,
    text: record.content,
    timestamp,
    executionId: record.execution_id ?? undefined,
    messageRecordId: record.id,
    feedbackValue: record.feedback_value,
    feedbackNote: record.feedback_note,
  };
}

export function AgentChat({ onRunExecution }: { onRunExecution: (execId: string) => void }) {
  const selectedAgentId = useStore((s) => s.selectedAgentId);
  const agent = useStore((s) => s.agents.find((a) => a.id === s.selectedAgentId));
  const project = useStore((s) => s.project);
  const chatMessages = useStore((s) => s.chatMessages);
  const addChatMessage = useStore((s) => s.addChatMessage);
  const setChatMessages = useStore((s) => s.setChatMessages);
  const agentCount = useStore((s) => s.agents.length);
  const createAgent = useStore((s) => s.createAgent);
  const pendingTask = useStore((s) => s.pendingTask);
  const consumePendingTask = useStore((s) => s.consumePendingTask);

  const [promptInput, setPromptInput] = useState("");
  const [selectedAttachmentIds, setSelectedAttachmentIds] = useState<string[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [conversationLoading, setConversationLoading] = useState(false);
  const [conversationError, setConversationError] = useState<string | null>(null);
  const [activeExecutionId, setActiveExecutionId] = useState<string | null>(null);
  const [isCancelling, setIsCancelling] = useState(false);
  const [chatNotice, setChatNotice] = useState<string | null>(null);
  const [isCreatingAgent, setIsCreatingAgent] = useState(false);
  const [createAgentError, setCreateAgentError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const processedExecutionRef = useRef<string | null>(null);
  const conversationLoadRef = useRef(0);
  const activeExecutionAgentRef = useRef<{ id: string; name: string; conversationId: string } | null>(null);
  const { events: activeExecutionEvents } = useExecutionStream(activeExecutionId);

  const agentMessages = agent ? chatMessages[agent.id] || [] : [];
  const rawBudget = project?.settings?.budget;
  const budgetSettings = rawBudget && typeof rawBudget === "object" ? rawBudget as Record<string, unknown> : {};
  const maximumCost = typeof budgetSettings.max_cost_usd === "number"
    && Number.isFinite(budgetSettings.max_cost_usd)
    && budgetSettings.max_cost_usd > 0
    ? budgetSettings.max_cost_usd
    : null;
  const knownSpentCost = activeExecutionEvents
    .filter((event) => event.type === "span_ended" && event.kind === "llm_call")
    .reduce((sum, event) => {
      const value = event.data.cost_usd;
      return typeof value === "number" && Number.isFinite(value) && value >= 0 ? sum + value : sum;
    }, 0);
  const budgetWarning = isProcessing && maximumCost !== null && knownSpentCost >= maximumCost * 0.8;

  // Conversations are loaded from SQLite when the selected project/agent changes.
  // The Zustand copy is only a bounded rendering cache; the API remains authoritative.
  useEffect(() => {
    if (!agent || !project) {
      setConversations([]);
      setActiveConversationId(null);
      setConversationLoading(false);
      return;
    }
    let cancelled = false;
    setConversationLoading(true);
    setConversationError(null);
    setConversations([]);
    setActiveConversationId(null);
    setChatMessages(agent.id, []);
    setSelectedAttachmentIds([]);

    void (async () => {
      try {
        let items = await api.conversations.list(project.id, agent.id);
        if (items.length === 0) {
          const created = await api.conversations.create(project.id, agent.id);
          items = [created];
        }
        if (cancelled) return;
        setConversations(items);
        setActiveConversationId(items[0].id);
      } catch (cause) {
        if (cancelled) return;
        setConversationError(cause instanceof Error ? cause.message : "Could not load saved conversations.");
        setConversationLoading(false);
      }
    })();

    return () => {
      cancelled = true;
      conversationLoadRef.current += 1;
    };
  }, [agent?.id, project?.id, setChatMessages]);

  useEffect(() => {
    if (!agent || !project || !activeConversationId) return;
    const selectedConversation = conversations.find(
      (item) => item.id === activeConversationId && item.project_id === project.id && item.agent_id === agent.id,
    );
    if (!selectedConversation) return;

    const loadId = ++conversationLoadRef.current;
    setConversationLoading(true);
    setConversationError(null);
    setChatMessages(agent.id, []);
    void api.conversations.messages(activeConversationId)
      .then((records) => {
        if (conversationLoadRef.current !== loadId) return;
        setChatMessages(agent.id, records.map((record) => fromStoredMessage(record, agent.name)));
      })
      .catch((cause) => {
        if (conversationLoadRef.current !== loadId) return;
        setConversationError(cause instanceof Error ? cause.message : "Could not load this conversation.");
      })
      .finally(() => {
        if (conversationLoadRef.current === loadId) setConversationLoading(false);
      });

    return () => {
      if (conversationLoadRef.current === loadId) conversationLoadRef.current += 1;
    };
  }, [activeConversationId, conversations, agent?.id, agent?.name, project?.id, setChatMessages]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [agentMessages, isProcessing, agent?.id]);

  // Tasks queued elsewhere (Run workflow dialog) go through exactly the same path as typing in the composer,
  // so they appear in this agent's chat history and trace like any other message.
  useEffect(() => {
    if (!pendingTask || !agent || pendingTask.agentId !== agent.id || isProcessing || conversationLoading || !activeConversationId) return;
    const text = consumePendingTask();
    if (text) void sendTask(text);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingTask, agent?.id, isProcessing, conversationLoading, activeConversationId]);

  useEffect(() => {
    const targetAgent = activeExecutionAgentRef.current;
    if (!activeExecutionId || !targetAgent) return;
    const ended = activeExecutionEvents.some(
      (event) => event.execution_id === activeExecutionId && event.type === "execution_ended",
    );
    if (!ended || processedExecutionRef.current === activeExecutionId) return;

    processedExecutionRef.current = activeExecutionId;
    const executionId = activeExecutionId;
    const agentId = targetAgent.id;
    const agentName = targetAgent.name;
    void (async () => {
      try {
        const [completedExecution] = await Promise.all([api.executions.get(executionId)]);
        for (const toolMessage of executionToolMessages(activeExecutionEvents)) {
          addChatMessage(agentId, toolMessage);
        }

        const allowedStatuses = new Set(["completed", "error", "cancelled", "budget_exceeded", "interrupted"]);
        const status = allowedStatuses.has(completedExecution.status)
          ? completedExecution.status as "completed" | "error" | "cancelled" | "budget_exceeded" | "interrupted"
          : "error";
        const totals = completedExecution.totals ?? {};
        const numeric = (value: unknown) => typeof value === "number" && Number.isFinite(value) ? value : 0;
        const cost = typeof totals.cost_usd === "number" && Number.isFinite(totals.cost_usd)
          ? totals.cost_usd
          : null;
        const endTime = completedExecution.ended_at ? Date.parse(completedExecution.ended_at) : Number.NaN;
        const startTime = completedExecution.started_at ? Date.parse(completedExecution.started_at) : Number.NaN;
        const durationSeconds = Number.isFinite(startTime) && Number.isFinite(endTime)
          ? Math.max(0, (endTime - startTime) / 1000)
          : null;
        const fallback = status === "cancelled"
          ? "Stopped."
          : status === "budget_exceeded"
            ? "Stopped: budget reached."
            : status === "interrupted"
              ? "This run was interrupted."
              : completedExecution.error || "The run failed. Open the activity panel for details.";
        const agentMsg: ChatMessage = {
          id: Date.now().toString(),
          sender: "agent",
          agentName,
          text: completedExecution.final_output || (status === "completed" ? "Task processed with no explicit final output." : fallback),
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          executionId,
          executionStatus: status,
          usage: {
            inputTokens: numeric(totals.input_tokens),
            outputTokens: numeric(totals.output_tokens),
            costUsd: cost,
            durationSeconds,
          },
        };
        let persistedAgentMsg = agentMsg;
        try {
          const saved = await api.conversations.appendMessage(targetAgent.conversationId, {
            role: "assistant",
            content: agentMsg.text,
            execution_id: executionId,
          });
          persistedAgentMsg = {
            ...agentMsg,
            id: saved.id,
            timestamp: new Date(saved.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
            messageRecordId: saved.id,
            feedbackValue: saved.feedback_value,
            feedbackNote: saved.feedback_note,
          };
        } catch (cause) {
          setConversationError(cause instanceof Error
            ? `Run finished, but its answer could not be saved: ${cause.message}`
            : "Run finished, but its answer could not be saved.");
        }
        addChatMessage(agentId, persistedAgentMsg);
        if (status === "cancelled") setChatNotice("Run stopped.");
        else if (status === "budget_exceeded") setChatNotice("Run stopped because it reached a budget limit.");
        else if (status === "error" || status === "interrupted") {
          setChatNotice("Run did not complete. See the run log for details.");
        }
      } catch (error) {
        setChatError(error instanceof Error ? error.message : "Unable to load the completed run.");
      } finally {
        setIsProcessing(false);
        setIsCancelling(false);
        activeExecutionAgentRef.current = null;
        setActiveExecutionId(null);
      }
    })();
  }, [activeExecutionId, activeExecutionEvents, addChatMessage]);

  const activeSpanName = (() => {
    const open = new Map<string, string>();
    for (const event of [...activeExecutionEvents].sort((a, b) => a.seq - b.seq)) {
      if (event.type === "span_started" && event.span_id) {
        open.set(event.span_id, event.name ?? "Current step");
      } else if (event.type === "span_ended" && event.span_id) {
        open.delete(event.span_id);
      }
    }
    const names = [...open.values()];
    return names.length ? names[names.length - 1] : null;
  })();

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

  const handleNewConversation = async () => {
    if (!agent || !project || isProcessing) return;
    setConversationError(null);
    try {
      const created = await api.conversations.create(project.id, agent.id);
      setConversations((current) => [created, ...current.filter((item) => item.id !== created.id)]);
      setChatMessages(agent.id, []);
      setActiveConversationId(created.id);
    } catch (cause) {
      setConversationError(cause instanceof Error ? cause.message : "Could not create a conversation.");
    }
  };

  const handleClearChat = async () => {
    if (!agent || !project || isProcessing) return;
    if (!window.confirm(`Delete this conversation with ${agent.name}? This cannot be undone.`)) return;
    setConversationError(null);
    try {
      const created = await api.conversations.create(project.id, agent.id);
      if (activeConversationId) await api.conversations.remove(activeConversationId);
      setConversations((current) => [created, ...current.filter((item) => item.id !== activeConversationId && item.id !== created.id)]);
      setChatMessages(agent.id, []);
      setActiveConversationId(created.id);
    } catch (cause) {
      setConversationError(cause instanceof Error ? cause.message : "Could not delete this conversation.");
    }
  };

  const handleFeedback = async (messageId: string, value: -1 | 1) => {
    if (!agent) return;
    const message = agentMessages.find((item) => item.id === messageId);
    if (!message || message.sender !== "agent" || !message.messageRecordId) return;
    try {
      await api.conversations.feedback(message.messageRecordId, value, message.feedbackNote ?? undefined);
      const latest = useStore.getState().chatMessages[agent.id] || [];
      setChatMessages(agent.id, latest.map((item) =>
        item.id === messageId && item.sender === "agent" ? { ...item, feedbackValue: value } : item,
      ));
    } catch (cause) {
      setConversationError(cause instanceof Error ? cause.message : "Could not save message feedback.");
    }
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
    if (!activeConversationId || conversationLoading) {
      setChatError("Wait for the saved conversation to finish loading, then try again.");
      return;
    }
    if (!agent.model?.trim()) {
      setChatError("Pick a model in Config before starting a chat.");
      return;
    }

    const userText = rawText.trim();
    if (fromComposer) setPromptInput("");
    setChatError(null);
    setChatNotice(null);

    setIsProcessing(true);

    try {
      const history = buildRunHistory(agentMessages);
      const savedUser = await api.conversations.appendMessage(activeConversationId, {
        role: "user",
        content: userText,
      });
      const userMsg: ChatMessage = {
        id: savedUser.id,
        sender: "user",
        text: savedUser.content,
        timestamp: new Date(savedUser.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };
      addChatMessage(agent.id, userMsg);

      const execution = await api.executions.run(project.id, agent.id, userText, history, selectedAttachmentIds);
      setSelectedAttachmentIds([]);
      processedExecutionRef.current = null;
      activeExecutionAgentRef.current = { id: agent.id, name: agent.name, conversationId: activeConversationId };
      setActiveExecutionId(execution.id);
      onRunExecution(execution.id);
      // The stream owns completion now; do not poll the execution endpoint.
    } catch (e) {
      setChatError(e instanceof Error ? e.message : "Failed to start execution");
      setIsProcessing(false);
      setIsCancelling(false);
      activeExecutionAgentRef.current = null;
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
          <label className="sr-only" htmlFor="conversation-switcher">Saved conversations</label>
          <select
            id="conversation-switcher"
            aria-label="Saved conversations"
            value={activeConversationId ?? ""}
            onChange={(event) => setActiveConversationId(event.target.value || null)}
            disabled={conversationLoading || isProcessing || conversations.length === 0}
            className="max-w-40 rounded border border-studio-700 bg-studio-950 px-2 py-1.5 text-2xs text-studio-200 disabled:opacity-50"
          >
            {conversations.map((conversation) => (
              <option key={conversation.id} value={conversation.id}>{conversation.title || "New conversation"}</option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => void handleNewConversation()}
            disabled={isProcessing || conversationLoading}
            className="rounded border border-studio-700 px-2 py-1 text-2xs font-mono text-studio-300 transition-colors hover:bg-studio-800 disabled:opacity-50"
          >
            New chat
          </button>
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
                title="Delete this saved conversation and start a new one"
                disabled={isProcessing}
              >
                Delete
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
      {budgetWarning && (
        <div role="status" aria-live="polite" className="shrink-0 border-b border-amber-800 bg-amber-950/40 px-6 py-2 text-2xs leading-relaxed text-amber-200">
          <span className="font-semibold">Budget warning.</span> Known spend has reached at least 80% of the configured {new Intl.NumberFormat(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 4 }).format(maximumCost ?? 0)} limit. Unknown-priced calls may make the actual total higher.
        </div>
      )}
      {simulatedReply && (
        <div role="note" className="shrink-0 border-b border-amber-900/50 bg-amber-950/30 px-6 py-2 text-2xs leading-relaxed text-amber-300">
          <span className="font-semibold">Demo runner active.</span> Replies marked “Simulated” are placeholders from the built-in test runner, not real model output.
          Start the app with <span className="font-mono">npm run dev:live</span> to use real models.
        </div>
      )}

      <div role="log" aria-label={`Conversation with ${agent.name}`} aria-busy={conversationLoading} className="flex-1 overflow-y-auto p-6 space-y-4 min-h-0">
        {conversationLoading && (
          <p role="status" className="rounded border border-studio-800 bg-studio-900 px-3 py-2 text-2xs text-studio-400">
            Loading saved conversation…
          </p>
        )}
        {conversationError && (
          <p role="alert" className="rounded border border-amber-800 bg-amber-950/30 px-3 py-2 text-2xs text-amber-200">
            {conversationError}
          </p>
        )}
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
                    : msg.executionStatus === "error" || msg.executionStatus === "interrupted"
                      ? "bg-red-950/50 text-red-100 border-red-800/80 rounded-bl-md"
                      : msg.executionStatus === "budget_exceeded"
                        ? "bg-amber-950/50 text-amber-100 border-amber-800/80 rounded-bl-md"
                        : msg.executionStatus === "cancelled"
                          ? "bg-studio-850 text-studio-400 border-studio-700 rounded-bl-md"
                          : "bg-studio-900 text-studio-100 border-studio-750 rounded-bl-md"
                }`}
              >
                {msg.sender === "user" ? (
                  <p className="whitespace-pre-wrap text-sm leading-6">{msg.text}</p>
                ) : (
                  <ArtifactViewer content={msg.text} executionId={msg.executionId} />
                )}
              </div>
            )}

            {msg.sender === "agent" && msg.executionStatus && msg.executionStatus !== "completed" && (
              <p className={`mt-1 ml-1 text-2xs font-mono ${msg.executionStatus === "error" || msg.executionStatus === "interrupted" ? "text-red-300" : msg.executionStatus === "budget_exceeded" ? "text-amber-300" : "text-studio-500"}`}>
                {msg.executionStatus === "error" ? "Run failed" : msg.executionStatus === "interrupted" ? "Run interrupted" : msg.executionStatus === "budget_exceeded" ? "Budget reached" : "Stopped"}
              </p>
            )}
            {msg.sender === "agent" && msg.usage && (
              <p className="mt-1 ml-1 text-2xs font-mono text-studio-500">
                {msg.usage.inputTokens.toLocaleString()} in · {msg.usage.outputTokens.toLocaleString()} out · {msg.usage.costUsd === null ? "n/a" : "$" + msg.usage.costUsd.toFixed(3)} · {msg.usage.durationSeconds === null ? "n/a" : msg.usage.durationSeconds.toFixed(1) + " s"}
              </p>
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
            {msg.sender === "agent" && msg.messageRecordId && (
              <div role="group" aria-label="Rate this answer" className="mt-1 ml-1 flex items-center gap-2 text-2xs text-studio-500">
                <span>Helpful?</span>
                <button
                  type="button"
                  aria-label="Mark answer helpful"
                  aria-pressed={msg.feedbackValue === 1}
                  onClick={() => void handleFeedback(msg.id, 1)}
                  className={`rounded border px-2 py-1 transition-colors ${msg.feedbackValue === 1 ? "border-emerald-700 bg-emerald-950 text-emerald-200" : "border-studio-800 text-studio-400 hover:bg-studio-800"}`}
                >👍 Yes</button>
                <button
                  type="button"
                  aria-label="Mark answer not helpful"
                  aria-pressed={msg.feedbackValue === -1}
                  onClick={() => void handleFeedback(msg.id, -1)}
                  className={`rounded border px-2 py-1 transition-colors ${msg.feedbackValue === -1 ? "border-amber-700 bg-amber-950 text-amber-200" : "border-studio-800 text-studio-400 hover:bg-studio-800"}`}
                >👎 No</button>
              </div>
            )}
          </div>
        ))}

        {isProcessing && (
          <div role="status" aria-live="polite" className="flex items-center gap-2 text-studio-300 text-sm py-3 px-4 bg-studio-900 border border-studio-700 rounded-md w-fit font-mono">
            <span className="h-2 w-2 rounded-full bg-amber-300 animate-pulse" /> {activeSpanName ? `${activeSpanName} is running…` : `${agent.name} is running the task…`}
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

      <ApprovalDialog executionId={activeExecutionId} events={activeExecutionEvents} />

      {/* Multi-Line Prompt Bar */}
      <div className="p-4 border-t border-studio-800 bg-studio-900 shrink-0">
        <div className="max-w-4xl mx-auto mb-2">
          <ProjectAttachmentsPanel
            projectId={project.id}
            selectedIds={selectedAttachmentIds}
            onSelectedIdsChange={setSelectedAttachmentIds}
            disabled={isProcessing || conversationLoading}
          />
        </div>
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
