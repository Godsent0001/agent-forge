import { useEffect, useMemo, useRef, useState } from "react";
import { api, type ExecutionArtifact, type PreviewStatus } from "../api/client";
import type { ExecutionEvent } from "../types";
import { Icon } from "./ui/Icon";

type WorkspaceFile = { path: string; size_bytes: number };
type Entry = {
  key: string;
  name: string;
  path: string;
  size: number;
  mediaType?: string;
  artifactId?: string;
  version?: number;
  source?: "run" | "project";
};

const TEXT_EXTENSIONS = new Set([
  "txt", "md", "markdown", "json", "jsonl", "csv", "tsv", "py", "js", "jsx",
  "ts", "tsx", "css", "html", "htm", "xml", "yaml", "yml", "toml", "ini",
  "sh", "bat", "cmd", "ps1", "sql", "log", "env", "gitignore", "diff", "svg",
]);
const IMAGE_EXTENSIONS = new Set(["png", "jpg", "jpeg", "gif", "webp", "bmp"]);
const VIDEO_EXTENSIONS = new Set(["mp4", "webm", "mov", "m4v"]);
const AUDIO_EXTENSIONS = new Set(["mp3", "wav", "ogg", "m4a", "aac", "flac"]);
const DOCUMENT_EXTENSIONS = new Set(["pdf"]);

function extension(path: string) {
  const name = path.split(/[\\/]/).pop() ?? path;
  return name.includes(".") ? name.split(".").pop()!.toLowerCase() : "";
}
function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}
function shortEvent(event: ExecutionEvent) {
  const name = event.name || event.type.replace(/_/g, " ");
  const data = event.data ?? {};
  if (event.kind === "tool_call" || name.toLowerCase().includes("shell")) {
    const args = data.args;
    if (typeof args === "string") return args.slice(0, 180);
    if (args && typeof args === "object") {
      const record = args as Record<string, unknown>;
      const command = record.command ?? record.cmd ?? record.input ?? record.path ?? record.file_path;
      if (typeof command === "string") return command.slice(0, 180);
    }
  }
  const output = data.result_preview ?? data.output_preview ?? data.message;
  return typeof output === "string" ? output.slice(0, 180) : name;
}

