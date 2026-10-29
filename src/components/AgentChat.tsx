import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { ProjectAttachmentsPanel } from "./ProjectAttachmentsPanel";
import { api } from "../api/client";
import { useStore } from "../store/useStore";
import type { ChatMessage, ConversationMessageRecord, ConversationSummary } from "../types";
import { ArtifactViewer } from "./ArtifactViewer";
import { ApprovalDialog } from "./run/ApprovalDialog";
import { Button } from "./ui/Button";
import { Icon } from "./ui/Icon";
import { LogoMark } from "./ui/LogoMark";
import { isSimulatedText } from "../utils/simulated";
import { buildRunHistory } from "../utils/chatHistory";
import { useExecutionStream } from "../hooks/useExecutionStream";

const TERMINAL_RUN_STATUSES = ["completed", "error", "cancelled", "budget_exceeded", "interrupted"] as const;
type TerminalRunStatus = (typeof TERMINAL_RUN_STATUSES)[number];

function storedRunStatus(status: string | null | undefined): TerminalRunStatus | undefined {
  return TERMINAL_RUN_STATUSES.find((value) => value === status);
}

function describeActiveStep(event: import("../types").ExecutionEvent): string {
  const rawName = (event.name || "Current step").replace(/[_-]+/g, " ").trim();
  let args: Record<string, unknown> = {};
  const rawArgs = event.data?.args;
  if (typeof rawArgs === "string") {
    try {
      const parsed: unknown = JSON.parse(rawArgs);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) args = parsed as Record<string, unknown>;
    } catch { /* Tool arguments may be omitted or summarized. */ }
  } else if (rawArgs && typeof rawArgs === "object" && !Array.isArray(rawArgs)) {
    args = rawArgs as Record<string, unknown>;
  }
  const operation = [args.operation, args.action].find((value) => typeof value === "string") as string | undefined;
  const filePath = [args.path, args.file_path].find((value) => typeof value === "string") as string | undefined;
  const detail = [args.query, args.url, filePath, operation].find((value) => typeof value === "string" && value.trim());
  const suffix = typeof detail === "string" ? ` · ${detail.length > 64 ? detail.slice(0, 61) + "…" : detail}` : "";
  const name = rawName.toLowerCase();
  if (name.includes("web search")) return `Searching the web${suffix}`;
  if (name === "browser") return `Inspecting webpage${suffix}`;
  if (name === "file" || name.includes("workspace files")) {
    const target = filePath ? filePath.split(/[\\/]/).pop() : "";
    if (operation === "read") return `Inspecting file ${target || "contents"} for the current task`;
    if (operation === "write") return `Writing ${target || "a project file"}`;
    if (operation === "list") return "Checking project files";
    if (operation === "mkdir") return `Creating project directory ${target || ""}`.trim();
    if (operation === "delete") return `Removing project file ${target || ""}`.trim();
    return `Working with project files${suffix}`;
  }
  if (name === "python") return operation === "install" ? "Installing Python dependencies" : operation === "ensure" ? "Preparing the Python environment" : operation === "list" ? "Checking installed Python packages" : "Running Python work";
  if (name.includes("knowledge ingest")) return `Indexing document for retrieval${suffix}`;
  if (name.includes("knowledge search")) return `Searching indexed project knowledge${suffix}`;
  if (name.includes("shell") || name.includes("cmd")) return "Running a shell command";
  return `Working with ${rawName}${suffix}`;
}

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
    executionStatus: storedRunStatus(record.execution_status),
    messageRecordId: record.id,
    feedbackValue: record.feedback_value,
    feedbackNote: record.feedback_note,
  };
}

