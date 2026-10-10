import React, { useState, useEffect, useRef } from "react";
import { useStore } from "../store/useStore";
import { api } from "../api/client";
import { useExecutionStream } from "../hooks/useExecutionStream";
import { executionToolMessages } from "../utils/executionToolMessages";
import type { ChatMessage } from "../types";

interface LiveConsoleDrawerProps {
  executionId: string | null;
  onRunExecution: (execId: string) => void;
  isExpanded?: boolean;
  onToggleExpand?: () => void;
}

export function LiveConsoleDrawer({
  executionId,
  onRunExecution,
  isExpanded = true,
  onToggleExpand,
}: LiveConsoleDrawerProps) {
  const agent = useStore((s) => s.agents.find((a) => a.id === s.selectedAgentId));
  const project = useStore((s) => s.project);
  const chatMessages = useStore((s) => s.chatMessages);
  const addChatMessage = useStore((s) => s.addChatMessage);

  const [promptInput, setPromptInput] = useState("");
  const [isProcessing, setIsProcessing] = useState(false);
  const [activeExecId, setActiveExecId] = useState<string | null>(executionId);
  const [copied, setCopied] = useState(false);
  const [selectedEventSeq, setSelectedEventSeq] = useState<number | null>(null);

  const { events } = useExecutionStream(activeExecId);
  const chatEndRef = useRef<HTMLDivElement>(null);

  const agentMessages = agent ? chatMessages[agent.id] || [] : [];

  useEffect(() => {
    if (executionId) {
      setActiveExecId(executionId);
    }
  }, [executionId]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [agentMessages, isProcessing]);

  const isExecutionRunning = events.length > 0 && !events.some((e) => e.type === "execution_ended");

  // Selected event or latest
  const displayEvent = events.find((e) => e.seq === selectedEventSeq) || events[events.length - 1];

  const handleSendMessage = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!promptInput.trim() || isProcessing || !agent || !project) return;

    const userText = promptInput.trim();
    setPromptInput("");
    setIsProcessing(true);

    const userMsg: ChatMessage = {
      id: Date.now().toString(),
      sender: "user",
      text: userText,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };
    addChatMessage(agent.id, userMsg);

    try {
      const execution = await api.executions.run(project.id, agent.id, userText);
      setActiveExecId(execution.id);
      onRunExecution(execution.id);

      // Poll until finished
      let completedExecution = await api.executions.get(execution.id);
      for (let i = 0; i < 180; i++) {
        await new Promise((r) => setTimeout(r, 600));
        completedExecution = await api.executions.get(execution.id);
        if (["completed", "error", "cancelled"].includes(completedExecution.status)) {
          break;
        }
      }

      // Add tool preview messages if any
      const executionEvents = await api.executions.getEvents(execution.id);
      const toolMessages = executionToolMessages(executionEvents);
      for (const tm of toolMessages) {
        addChatMessage(agent.id, tm);
      }

      const agentMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        sender: "agent",
        agentName: agent.name,
        text:
          completedExecution.final_output ||
          completedExecution.error ||
          "Execution complete.",
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };
      addChatMessage(agent.id, agentMsg);
    } catch (err) {
      console.error("Execution error:", err);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleCopyLogs = () => {
    const textToCopy = displayEvent
      ? JSON.stringify(displayEvent.data, null, 2)
      : JSON.stringify({ status: "idle", message: "No execution logs yet" }, null, 2);
    navigator.clipboard.writeText(textToCopy);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="w-full bg-studio-900 border-t border-studio-700/80 flex flex-col shrink-0 select-none transition-all shadow-elevated">
      {/* Drawer Control Header */}
      <div
        onClick={onToggleExpand}
        className="h-8 px-4 bg-studio-850 hover:bg-studio-800 border-b border-studio-700/60 flex items-center justify-between text-2xs font-mono cursor-pointer transition-colors"
      >
        <div className="flex items-center gap-3">
          <span className="text-studio-400">
            {isExpanded ? "▼" : "▲"} Console & Debugger
          </span>
          <span className="text-studio-600">|</span>
          <span className="text-studio-300">
            Agent: <strong className="text-accent-400">{agent?.name || "None"}</strong>
          </span>
          {activeExecId && (
            <span className="text-studio-500">
              Run: #{activeExecId.slice(0, 8)}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {isExecutionRunning ? (
            <span className="text-amber-400 flex items-center gap-1.5 font-semibold">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
              Executing Trace…
            </span>
          ) : activeExecId ? (
            <span className="text-emerald-400 flex items-center gap-1.5 font-semibold">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
              Completed
            </span>
          ) : (
            <span className="text-studio-500">Idle</span>
          )}
        </div>
      </div>

      {/* Expanded Dual-Panel Content */}
      {isExpanded && (
        <div className="h-64 grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-studio-800 overflow-hidden text-xs">
          {/* Left Panel: AI Collaboration Chat */}
          <div className="flex flex-col h-full bg-studio-950/60 overflow-hidden min-w-0">
            {/* Header */}
            <div className="p-2.5 border-b border-studio-800 bg-studio-900/90 flex items-center justify-between shrink-0">
              <div className="flex items-center gap-2">
                <span className="text-xs">💬</span>
                <span className="font-semibold text-studio-200">AI Collaboration Chat</span>
              </div>
              <span className="text-2xs font-mono text-studio-500">
                {agentMessages.length} messages
              </span>
            </div>

            {/* Messages Thread */}
            <div className="flex-1 overflow-y-auto p-3 space-y-2.5 min-h-0">
              {agentMessages.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center text-center p-4 text-studio-500 text-2xs space-y-1">
                  <span>Enter a task or instruction below to test this agent workflow.</span>
                  <span className="text-studio-600">
                    Triggers full execution tree, attached tools, and structured outputs.
                  </span>
                </div>
              ) : (
                agentMessages.map((msg) => (
                  <div
                    key={msg.id}
                    className={`flex flex-col ${
                      msg.sender === "user" ? "items-end" : "items-start"
                    }`}
                  >
                    <div className="flex items-center gap-1.5 mb-0.5">
                      <span className="text-2xs font-mono text-studio-500">
                        {msg.sender === "user" ? "You" : msg.sender === "tool" ? `Tool: ${msg.toolName}` : msg.agentName || "Agent"}
                      </span>
                      <span className="text-2xs font-mono text-studio-600">{msg.timestamp}</span>
                    </div>
                    <div
                      className={`max-w-[85%] rounded-md px-3 py-1.5 text-xs whitespace-pre-wrap leading-relaxed ${
                        msg.sender === "user"
                          ? "bg-accent-600 text-white shadow-sm"
                          : msg.sender === "tool"
                          ? "bg-emerald-950/40 text-emerald-300 border border-emerald-800/60 font-mono text-2xs"
                          : "bg-studio-850 text-studio-100 border border-studio-700/80 shadow-sm"
                      }`}
                    >
                      {msg.text}
                    </div>
                  </div>
                ))
              )}
              {isProcessing && (
                <div className="flex items-center gap-2 text-2xs font-mono text-accent-400 p-2 bg-studio-900 rounded border border-studio-800 animate-pulse">
                  <span>⚙️</span>
                  <span>Executing agent graph and tool calls…</span>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>

            {/* Chat Input Bar */}
            <form
              onSubmit={handleSendMessage}
              className="p-2 border-t border-studio-800 bg-studio-900 flex items-center gap-2 shrink-0"
            >
              <input
                type="text"
                value={promptInput}
                onChange={(e) => setPromptInput(e.target.value)}
                placeholder="Type a message or instruction to run…"
                disabled={isProcessing || !agent}
                className="flex-1 bg-studio-800 text-studio-100 placeholder:text-studio-500 border border-studio-700 rounded px-3 py-1.5 text-xs focus:outline-none focus:border-accent-500 disabled:opacity-50"
              />
              <button
                type="submit"
                disabled={!promptInput.trim() || isProcessing || !agent}
                className="px-3.5 py-1.5 bg-accent-600 hover:bg-accent-500 disabled:opacity-40 text-white font-medium text-xs rounded transition-colors shadow-studio cursor-pointer shrink-0"
              >
                Send
              </button>
            </form>
          </div>

          {/* Right Panel: Live Execution Logs (Concept 1 style) */}
          <div className="flex flex-col h-full bg-studio-950/60 overflow-hidden min-w-0">
            {/* Header */}
            <div className="p-2.5 border-b border-studio-800 bg-studio-900/90 flex items-center justify-between shrink-0">
              <div className="flex items-center gap-2">
                <span className="text-xs">⚡</span>
                <span className="font-semibold text-studio-200">Live Execution Logs</span>
              </div>
              <div className="flex items-center gap-2 text-2xs font-mono">
                <span className="text-studio-500">
                  status: {isExecutionRunning ? "running" : activeExecId ? "completed" : "idle"}
                </span>
                <span className="text-studio-600">·</span>
                <span className="text-studio-400">v3.2.1</span>
              </div>
            </div>

            {/* Split Log Body: Node Checklist (Left) & JSON Inspector (Right) */}
            <div className="flex-1 grid grid-cols-1 sm:grid-cols-5 divide-x divide-studio-800 overflow-hidden min-h-0">
              {/* Checklist Column */}
              <div className="sm:col-span-2 overflow-y-auto p-2 space-y-1 bg-studio-900/40">
                <span className="text-2xs font-mono uppercase text-studio-500 block px-1 mb-1">
                  Trace Nodes
                </span>

                <div
                  onClick={() => setSelectedEventSeq(null)}
                  className={`p-1.5 rounded cursor-pointer border flex items-center justify-between transition-colors ${
                    selectedEventSeq === null
                      ? "bg-studio-800 border-accent-500 text-white"
                      : "bg-studio-900 border-studio-800 text-studio-300 hover:bg-studio-850"
                  }`}
                >
                  <div className="flex items-center gap-1.5 truncate">
                    <span className="text-emerald-400 text-xs">✓</span>
                    <span className="text-2xs font-mono font-medium truncate uppercase">
                      TRIGGER
                    </span>
                  </div>
                  <span className="text-2xs font-mono text-studio-500">input</span>
                </div>

                {events.map((evt) => {
                  const isSelected = selectedEventSeq === evt.seq;
                  const isEnded = evt.type === "span_ended";
                  const isStarted = evt.type === "span_started";
                  if (!isStarted && !isEnded) return null;

                  return (
                    <div
                      key={evt.seq}
                      onClick={() => setSelectedEventSeq(evt.seq)}
                      className={`p-1.5 rounded cursor-pointer border flex items-center justify-between transition-colors ${
                        isSelected
                          ? "bg-studio-800 border-accent-500 text-white"
                          : "bg-studio-900 border-studio-800 text-studio-300 hover:bg-studio-850"
                      }`}
                    >
                      <div className="flex items-center gap-1.5 truncate">
                        <span className={`text-xs ${evt.status === "error" ? "text-red-400" : "text-emerald-400"}`}>
                          {evt.status === "error" ? "✕" : "✓"}
                        </span>
                        <span className="text-2xs font-mono truncate uppercase">
                          {evt.name || evt.kind || evt.type}
                        </span>
                      </div>
                      <span className="text-2xs font-mono text-studio-500">#{evt.seq}</span>
                    </div>
                  );
                })}

                {events.length === 0 && (
                  <div className="p-3 text-center text-studio-500 text-2xs italic">
                    No run executed yet.
                  </div>
                )}
              </div>

              {/* Step Payload Inspector Column */}
              <div className="sm:col-span-3 flex flex-col h-full bg-studio-950 overflow-hidden">
                <div className="p-2 border-b border-studio-800 flex items-center justify-between bg-studio-900/60 shrink-0">
                  <span className="text-2xs font-mono text-studio-400 truncate">
                    Processing node: <strong className="text-emerald-400">{displayEvent?.name || "Pipeline"}</strong>
                  </span>
                  <button
                    onClick={handleCopyLogs}
                    className="p-1 text-2xs font-mono text-studio-400 hover:text-white hover:bg-studio-800 rounded transition-colors cursor-pointer"
                    title="Copy step payload JSON"
                  >
                    {copied ? "Copied! ✓" : "Copy 📋"}
                  </button>
                </div>

                <div className="flex-1 overflow-auto p-2.5">
                  <pre className="text-2xs font-mono text-emerald-300/90 leading-relaxed whitespace-pre-wrap break-all">
                    {displayEvent
                      ? JSON.stringify(displayEvent.data, null, 2)
                      : JSON.stringify(
                          {
                            status: "ready",
                            target_agent: agent?.name || "None",
                            message: "Awaiting execution trigger...",
                          },
                          null,
                          2
                        )}
                  </pre>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
