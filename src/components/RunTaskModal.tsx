import { useEffect, useRef, useState } from "react";
import { useEscapeKey } from "../hooks/useEscapeKey";
import { Button } from "./ui/Button";
import { Icon } from "./ui/Icon";

interface RunTaskModalProps {
  agentName: string;
  onClose: () => void;
  /** Resolve to close the dialog; throw to show the message inline and keep the dialog open. */
  onSubmit: (task: string) => Promise<void>;
}

export function RunTaskModal({ agentName, onClose, onSubmit }: RunTaskModalProps) {
  const [task, setTask] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEscapeKey(onClose, !isSubmitting);
  useEffect(() => textareaRef.current?.focus(), []);

  const canSubmit = task.trim().length > 0 && !isSubmitting;

  const submit = async () => {
    if (!canSubmit) return;
    setIsSubmitting(true);
    setError(null);
    try {
      await onSubmit(task.trim());
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The run could not be started.");
      setIsSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !isSubmitting) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="run-task-title"
        className="w-full max-w-lg space-y-4 rounded-panel bg-studio-900 p-5 text-studio-100 shadow-elevated"
      >
        <div className="flex items-start justify-between gap-3 border-b border-line pb-3">
          <div>
            <h2 id="run-task-title" className="text-sm font-semibold">
              Run workflow
            </h2>
            <p className="mt-0.5 text-2xs text-studio-400">
              <span className="font-mono text-studio-300">{agentName}</span> will receive this task and may delegate to its team. It is saved in this agent’s chat history.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded p-1 text-studio-400 transition-colors hover:bg-studio-800 hover:text-studio-100"
          >
            <Icon name="close" size={14} />
          </button>
        </div>

        <div className="space-y-1.5">
          <label htmlFor="run-task-input" className="block text-2xs font-mono uppercase tracking-wider text-studio-400">
            Task
          </label>
          <textarea
            id="run-task-input"
            ref={textareaRef}
            rows={5}
            value={task}
            onChange={(event) => setTask(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
                event.preventDefault();
                void submit();
              }
            }}
            placeholder="Describe what you want done, e.g. “Draft a 30-second launch teaser script.”"
            className="w-full resize-none rounded-lg border border-transparent bg-studio-900 p-3 text-sm text-studio-100 placeholder:text-studio-500 transition-colors hover:border-studio-600 focus:border-accent-500 focus:outline-none focus:ring-1 focus:ring-accent-500/50"
          />
        </div>

        {error && (
          <p role="alert" className="rounded border border-red-900/60 bg-red-950/40 px-3 py-2 text-xs text-red-300">
            {error}
          </p>
        )}

        <div className="flex items-center justify-between">
          <span className="text-2xs text-studio-500">Ctrl/⌘ + Enter to run</span>
          <div className="flex gap-2">
            <Button variant="outline" onClick={onClose} disabled={isSubmitting}>
              Cancel
            </Button>
            <Button variant="primary" onClick={() => void submit()} disabled={!canSubmit}>
              {isSubmitting ? "Starting…" : "Run"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
