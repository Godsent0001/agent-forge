import { useEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";
import { api } from "../api/client";
import type { ProjectAttachment } from "../types";
import { Icon } from "./ui/Icon";

const MAX_FILE_BYTES = 25 * 1024 * 1024;
const MAX_RUN_BYTES = 100 * 1024 * 1024;
const MAX_RUN_FILES = 20;
const ACCEPTED_EXTENSIONS = ".txt,.py,.md,.csv,.json,.pdf,.png,.jpg,.jpeg,.webp,.wav,.mp3,.mp4,.webm";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function statusLabel(status: ProjectAttachment["status"]): string {
  if (status === "clean") return "Scanned · ready";
  if (status === "unscanned") return "Unscanned · inspection allowed";
  if (status === "rejected") return "Rejected";
  return "Quarantined · scan required";
}

export function ProjectAttachmentsPanel({
  projectId,
  selectedIds,
  onSelectedIdsChange,
  disabled = false,
  compact = false,
}: {
  projectId: string;
  selectedIds: string[];
  onSelectedIdsChange: Dispatch<SetStateAction<string[]>>;
  disabled?: boolean;
  compact?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<ProjectAttachment[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const currentProjectId = useRef(projectId);
  useEffect(() => { currentProjectId.current = projectId; }, [projectId]);

  const refresh = async () => {
    const requestedProjectId = projectId;
    const result = await api.attachments.list(requestedProjectId, 100);
    if (currentProjectId.current !== requestedProjectId) return;
    setItems(result.items);
  };

  useEffect(() => {
    let cancelled = false;
    setItems([]);
    setError(null);
    setNotice(null);
    setLoading(true);
    onSelectedIdsChange([]);
    void api.attachments.list(projectId, 100)
      .then((result) => {
        if (cancelled) return;
        setItems(result.items);
        setError(null);
      })
      .catch((cause) => {
        if (cancelled) return;
        setError(cause instanceof Error ? cause.message : "Could not load project attachments.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
    // Parent state is reset by project/agent switching; this effect intentionally runs only per project.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  const selected = items.filter((item) => selectedIds.includes(item.id) && (item.status === "clean" || item.status === "unscanned"));
  const selectedBytes = selected.reduce((total, item) => total + item.size_bytes, 0);

  const toggleSelection = (item: ProjectAttachment, checked: boolean) => {
    setError(null);
    setNotice(null);
    if (checked) {
      if (item.status !== "clean" && item.status !== "unscanned") return;
      if (selectedIds.length >= MAX_RUN_FILES) {
        setError(`A run can include at most ${MAX_RUN_FILES} files.`);
        return;
      }
      const newBytes = selectedBytes + item.size_bytes;
      if (newBytes > MAX_RUN_BYTES) {
        setError("Selected attachments exceed the 100 MiB combined run limit.");
        return;
      }
      onSelectedIdsChange([...selectedIds, item.id]);
    } else {
      onSelectedIdsChange(selectedIds.filter((id) => id !== item.id));
    }
  };

  const uploadFiles = async (files: FileList | File[]) => {
    if (disabled || uploading || files.length === 0) return;
    setError(null);
    setNotice(null);
    setUploading(true);
    let uploaded = 0;
    let autoSelectedCount = 0;
    let autoSelectedBytes = selectedBytes;
    let autoSelectedFiles = selectedIds.length;
    const autoSelectedIds: string[] = [];
    try {
      for (const file of Array.from(files)) {
        if (file.size > MAX_FILE_BYTES) {
          throw new Error(`${file.name} exceeds the 25 MiB per-file limit.`);
        }
        const extension = file.name.includes(".") ? `.${file.name.split(".").pop()?.toLowerCase()}` : "";
        if (!ACCEPTED_EXTENSIONS.split(",").includes(extension)) {
          throw new Error(`${file.name} has an unsupported file extension.`);
        }
        const item = await api.attachments.upload(projectId, file);
        setItems((current) => [item, ...current.filter((old) => old.id !== item.id)]);
        if (item.status === "clean" || item.status === "unscanned") {
          if (autoSelectedFiles < MAX_RUN_FILES && autoSelectedBytes + item.size_bytes <= MAX_RUN_BYTES) {
            autoSelectedIds.push(item.id);
            autoSelectedFiles += 1;
            autoSelectedBytes += item.size_bytes;
            autoSelectedCount += 1;
          } else {
            setNotice(`${item.name} passed scanning, but was not auto-selected because the run attachment limit would be exceeded.`);
          }
        } else {
          setNotice(`${item.name} was not attached because its status is ${item.status}.`);
        }
        uploaded += 1;
      }
      if (autoSelectedIds.length > 0) {
        onSelectedIdsChange((current) => [...current, ...autoSelectedIds.filter((id) => !current.includes(id))]);
        setNotice(`${autoSelectedCount} file${autoSelectedCount === 1 ? "" : "s"} uploaded and selected for the next run. TXT, Python source, MD, CSV, and JSON can be read directly; other formats require a dedicated parser or multimodal tool.`);
      }
      await refresh();
      if (uploaded > 0 && autoSelectedIds.length === 0) setNotice((current) => current ?? `${uploaded} file${uploaded === 1 ? "" : "s"} uploaded.`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Upload failed.");
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  const rescan = async (item: ProjectAttachment) => {
    setBusyId(item.id);
    setError(null);
    setNotice(null);
    try {
      const result = await api.attachments.scan(projectId, item.id);
      setItems((current) => current.map((old) => old.id === item.id ? result : old));
      if (result.status === "clean") {
        setNotice(`${item.name} passed scanning. Select it below to attach it to a run.`);
      } else if (result.status === "rejected") {
        onSelectedIdsChange(selectedIds.filter((id) => id !== item.id));
        setNotice(`${item.name} was rejected by validation or scanning.`);
      } else {
        setNotice("The scanner is unavailable or returned an uncertain result. The file remains marked unscanned and can be inspected, but must not be treated as trusted code.");
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not rescan this attachment.");
    } finally {
      setBusyId(null);
    }
  };

  const remove = async (item: ProjectAttachment) => {
    if (!window.confirm(`Delete ${item.name} from this project? This cannot be undone.`)) return;
    setBusyId(item.id);
    setError(null);
    setNotice(null);
    try {
      await api.attachments.remove(projectId, item.id);
      setItems((current) => current.filter((old) => old.id !== item.id));
      onSelectedIdsChange(selectedIds.filter((id) => id !== item.id));
      setNotice(`${item.name} deleted.`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not delete this attachment.");
    } finally {
      setBusyId(null);
    }
  };

  const download = async (item: ProjectAttachment) => {
    setBusyId(item.id);
    setError(null);
    try {
      const blob = await api.attachments.download(projectId, item.id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = item.name;
      link.click();
      URL.revokeObjectURL(url);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not download this attachment.");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className={compact ? "flex min-w-0 shrink-0 items-center gap-2" : "w-full"}>
      <div className="flex items-center justify-between gap-3">
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ACCEPTED_EXTENSIONS}
          className="sr-only"
          aria-label="Choose project files to upload"
          onChange={(event) => void uploadFiles(event.currentTarget.files ?? [])}
          disabled={disabled || uploading}
        />
        <button
          type="button"
          onClick={() => compact ? inputRef.current?.click() : setOpen((value) => !value)}
          aria-expanded={compact ? undefined : open}
          aria-controls={compact ? undefined : "project-attachments-panel"}
          aria-label={compact ? "Attach files" : "Open project attachments"}
          title={compact ? "Attach files" : "Project attachments"}
          disabled={disabled || uploading}
          className={compact
            ? "inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-studio-800 text-studio-300 hover:text-white hover:bg-studio-700 disabled:opacity-50"
            : "inline-flex items-center gap-2 neu-btn px-3 py-2 text-xs font-medium text-studio-300 transition-all disabled:opacity-50"}
        >
          <Icon name={uploading ? "loader-circle" : "paperclip"} size={compact ? 17 : 14} />
          {!compact && <>Files · {selectedIds.length}{items.length > 0 ? ` / ${items.length}` : ""}<Icon name={open ? "chevron-up" : "chevron-down"} size={12} /></>}
        </button>
        {selectedIds.length > 0 && (
          <span className="text-2xs font-mono text-studio-400">{formatBytes(selectedBytes)} attached to next run</span>
        )}
      </div>

      {compact && selected.length > 0 && (
        <div className="flex min-w-0 flex-wrap items-center gap-1.5">
          {selected.map((item) => (
            <span key={item.id} title={item.name} className="inline-flex max-w-44 items-center gap-1 rounded-full border border-line bg-studio-950 px-2 py-1 text-[10px] text-studio-300">
              <Icon name="file" size={11} /><span className="truncate">{item.name}</span>
              <button type="button" aria-label={`Remove ${item.name} from next message`} onClick={() => toggleSelection(item, false)} className="ml-0.5 text-studio-500 hover:text-white">×</button>
            </span>
          ))}
        </div>
      )}
      {compact && (error || notice) && (
        <p role={error ? "alert" : "status"} className={`max-w-xs text-[10px] leading-4 ${error ? "text-red-300" : "text-studio-400"}`}>{error || notice}</p>
      )}
      {open && !compact && (
        <section id="project-attachments-panel" aria-label="Project attachments" className="mt-2 rounded-lg border border-line-strong bg-studio-950 p-3">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-3">
            <div>
              <h4 className="text-sm font-semibold text-studio-100">Project files</h4>
              <p className="mt-1 max-w-xl text-2xs leading-5 text-studio-400">
                Valid uploads can be inspected even when antivirus is unavailable. Unscanned files remain marked as untrusted; rejected files cannot be attached.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => inputRef.current?.click()}
                disabled={disabled || uploading}
                className="inline-flex items-center gap-2 rounded-md bg-accent-600 px-3 py-2 text-xs font-semibold text-white hover:bg-accent-500 disabled:opacity-50"
              >
                <Icon name="upload" size={13} /> {uploading ? "Uploading…" : "Upload files"}
              </button>
            </div>
          </div>

          {loading && <p role="status" className="py-3 text-xs text-studio-400">Loading project files…</p>}
          {error && <p role="alert" className="mt-3 rounded border border-red-800 bg-red-950/40 px-3 py-2 text-xs text-red-200">{error}</p>}
          {notice && <p role="status" className="mt-3 rounded border border-line-strong bg-studio-900 px-3 py-2 text-xs text-studio-300">{notice}</p>}

          {!loading && items.length === 0 && !error && (
            <div className="py-6 text-center">
              <Icon name="file-up" size={22} />
              <p className="mt-2 text-xs font-medium text-studio-200">No project files yet</p>
              <p className="mt-1 text-2xs text-studio-500">Add a brief, dataset, image, audio clip, or supported video.</p>
            </div>
          )}

          <ul className="mt-2 divide-y divide-line">
            {items.map((item) => {
              const checked = selectedIds.includes(item.id) && (item.status === "clean" || item.status === "unscanned");
              const busy = uploading || busyId === item.id || disabled;
              return (
                <li key={item.id} className="flex flex-wrap items-center gap-3 py-3">
                  <input
                    type="checkbox"
                    aria-label={`Attach ${item.name} to the next run`}
                    checked={checked}
                    disabled={busy || (item.status !== "clean" && item.status !== "unscanned")}
                    onChange={(event) => toggleSelection(item, event.currentTarget.checked)}
                    className="h-4 w-4 accent-accent-500 disabled:opacity-40"
                  />
                  <div className="min-w-0 flex-1">
                    <p className="break-words text-xs font-medium text-studio-100">{item.name}</p>
                    <p className="mt-1 text-2xs text-studio-500">{formatBytes(item.size_bytes)} · {item.mime}</p>
                  </div>
                  <span
                    className={`rounded border px-2 py-1 text-2xs ${item.status === "clean" ? "border-emerald-800 bg-emerald-950/40 text-emerald-300" : item.status === "rejected" ? "border-red-800 bg-red-950/40 text-red-300" : "border-amber-800 bg-amber-950/40 text-amber-200"}`}
                    title={item.scanned_at ?? "No clean scanner verdict yet"}
                  >
                    {statusLabel(item.status)}
                  </span>
                  <div className="flex items-center gap-1">
                    {(item.status === "clean" || item.status === "unscanned") && (
                      <button type="button" aria-label={`Download ${item.name}`} onClick={() => void download(item)} disabled={busy} className="rounded p-2 text-studio-400 hover:bg-studio-800 hover:text-studio-100 disabled:opacity-40">
                        <Icon name="download" size={13} />
                      </button>
                    )}
                    {(item.status === "quarantined" || item.status === "unscanned") && (
                      <button type="button" aria-label={`Rescan ${item.name}`} onClick={() => void rescan(item)} disabled={busy} className="rounded p-2 text-studio-400 hover:bg-studio-800 hover:text-studio-100 disabled:opacity-40">
                        <Icon name="shield-check" size={13} />
                      </button>
                    )}
                    <button type="button" aria-label={`Delete ${item.name}`} onClick={() => void remove(item)} disabled={busy} className="rounded p-2 text-studio-400 hover:bg-red-950 hover:text-red-200 disabled:opacity-40">
                      <Icon name="trash-2" size={13} />
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </div>
  );
}