export function AgentChat({ onRunExecution }: { onRunExecution: (execId: string) => void }) {
  const selectedAgentId = useStore((s) => s.selectedAgentId);
  const agent = useStore((s) => s.agents.find((a) => a.id === s.selectedAgentId));
  const project = useStore((s) => s.project);
  const setActiveConversationForScope = useStore((s) => s.setActiveConversationForScope);
  const activeExecutionByScope = useStore((s) => s.activeExecutionByScope);
  const setActiveExecutionForScope = useStore((s) => s.setActiveExecutionForScope);
  const clearActiveExecutionForScope = useStore((s) => s.clearActiveExecutionForScope);
  const chatMessages = useStore((s) => s.chatMessages);
  const addChatMessage = useStore((s) => s.addChatMessage);
  const setChatMessages = useStore((s) => s.setChatMessages);
  const agentCount = useStore((s) => s.agents.length);
  const createAgent = useStore((s) => s.createAgent);
  const pendingTask = useStore((s) => s.pendingTask);
  const consumePendingTask = useStore((s) => s.consumePendingTask);

  const [promptInput, setPromptInput] = useState("");
  const [editingMessageId, setEditingMessageId] = useState<string | null>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const [selectedAttachmentIds, setSelectedAttachmentIds] = useState<string[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [conversationLoading, setConversationLoading] = useState(false);
  const [conversationReloadKey, setConversationReloadKey] = useState(0);
  const [conversationListReloadKey, setConversationListReloadKey] = useState(0);
  const [readyConversationIds, setReadyConversationIds] = useState<Set<string>>(new Set());
  const [newConversationIds, setNewConversationIds] = useState<Set<string>>(new Set());
  const [conversationError, setConversationError] = useState<string | null>(null);
  const [activeExecutionId, setActiveExecutionId] = useState<string | null>(null);
  const [isCancelling, setIsCancelling] = useState(false);
  const [chatNotice, setChatNotice] = useState<string | null>(null);
  const [isCreatingAgent, setIsCreatingAgent] = useState(false);
  const [createAgentError, setCreateAgentError] = useState<string | null>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const processedExecutionRef = useRef<string | null>(null);
  const conversationLoadRef = useRef(0);
  const conversationNavigationRef = useRef(0);
  const activeExecutionAgentRef = useRef<{ id: string; name: string; conversationId: string } | null>(null);
  const { events: activeExecutionEvents } = useExecutionStream(activeExecutionId);

  useEffect(() => {
    if (!agent || !project) return;
    const scope = project.id + ":" + agent.id;
    const saved = activeExecutionByScope[scope];
    if (!saved || activeExecutionId) return;

    let ignore = false;
    void (async () => {
      try {
        const statusRes = await api.executions.get(saved.executionId);
        if (ignore) return;
        if (TERMINAL_RUN_STATUSES.includes(statusRes.status as TerminalRunStatus)) {
          clearActiveExecutionForScope(scope, saved.executionId);
          setIsProcessing(false);
          return;
        }
        activeExecutionAgentRef.current = { id: saved.agentId, name: saved.agentName, conversationId: saved.conversationId };
        setActiveExecutionId(saved.executionId);
        setIsProcessing(true);
      } catch {
        if (!ignore) {
          clearActiveExecutionForScope(scope, saved.executionId);
          setIsProcessing(false);
        }
      }
    })();

    return () => {
      ignore = true;
    };
  }, [agent?.id, project?.id, activeExecutionByScope, activeExecutionId, clearActiveExecutionForScope]);

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
    const navigationId = conversationNavigationRef.current;
    setConversationLoading(true);
    setConversationError(null);
    setConversations([]);
    setActiveConversationId(null);
    setReadyConversationIds(new Set());
    setNewConversationIds(new Set());
    setChatMessages(agent.id, []);
    setSelectedAttachmentIds([]);

    void (async () => {
      try {
        let items = await api.conversations.list(project.id, agent.id);
        let createdId: string | null = null;
        if (items.length === 0) {
          const created = await api.conversations.create(project.id, agent.id);
          createdId = created.id;
          items = [created];
        }
        if (cancelled || navigationId !== conversationNavigationRef.current) {
          if (createdId) void api.conversations.remove(createdId).catch(() => undefined);
          return;
        }
        if (createdId) {
          const id = createdId;
          setNewConversationIds((current) => new Set(current).add(id));
          setReadyConversationIds((current) => new Set(current).add(id));
        }
        setConversations(items);
        const scope = `${project.id}:${agent.id}`;
        const rememberedId = useStore.getState().activeConversationByScope[scope];
        const selectedConversation = items.find((item) => item.id === rememberedId) ?? items[0];
        setActiveConversationId(selectedConversation.id);
        setActiveConversationForScope(scope, selectedConversation.id);
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
  }, [agent?.id, project?.id, conversationListReloadKey, setChatMessages, setActiveConversationForScope]);

  useEffect(() => {
    if (!agent || !project || !activeConversationId) return;
    setActiveConversationForScope(`${project.id}:${agent.id}`, activeConversationId);
    const loadId = ++conversationLoadRef.current;
    if (newConversationIds.has(activeConversationId)) {
      setConversationError(null);
      setConversationLoading(false);
      setChatMessages(agent.id, []);
      setReadyConversationIds((current) => new Set(current).add(activeConversationId));
      return () => {
        if (conversationLoadRef.current === loadId) conversationLoadRef.current += 1;
      };
    }
    setReadyConversationIds((current) => {
      const next = new Set(current);
      next.delete(activeConversationId);
      return next;
    });
    let timeoutId: number | undefined;
    setConversationLoading(true);
    setConversationError(null);
    setChatMessages(agent.id, []);
    const timeout = new Promise<never>((_, reject) => {
      timeoutId = window.setTimeout(
        () => reject(new Error("Loading this conversation timed out. You can switch chats and try again.")),
        15000,
      );
    });
    void Promise.race([api.conversations.messages(activeConversationId), timeout])
      .then((records) => {
        if (conversationLoadRef.current !== loadId) return;
        setChatMessages(agent.id, records.map((record) => fromStoredMessage(record, agent.name)));
        setReadyConversationIds((current) => new Set(current).add(activeConversationId));
      })
      .catch((cause) => {
        if (conversationLoadRef.current !== loadId) return;
        setConversationError(cause instanceof Error ? cause.message : "Could not load this conversation.");
      })
      .finally(() => {
        if (timeoutId !== undefined) window.clearTimeout(timeoutId);
        if (conversationLoadRef.current === loadId) setConversationLoading(false);
      });

    return () => {
      if (timeoutId !== undefined) window.clearTimeout(timeoutId);
      if (conversationLoadRef.current === loadId) conversationLoadRef.current += 1;
    };
  }, [activeConversationId, newConversationIds, conversationReloadKey, agent?.id, agent?.name, project?.id, setChatMessages, setActiveConversationForScope]);

  // Position the chat at its latest content before paint. Avoid smooth scrolling
  // from the first message, which makes every newly opened conversation visibly loop.
  useLayoutEffect(() => {
    const container = messagesContainerRef.current;
    if (container) container.scrollTop = container.scrollHeight;
  }, [agentMessages, isProcessing, activeConversationId, conversationLoading, agent?.id]);

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
        const orderedEvents = [...activeExecutionEvents].sort((a, b) => a.seq - b.seq);
        const endedSpans = new Set(
          orderedEvents.filter((event) => event.type === "span_ended" && event.span_id)
            .map((event) => event.span_id as string),
        );
        const openStep = [...orderedEvents].reverse().find(
          (event) => event.type === "span_started" && event.span_id && !endedSpans.has(event.span_id),
        );
        const lastCompletedTool = [...orderedEvents].reverse().find(
          (event) => event.type === "span_ended" && event.kind === "tool_call",
        );
        const cancellationDetails = status === "cancelled"
          ? [
              openStep ? `Stopped during: ${describeActiveStep(openStep)}.` : "",
              lastCompletedTool ? `Last completed tool: ${describeActiveStep(lastCompletedTool)}.` : "",
              `Original task: ${targetAgent.conversationId ? (chatMessages[agentId] || []).slice().reverse().find((message) => message.sender === "user")?.text || "See the preceding user message." : "See the preceding user message."}`,
            ].filter(Boolean).join("\n")
          : "";
        const fallback = status === "cancelled"
          ? `Stopped. Progress at cancellation:\n${cancellationDetails || "The execution stopped before any detailed progress event was recorded."}`
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
      } catch (error) {
        setChatError(error instanceof Error ? error.message : "Unable to load the completed run.");
      } finally {
        setIsProcessing(false);
        setIsCancelling(false);
        setNewConversationIds((current) => { if (!current.has(targetAgent.conversationId)) return current; const next = new Set(current); next.delete(targetAgent.conversationId); return next; });
        activeExecutionAgentRef.current = null;
        clearActiveExecutionForScope(project?.id + ":" + agentId, executionId);
        setActiveExecutionId(null);
      }
    })();
  }, [activeExecutionId, activeExecutionEvents, addChatMessage, chatMessages, clearActiveExecutionForScope, project?.id]);

  const latestUserTask = agentMessages.slice().reverse().find((message) => message.sender === "user");
  const activeTaskGoal = latestUserTask?.text
    ? latestUserTask.text.replace(/\s+/g, " ").trim().slice(0, 110)
    : null;
  const activeProgressBrief = (() => {
    const open = new Map<string, import("../types").ExecutionEvent>();
    for (const event of [...activeExecutionEvents].sort((a, b) => a.seq - b.seq)) {
      if (event.type === "span_started" && event.span_id) open.set(event.span_id, event);
      else if (event.type === "span_ended" && event.span_id) open.delete(event.span_id);
    }
    const openSpans = [...open.values()];
    const latest = openSpans[openSpans.length - 1];
    return latest ? describeActiveStep(latest) : null;
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
    conversationNavigationRef.current += 1;
    setEditingMessageId(null);
    setPromptInput("");
    setConversationError(null);
    try {
      const created = await api.conversations.create(project.id, agent.id);
      setConversations((current) => [created, ...current.filter((item) => item.id !== created.id)]);
      setReadyConversationIds((current) => new Set(current).add(created.id));
      setNewConversationIds((current) => new Set(current).add(created.id));
      setChatMessages(agent.id, []);
      setActiveConversationId(created.id);
    } catch (cause) {
      setConversationError(cause instanceof Error ? cause.message : "Could not create a conversation.");
      setConversationListReloadKey((value) => value + 1);
    }
  };

  const handleClearChat = async () => {
    if (!agent || !project || isProcessing) return;
    if (!window.confirm(`Delete this conversation with ${agent.name}? This cannot be undone.`)) return;
    conversationNavigationRef.current += 1;
    setConversationError(null);
    try {
      const created = await api.conversations.create(project.id, agent.id);
      if (activeConversationId) await api.conversations.remove(activeConversationId);
      setConversations((current) => [created, ...current.filter((item) => item.id !== activeConversationId && item.id !== created.id)]);
      setReadyConversationIds((current) => new Set(current).add(created.id));
      setNewConversationIds((current) => new Set(current).add(created.id));
      setChatMessages(agent.id, []);
      setActiveConversationId(created.id);
    } catch (cause) {
      setConversationError(cause instanceof Error ? cause.message : "Could not delete this conversation.");
      setConversationListReloadKey((value) => value + 1);
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
      <div className="h-full w-full flex-1 flex items-center justify-center p-6 select-none">
        <div className="text-center max-w-sm">
          <div className="mx-auto mb-4 flex h-11 w-11 items-center justify-center rounded-2xl bg-studio-900 neu-raised text-accent-400">
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

  const copyMessage = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setChatNotice("Message copied.");
    } catch {
      setChatError("Could not copy this message. Check clipboard permissions and try again.");
    }
  };

  const beginEditMessage = (message: Extract<ChatMessage, { sender: "user" }>) => {
    setEditingMessageId(message.id);
    setPromptInput(message.text);
    setChatError(null);
    setChatNotice("Editing this message will remove later turns and restart the conversation from here.");
    window.setTimeout(() => composerRef.current?.focus(), 0);
  };

  const cancelEditMessage = () => {
    setEditingMessageId(null);
    setPromptInput("");
    setChatNotice(null);
  };

  const sendTask = async (rawText: string, fromComposer = false) => {
    if (!rawText.trim() || isProcessing || !agent || !project) return;
    if (!activeConversationId || !readyConversationIds.has(activeConversationId)) {
      setChatError(conversationLoading
        ? "Wait for the saved conversation to finish loading, then try again."
        : "This conversation did not load successfully. Switch to another chat or reselect it to retry.");
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
      const editingIndex = editingMessageId
        ? agentMessages.findIndex((message) => message.id === editingMessageId && message.sender === "user")
        : -1;
      const historyMessages = editingIndex >= 0 ? agentMessages.slice(0, editingIndex) : agentMessages;
      const history = buildRunHistory(historyMessages);
      let userMsg: ChatMessage;
      if (editingIndex >= 0 && editingMessageId) {
        const savedUser = await api.conversations.editUserMessage(editingMessageId, userText);
        userMsg = {
          id: savedUser.id,
          sender: "user",
          text: savedUser.content,
          timestamp: new Date(savedUser.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        };
        setChatMessages(agent.id, [...historyMessages, userMsg]);
      } else {
        const savedUser = await api.conversations.appendMessage(activeConversationId, {
          role: "user",
          content: userText,
        });
        userMsg = {
          id: savedUser.id,
          sender: "user",
          text: savedUser.content,
          timestamp: new Date(savedUser.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        };
        addChatMessage(agent.id, userMsg);
      }

      const execution = await api.executions.run(project.id, agent.id, userText, history, selectedAttachmentIds);
      setSelectedAttachmentIds([]);
      setEditingMessageId(null);
      processedExecutionRef.current = null;
      activeExecutionAgentRef.current = { id: agent.id, name: agent.name, conversationId: activeConversationId };
      setActiveExecutionForScope(project.id + ":" + agent.id, {
        executionId: execution.id, agentId: agent.id, agentName: agent.name, conversationId: activeConversationId,
      });
      setActiveExecutionId(execution.id);
      onRunExecution(execution.id);
      // The stream owns completion now; do not poll the execution endpoint.
    } catch (e) {
      setNewConversationIds((current) => { if (!current.has(activeConversationId)) return current; const next = new Set(current); next.delete(activeConversationId); return next; });
      setReadyConversationIds((current) => { const next = new Set(current); next.delete(activeConversationId); return next; });
      setChatError(e instanceof Error ? e.message : "Failed to start execution");
      setIsProcessing(false);
      setIsCancelling(false);
      activeExecutionAgentRef.current = null;
      clearActiveExecutionForScope(project.id + ":" + agent.id);
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
    <div className="h-full w-full flex-1 flex flex-col min-w-0 text-studio-100">
      {/* Header bar showing active agent */}
      <div className="px-6 py-4 border-b border-line flex flex-wrap items-center justify-between gap-x-4 gap-y-2 shrink-0 min-w-0 select-none">
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
        <div className="flex flex-wrap items-center gap-2">
          <label className="sr-only" htmlFor="conversation-switcher">Saved conversations</label>
          <select
            id="conversation-switcher"
            aria-label="Saved conversations"
            value={activeConversationId ?? ""}
            onChange={(event) => {
              const nextId = event.target.value || null;
              conversationNavigationRef.current += 1;
              setEditingMessageId(null);
              setPromptInput("");
              if (nextId && !newConversationIds.has(nextId)) {
                setReadyConversationIds((current) => { const next = new Set(current); next.delete(nextId); return next; });
              }
              setActiveConversationId(nextId);
            }}
            disabled={isProcessing || conversations.length === 0}
            className="max-w-40 rounded-lg border border-transparent bg-studio-900 px-2.5 py-1.5 text-2xs text-studio-200 disabled:opacity-50"
          >
            {conversations.map((conversation) => (
              <option key={conversation.id} value={conversation.id}>{conversation.title || "New conversation"}</option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => void handleNewConversation()}
            disabled={isProcessing}
            className="neu-btn px-2.5 py-1 text-2xs font-mono text-studio-300 transition-all disabled:opacity-50"
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
            <span className="text-2xs font-mono px-2 py-0.5 rounded-full bg-studio-900 neu-raised-sm text-studio-300 font-medium shrink-0">
              {agent.child_agent_ids.length} delegated
            </span>
          )}
          {agent.tool_ids && agent.tool_ids.length > 0 && (
            <span className="text-2xs font-mono px-2 py-0.5 rounded-full bg-studio-900 neu-raised-sm text-studio-300 font-medium shrink-0">
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

      <div ref={messagesContainerRef} role="log" aria-label={`Conversation with ${agent.name}`} aria-busy={conversationLoading} className="flex-1 overflow-y-auto p-6 space-y-4 min-h-0">
        {conversationLoading && (
          <p role="status" className="rounded-lg bg-studio-900 neu-raised-sm px-3 py-2 text-2xs text-studio-400">
            Loading saved conversation…
          </p>
        )}
        {conversationError && (
          <div role="alert" className="flex flex-wrap items-center gap-2 rounded border border-amber-800 bg-amber-950/30 px-3 py-2 text-2xs text-amber-200">
            <span className="min-w-0 flex-1">{conversationError}</span>
            <button type="button" onClick={() => setConversationReloadKey((value) => value + 1)} disabled={conversationLoading || isProcessing} className="rounded border border-amber-700/70 px-2 py-1 hover:bg-amber-900/40 disabled:opacity-50">Retry loading</button>
          </div>
        )}
        {agentMessages.every((message) => message.sender === "tool") && (
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
                  className="rounded-xl bg-studio-900 neu-raised-sm px-3.5 py-2 text-xs text-studio-300 transition-all hover:text-white active:shadow-neu-pressed"
                >
                  {starter.label}
                </button>
              ))}
            </div>
          </div>
        )}

        {agentMessages.filter((msg) => msg.sender !== "tool").map((msg) => (
          <div
            key={msg.id}
            className={`flex flex-col ${msg.sender === "user" ? "items-end" : "items-start"}`}
          >
            <div className="flex items-center gap-2 mb-1 px-1">
              <span className="text-2xs font-mono font-semibold text-studio-400">
                {msg.sender === "user" ? "You" : msg.agentName || "Agent"}
              </span>
              <span className="text-2xs font-mono text-studio-600">{msg.timestamp}</span>
              {msg.sender === "agent" && isSimulatedText(msg.text) && (
                <span className="rounded border border-amber-800/70 bg-amber-950/40 px-1.5 text-[10px] font-mono uppercase text-amber-300">Simulated</span>
              )}
            </div>

            <div
              className={`max-w-3xl rounded-2xl px-4 py-3 border ${
                msg.sender === "user"
                  ? "neu-accent text-white border-transparent rounded-br-md"
                  : msg.executionStatus === "error" || msg.executionStatus === "interrupted"
                    ? "bg-red-950/45 neu-raised-sm text-red-100 border-red-500/20 rounded-bl-md"
                    : msg.executionStatus === "budget_exceeded"
                      ? "bg-amber-950/45 neu-raised-sm text-amber-100 border-amber-500/20 rounded-bl-md"
                      : msg.executionStatus === "cancelled"
                        ? "bg-studio-900 neu-raised-sm text-studio-400 border-transparent rounded-bl-md"
                        : "bg-studio-900 neu-raised-sm text-studio-100 border-transparent rounded-bl-md"
              }`}
            >
              {msg.sender === "user" ? <p className="whitespace-pre-wrap text-sm leading-6">{msg.text}</p> : <ArtifactViewer content={msg.text} executionId={msg.executionId} />}
            </div>
            {(msg.sender === "user" || msg.sender === "agent") && (
              <div className={`mt-1 ml-1 flex items-center gap-3 text-[10px] text-studio-500 ${msg.sender === "user" ? "justify-end" : ""}`}>
                <button type="button" onClick={() => void copyMessage(msg.text)} className="hover:text-studio-200" aria-label={msg.sender === "user" ? "Copy your message" : "Copy assistant response"}>Copy</button>
                {msg.sender === "user" && (
                  <button type="button" onClick={() => beginEditMessage(msg)} disabled={isProcessing || conversationLoading} className="hover:text-studio-200 disabled:opacity-40" aria-label="Edit and resend message">Edit</button>
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
                  className={`rounded border px-2 py-1 transition-colors ${msg.feedbackValue === 1 ? "border-emerald-700 bg-emerald-950 text-emerald-200" : "border-line text-studio-400 hover:bg-studio-800"}`}
                >👍 Yes</button>
                <button
                  type="button"
                  aria-label="Mark answer not helpful"
                  aria-pressed={msg.feedbackValue === -1}
                  onClick={() => void handleFeedback(msg.id, -1)}
                  className={`rounded border px-2 py-1 transition-colors ${msg.feedbackValue === -1 ? "border-amber-700 bg-amber-950 text-amber-200" : "border-line text-studio-400 hover:bg-studio-800"}`}
                >👎 No</button>
              </div>
            )}
          </div>
        ))}

        {isProcessing && (
          <div role="status" aria-live="polite" className="flex items-start gap-3 text-studio-300 text-sm py-3 px-4 bg-studio-900 neu-raised-sm rounded-2xl w-fit max-w-3xl">
            <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-amber-300 animate-pulse" />
            <div className="min-w-0">
              <p className="font-mono text-xs sm:text-sm">{activeProgressBrief || `${agent.name} is working through the task…`}</p>
              {activeTaskGoal && <p className="mt-1 text-[10px] leading-4 text-studio-500">Goal: {activeTaskGoal}{latestUserTask && latestUserTask.text.trim().length > 110 ? "…" : ""}</p>}
            </div>
          </div>
        )}

        {chatNotice && (
          <div role="status" className="rounded-md border border-line-strong bg-studio-900 px-4 py-3 text-sm text-studio-300">
            {chatNotice}
          </div>
        )}

        {chatError && (
          <div role="alert" className="rounded-md border border-red-800 bg-red-950/60 px-4 py-3 text-sm text-red-300">
            <span className="font-semibold">Something went wrong.</span> {chatError}
          </div>
        )}
      </div>

      <ApprovalDialog executionId={activeExecutionId} events={activeExecutionEvents} />

      {/* Multi-Line Prompt Bar */}
      <div className="p-4 shrink-0">
        <div className="max-w-4xl mx-auto flex items-end gap-3 bg-studio-900 neu-inset border border-transparent rounded-2xl p-2.5 focus-within:border-accent-500/50 transition-colors">
          <ProjectAttachmentsPanel
            projectId={project.id}
            selectedIds={selectedAttachmentIds}
            onSelectedIdsChange={setSelectedAttachmentIds}
            disabled={isProcessing || conversationLoading}
            compact
          />
          <textarea
            ref={composerRef}
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
            placeholder={editingMessageId ? "Edit your message and resend…" : `Message ${agent.name}…`}
            disabled={isProcessing}
            className="flex-1 bg-transparent shadow-none focus-visible:shadow-none text-sm text-studio-100 placeholder:text-studio-500 focus:outline-none resize-none py-2 px-3 min-h-[40px] max-h-40 overflow-y-auto"
          />
          {editingMessageId && !isProcessing && (
            <button type="button" onClick={cancelEditMessage} className="h-10 w-10 shrink-0 rounded-full bg-studio-800 text-studio-400 hover:text-white" aria-label="Cancel editing" title="Cancel editing">×</button>
          )}
          {isProcessing ? (
            <button
              onClick={handleCancelExecution}
              disabled={!activeExecutionId || isCancelling}
              className="bg-red-900/80 neu-raised-sm hover:bg-red-800 active:shadow-neu-pressed disabled:opacity-40 text-red-100 text-xs font-semibold px-4 py-2 rounded-xl transition-all flex items-center gap-1 shrink-0 h-9 cursor-pointer"
              aria-label="Stop execution"
            >
              <span>{isCancelling ? "Stopping…" : "Stop"}</span>
            </button>
          ) : (
            <button
              onClick={handleSendMessage}
              disabled={!promptInput.trim()}
              className="neu-accent hover:brightness-110 active:shadow-neu-pressed disabled:opacity-40 disabled:shadow-none text-white rounded-full transition-all flex items-center justify-center shrink-0 h-10 w-10 cursor-pointer"
              aria-label={editingMessageId ? "Resend edited message" : "Send message"}
              title={editingMessageId ? "Resend edited message" : "Send message"}
            >
              <span className="sr-only">{editingMessageId ? "Resend" : "Send"}</span><Icon name="chevron-right" size={17} />
            </button>
          )}
        </div>
        <p className="mx-auto mt-1.5 max-w-4xl px-2 text-[10px] text-studio-500">Enter to send · Shift+Enter for a new line</p>
      </div>
    </div>
  );
}