export function AgentWorkspacePanel({
  projectId,
  executionId,
}: {
  projectId: string;
  executionId: string | null;
}) {
  const [tab, setTab] = useState<"preview" | "files">("preview");
  const [workspaceFiles, setWorkspaceFiles] = useState<WorkspaceFile[]>([]);
  const [runFiles, setRunFiles] = useState<WorkspaceFile[]>([]);
  const [artifacts, setArtifacts] = useState<ExecutionArtifact[]>([]);
  const [observedExecutionId, setObservedExecutionId] = useState<string | null>(executionId);
  const [events, setEvents] = useState<ExecutionEvent[]>([]);
  const [runStatus, setRunStatus] = useState<string>("idle");
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewText, setPreviewText] = useState<string | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);
  const [previewServer, setPreviewServer] = useState<PreviewStatus | null>(null);
  const [previewServerBusy, setPreviewServerBusy] = useState(false);
  const [previewServerError, setPreviewServerError] = useState<string | null>(null);
  const lastSeq = useRef(0);

  useEffect(() => {
    if (executionId) setObservedExecutionId(executionId);
  }, [executionId]);

  useEffect(() => {
    let active = true;
    const refresh = async () => {
      try {
        const workspace = await api.projects.workspace(projectId);
        if (active) setWorkspaceFiles(workspace.files);
      } catch {
        if (active) setWorkspaceFiles([]);
      }
      if (observedExecutionId) {
        try {
          const runWorkspace = await api.executions.workspaceFiles(observedExecutionId);
          if (active) setRunFiles(runWorkspace.files);
        } catch {
          if (active) setRunFiles([]);
        }
      } else if (active) {
        setRunFiles([]);
      }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 2500);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [projectId, observedExecutionId]);

  useEffect(() => {
    let active = true;
    if (!observedExecutionId) {
      setArtifacts([]);
      setEvents([]);
      setRunStatus("idle");
      lastSeq.current = 0;
      void api.executions.list(projectId, 1).then((runs) => {
        if (active && runs[0]) {
          setObservedExecutionId(runs[0].id);
          setRunStatus(runs[0].status);
        }
      }).catch(() => undefined);
      return () => { active = false; };
    }

    setEvents([]);
    setArtifacts([]);
    lastSeq.current = 0;
    const poll = async () => {
      try {
        const [nextEvents, run, nextArtifacts] = await Promise.all([
          api.executions.getEvents(observedExecutionId, lastSeq.current),
          api.executions.get(observedExecutionId),
          api.artifacts.list(observedExecutionId),
        ]);
        if (!active) return;
        if (nextEvents.length) {
          lastSeq.current = nextEvents[nextEvents.length - 1].seq;
          setEvents((current) => [...current, ...nextEvents].slice(-60));
        }
        setRunStatus(run.status);
        setArtifacts(nextArtifacts);
      } catch {
        // A selected execution may be removed or unavailable; keep the workspace usable.
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 1400);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [observedExecutionId, projectId]);

  const entries = useMemo<Entry[]>(() => {
    const files: Entry[] = [
      ...runFiles.map((file) => ({
        key: `run-file:${file.path}`,
        name: file.path.split("/").pop() || file.path,
        path: file.path,
        size: file.size_bytes,
        source: "run" as const,
      })),
      ...workspaceFiles.map((file) => ({
        key: `project-file:${file.path}`,
        name: file.path.split("/").pop() || file.path,
        path: file.path,
        size: file.size_bytes,
        source: "project" as const,
      })),
    ];
    const generated: Entry[] = artifacts.map((artifact) => ({
      key: `artifact:${artifact.artifact_id}:${artifact.version}`,
      name: artifact.name,
      path: artifact.name,
      size: artifact.size_bytes,
      mediaType: artifact.media_type,
      artifactId: artifact.artifact_id,
      version: artifact.version,
    }));
    return [...generated, ...files].sort((a, b) => a.path.localeCompare(b.path));
  }, [workspaceFiles, runFiles, artifacts]);

  useEffect(() => {
    if (selectedKey && entries.some((entry) => entry.key === selectedKey)) return;
    if (!entries.length) return;
    const preferred = entries.find((entry) => entry.artifactId) ??
      entries.find((entry) => DOCUMENT_EXTENSIONS.has(extension(entry.path)) ||
        IMAGE_EXTENSIONS.has(extension(entry.path)) || VIDEO_EXTENSIONS.has(extension(entry.path)) ||
        AUDIO_EXTENSIONS.has(extension(entry.path))) ??
      entries.find((entry) => extension(entry.path) === "index.html") ??
      entries.find((entry) => entry.source === "run") ?? entries[0];
    setSelectedKey(preferred.key);
  }, [entries, selectedKey]);

  const packageEntry = entries
    .filter((entry) => entry.source === "run" && extension(entry.path) === "json" && entry.path.split("/").pop() === "package.json")
    .sort((a, b) => Number(a.path !== "package.json") - Number(b.path !== "package.json"))[0] ?? null;

  useEffect(() => {
    let active = true;
    if (!observedExecutionId || !packageEntry) {
      setPreviewServer(null);
      return () => { active = false; };
    }
    const poll = async () => {
      try {
        const status = await api.executions.previewStatus(observedExecutionId);
        if (active) setPreviewServer(status);
      } catch {
        if (active) setPreviewServer(null);
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 1200);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [observedExecutionId, packageEntry?.path]);

  const startAppPreview = async () => {
    if (!observedExecutionId || !packageEntry || previewServerBusy) return;
    setPreviewServerBusy(true);
    setPreviewServerError(null);
    try {
      const status = await api.executions.startPreview(observedExecutionId, packageEntry.path);
      setPreviewServer(status);
    } catch (error) {
      setPreviewServerError(error instanceof Error ? error.message : "Could not start the app preview.");
    } finally {
      setPreviewServerBusy(false);
    }
  };

  const stopAppPreview = async () => {
    if (!observedExecutionId || previewServerBusy) return;
    setPreviewServerBusy(true);
    try {
      setPreviewServer(await api.executions.stopPreview(observedExecutionId));
    } catch (error) {
      setPreviewServerError(error instanceof Error ? error.message : "Could not stop the app preview.");
    } finally {
      setPreviewServerBusy(false);
    }
  };

  const selected = entries.find((entry) => entry.key === selectedKey) ?? null;
  useEffect(() => {
    let active = true;
    let objectUrl: string | null = null;
    setPreviewUrl(null);
    setPreviewText(null);
    setFileError(null);
    if (!selected) {
      setLoadingPreview(false);
      return () => { active = false; };
    }

    setLoadingPreview(true);
    const load = async () => {
      try {
        let blob = selected.artifactId && observedExecutionId
          ? await api.artifacts.download(observedExecutionId, selected.artifactId, selected.version)
          : selected.source === "run" && observedExecutionId
            ? await api.executions.readFile(observedExecutionId, selected.path)
            : await api.projects.readWorkspaceFile(projectId, selected.path);
        if (!active) return;
        const ext = extension(selected.path);
        const type = selected.mediaType || blob.type || "application/octet-stream";
        if (TEXT_EXTENSIONS.has(ext) || type.startsWith("text/") || type.includes("json") || type.includes("xml")) {
          const textBlob = type && blob.type !== type ? new Blob([blob], { type }) : blob;
          const text = await textBlob.text();
          if (active) setPreviewText(text.slice(0, 1_000_000));
        } else {
          if (selected.mediaType && blob.type !== selected.mediaType) blob = new Blob([blob], { type: selected.mediaType });
          objectUrl = URL.createObjectURL(blob);
          if (active) setPreviewUrl(objectUrl);
        }
      } catch (error) {
        if (active) setFileError(error instanceof Error ? error.message : "Could not open this file.");
      } finally {
        if (active) setLoadingPreview(false);
      }
    };
    void load();
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [selectedKey, selected?.path, selected?.artifactId, selected?.version, observedExecutionId, projectId]);

  const selectedExt = selected ? extension(selected.path) : "";
  const isImage = IMAGE_EXTENSIONS.has(selectedExt) || Boolean(selected?.mediaType?.startsWith("image/"));
  const isVideo = VIDEO_EXTENSIONS.has(selectedExt) || Boolean(selected?.mediaType?.startsWith("video/"));
  const isAudio = AUDIO_EXTENSIONS.has(selectedExt) || Boolean(selected?.mediaType?.startsWith("audio/"));
  const isPdf = DOCUMENT_EXTENSIONS.has(selectedExt) || selected?.mediaType === "application/pdf";
  const isHtml = selectedExt === "html" || selectedExt === "htm";
  const visibleEvents = [...events].reverse().filter((event) =>
    event.type === "span_started" || event.type === "span_ended" ||
    event.type === "artifact_persisted" || event.type === "artifact_verification" ||
    event.type === "approval_requested" || event.type === "execution_ended"
  ).slice(0, 18);

  return (
    <section aria-label="Agent workspace" className="flex h-full min-w-0 flex-1 flex-col overflow-hidden rounded-panel bg-studio-900 neu-raised">
      <header className="flex shrink-0 items-center justify-between border-b border-line px-3 py-3">
        <div className="flex min-w-0 items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-studio-900 neu-raised-sm text-accent-300"><Icon name="editor" size={15} /></span>
          <div className="min-w-0">
            <h2 className="truncate text-xs font-semibold text-studio-100">Agent Workspace</h2>
            <p className="text-[10px] text-studio-500">{runStatus === "running" ? "Working" : runStatus === "completed" ? "Completed" : runStatus === "error" ? "Failed" : runStatus === "cancelled" ? "Stopped" : "Project files"}</p>
          </div>
        </div>
        <button type="button" onClick={() => { void api.projects.openWorkspace(projectId).catch(() => undefined); }} className="neu-btn rounded-lg p-2 text-studio-400 hover:text-studio-100" aria-label="Open workspace folder" title="Open folder"><Icon name="folder-open" size={14} /></button>
      </header>

      <div className="flex shrink-0 gap-2 px-3 pt-3">
        <button type="button" onClick={() => setTab("preview")} aria-pressed={tab === "preview"} className={`flex flex-1 items-center justify-center gap-2 rounded-lg px-3 py-2 text-xs font-medium ${tab === "preview" ? "neu-selected text-accent-300" : "neu-btn text-studio-400"}`}><Icon name="editor" size={14} />Preview</button>
        <button type="button" onClick={() => setTab("files")} aria-pressed={tab === "files"} className={`flex flex-1 items-center justify-center gap-2 rounded-lg px-3 py-2 text-xs font-medium ${tab === "files" ? "neu-selected text-accent-300" : "neu-btn text-studio-400"}`}><Icon name="folder-open" size={14} />Files</button>
      </div>

      {tab === "preview" ? (
        <div className="flex min-h-0 flex-1 flex-col p-3">
          <div className="mb-2 flex min-w-0 items-center gap-2 text-[10px] text-studio-500">
            <span className="truncate">{selected?.path ?? "Preview"}</span>
            {selected && <span className="shrink-0">{formatBytes(selected.size)}</span>}
          </div>
          <div className="flex min-h-0 flex-1 items-center justify-center overflow-auto rounded-xl bg-studio-950 neu-inset p-3">
            {previewServer?.status === "ready" && previewServer.url ? <iframe title="Running app preview" src={previewServer.url} sandbox="allow-scripts allow-same-origin allow-forms" className="h-full min-h-0 w-full rounded-lg bg-white" /> :
              packageEntry ? <div className="flex max-w-sm flex-col items-center gap-3 text-center">
                <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-studio-900 neu-raised-sm text-accent-300"><Icon name="play" size={22} /></span>
                <p className="text-sm font-medium text-studio-200">{previewServer?.status === "starting" ? "Starting app…" : previewServer?.status === "failed" ? "App preview failed" : "App ready to preview"}</p>
                <p className="text-[11px] text-studio-500">{packageEntry.path}</p>
                {previewServerError && <p role="alert" className="text-[11px] text-red-300">{previewServerError}</p>}
                {previewServer?.log && previewServer.status === "failed" && <pre className="max-h-28 w-full overflow-auto whitespace-pre-wrap break-words rounded-lg bg-studio-900 p-2 text-left font-mono text-[10px] text-studio-400">{previewServer.log}</pre>}
                <div className="flex gap-2">
                  {previewServer?.status !== "ready" && <button type="button" disabled={previewServerBusy || previewServer?.status === "starting"} onClick={() => void startAppPreview()} className="neu-btn rounded-lg px-3 py-2 text-xs text-accent-200 disabled:opacity-50">{previewServerBusy ? "Starting…" : previewServer?.status === "starting" ? "Starting…" : previewServer?.status === "failed" ? "Retry preview" : "Start preview"}</button>}
                  {previewServer?.status === "ready" && <button type="button" disabled={previewServerBusy} onClick={() => void stopAppPreview()} className="neu-btn rounded-lg px-3 py-2 text-xs text-studio-300">Stop preview</button>}
                </div>
                {previewServer?.status === "starting" && <p className="text-[10px] text-studio-600">Waiting for the local server…</p>}
              </div> :
              loadingPreview ? <span className="text-xs text-studio-500">Loading preview…</span> :
              fileError ? <p role="alert" className="max-w-xs text-center text-xs text-red-300">{fileError}</p> :
              !selected ? <div className="text-center"><Icon name="editor" size={25} className="mx-auto mb-3 text-studio-600" /><p className="text-sm font-medium text-studio-300">Nothing to preview</p><p className="mt-1 text-[11px] text-studio-500">Choose a file in Files.</p></div> :
              isImage && previewUrl ? <img src={previewUrl} alt={selected.name} className="max-h-full max-w-full object-contain" /> :
              isVideo && previewUrl ? <video controls src={previewUrl} className="max-h-full max-w-full" /> :
              isAudio && previewUrl ? <audio controls src={previewUrl} className="w-full" /> :
              isPdf && previewUrl ? <iframe title={selected.name} src={previewUrl} className="h-full min-h-0 w-full rounded-lg bg-white" /> :
              isHtml && previewText !== null ? <iframe title={selected.name} srcDoc={previewText} sandbox="allow-scripts" className="h-full min-h-0 w-full rounded-lg bg-white" /> :
              previewText !== null ? <pre className="h-full w-full overflow-auto whitespace-pre-wrap break-words text-left font-mono text-[11px] leading-relaxed text-studio-200">{previewText}{previewText.length >= 1_000_000 ? "\n…preview limited to 1 MB…" : ""}</pre> :
              selected ? <div className="text-center"><Icon name="download" size={22} className="mx-auto mb-2 text-studio-500" /><p className="text-xs text-studio-300">Preview unavailable</p><p className="mt-1 text-[10px] text-studio-500">{selected.name}</p></div> : null}
          </div>
          {selected && <div className="mt-2 flex justify-end"><button type="button" onClick={() => setTab("files")} className="text-[11px] text-accent-300 hover:text-accent-200">View files →</button></div>}
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col gap-3 p-3">
          <div className="flex min-h-0 flex-[3] gap-2 overflow-hidden">
            <div className="flex w-[42%] min-w-0 flex-col overflow-hidden rounded-xl bg-studio-950 neu-inset">
              <div className="flex items-center justify-between px-2.5 py-2 text-[10px] font-semibold uppercase tracking-wider text-studio-500"><span>Project files</span><span>{entries.length}</span></div>
              <div className="min-h-0 flex-1 overflow-auto px-1.5 pb-2">
                {entries.length === 0 ? <p className="px-2 py-3 text-[11px] text-studio-500">No files yet</p> : entries.map((entry) => (
                  <button type="button" key={entry.key} onClick={() => setSelectedKey(entry.key)} title={entry.path} className={`flex w-full min-w-0 items-center gap-2 rounded-md px-2 py-2 text-left text-[11px] ${selectedKey === entry.key ? "neu-selected text-accent-200" : "text-studio-300 hover:bg-white/[0.03]"}`}>
                    <Icon name={entry.artifactId ? "download" : entry.source === "run" ? "play" : "folder-open"} size={13} className="shrink-0 text-studio-500" />
                    <span className="min-w-0 flex-1 truncate">{entry.name}</span>
                    <span className="shrink-0 text-[9px] text-studio-600">{formatBytes(entry.size)}</span>
                  </button>
                ))}
              </div>
            </div>
            <div className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-xl bg-studio-950 neu-inset">
              <div className="flex min-w-0 items-center justify-between gap-2 border-b border-line px-2.5 py-2">
                <span className="truncate text-[10px] text-studio-400">{selected?.path ?? "Select a file"}</span>
                {selected && <button type="button" onClick={() => setTab("preview")} className="shrink-0 text-[10px] text-accent-300">Preview</button>}
              </div>
              <div className="min-h-0 flex-1 overflow-auto p-2.5">
                {loadingPreview ? <span className="text-[11px] text-studio-500">Loading…</span> :
                  fileError ? <p role="alert" className="text-[11px] text-red-300">{fileError}</p> :
                  previewText !== null ? <pre className="whitespace-pre-wrap break-words font-mono text-[10px] leading-relaxed text-studio-200">{previewText}</pre> :
                  selected ? <div className="flex h-full flex-col items-center justify-center text-center"><Icon name="editor" size={20} className="mb-2 text-studio-600" /><p className="text-[11px] text-studio-400">Binary file</p><p className="mt-1 text-[10px] text-studio-600">Open Preview to view it.</p></div> :
                  <p className="text-[11px] text-studio-500">Files created by the agent appear here.</p>}
              </div>
            </div>
          </div>

          <div className="flex min-h-0 flex-[2] flex-col overflow-hidden rounded-xl bg-studio-950 neu-inset">
            <div className="flex items-center justify-between border-b border-line px-2.5 py-2"><span className="text-[10px] font-semibold uppercase tracking-wider text-studio-500">Activity</span><span className="text-[10px] text-studio-600">{runStatus === "running" ? "Live" : runStatus}</span></div>
            <div className="min-h-0 flex-1 overflow-auto p-2">
              {visibleEvents.length === 0 ? <p className="px-1 py-2 text-[11px] text-studio-500">No recent activity</p> : visibleEvents.map((event) => {
                const isError = event.status === "error" || event.type === "approval_requested";
                const isDone = event.type === "span_ended" || event.type === "execution_ended" || event.type === "artifact_persisted";
                return <div key={`${event.execution_id}:${event.seq}`} className="flex items-start gap-2 rounded-md px-1.5 py-2">
                  <span className={`mt-1 h-1.5 w-1.5 shrink-0 rounded-full ${isError ? "bg-red-400" : isDone ? "bg-emerald-400" : "bg-amber-400"}`} />
                  <div className="min-w-0 flex-1"><p className="truncate text-[11px] text-studio-200">{event.name || event.type.replace(/_/g, " ")}</p><p className="mt-0.5 break-words text-[10px] leading-relaxed text-studio-500">{shortEvent(event)}</p></div>
                  <span className="shrink-0 pt-0.5 text-[9px] text-studio-600">{new Date(event.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
                </div>;
              })}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
