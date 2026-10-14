import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { Agent, AgentLesson, AgentMemory, MemoryKind } from "../types";
import { useStore } from "../store/useStore";

type Section = "memory" | "lessons";

export function AgentMemoryPanel({ agent, section }: { agent: Agent; section: Section }) {
  const updateAgent = useStore((state) => state.updateAgent);
  const [memories, setMemories] = useState<AgentMemory[]>([]);
  const [lessons, setLessons] = useState<AgentLesson[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showArchived, setShowArchived] = useState(false);
  const [memoryText, setMemoryText] = useState("");
  const [memoryKind, setMemoryKind] = useState<MemoryKind>("fact");
  const [lessonText, setLessonText] = useState("");
  const [editingMemoryId, setEditingMemoryId] = useState<string | null>(null);
  const [editingMemoryText, setEditingMemoryText] = useState("");
  const [editingLessonId, setEditingLessonId] = useState<string | null>(null);
  const [editingLessonText, setEditingLessonText] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [memoryRows, lessonRows] = await Promise.all([
        api.memory.list(agent.id),
        api.lessons.list(agent.id),
      ]);
      setMemories(memoryRows);
      setLessons(lessonRows);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load agent memory and lessons.");
    } finally {
      setLoading(false);
    }
  }, [agent.id]);

  useEffect(() => { void refresh(); }, [refresh]);

  const changeMemorySetting = async (enabled: boolean) => {
    setSaving(true);
    setError(null);
    try {
      await updateAgent(agent.id, { memory_enabled: enabled });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not update the memory setting.");
    } finally {
      setSaving(false);
    }
  };

  const changeLessonsSetting = async (enabled: boolean) => {
    setSaving(true);
    setError(null);
    try {
      await updateAgent(agent.id, { lessons_enabled: enabled });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not update the lessons setting.");
    } finally {
      setSaving(false);
    }
  };

  const addMemory = async () => {
    const text = memoryText.trim();
    if (!text) return;
    setSaving(true);
    setError(null);
    try {
      const created = await api.memory.create(agent.id, { text, kind: memoryKind });
      setMemories((current) => [created, ...current]);
      setMemoryText("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not save this memory.");
    } finally {
      setSaving(false);
    }
  };

  const saveMemory = async (item: AgentMemory) => {
    const text = editingMemoryText.trim();
    if (!text) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await api.memory.update(agent.id, item.id, { text });
      setMemories((current) => current.map((row) => row.id === updated.id ? updated : row));
      setEditingMemoryId(null);
      setEditingMemoryText("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not update this memory.");
    } finally {
      setSaving(false);
    }
  };

  const patchMemory = async (item: AgentMemory, patch: { pinned?: boolean; status?: AgentMemory["status"] }) => {
    try {
      const updated = await api.memory.update(agent.id, item.id, patch);
      setMemories((current) => current.map((row) => row.id === updated.id ? updated : row));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not update this memory.");
    }
  };

  const deleteMemory = async (item: AgentMemory) => {
    try {
      await api.memory.remove(agent.id, item.id);
      setMemories((current) => current.filter((row) => row.id !== item.id));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not delete this memory.");
    }
  };

  const clearMemory = async () => {
    if (!window.confirm(`Delete all saved memories for ${agent.name}? This cannot be undone.`)) return;
    try {
      await api.memory.clear(agent.id);
      setMemories([]);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not clear agent memory.");
    }
  };

  const addLesson = async () => {
    const text = lessonText.trim();
    if (!text) return;
    setSaving(true);
    setError(null);
    try {
      const created = await api.lessons.create(agent.id, { text });
      setLessons((current) => [created, ...current]);
      setLessonText("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not save this lesson.");
    } finally {
      setSaving(false);
    }
  };

  const saveLesson = async (lesson: AgentLesson) => {
    const text = editingLessonText.trim();
    if (!text) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await api.lessons.update(agent.id, lesson.id, { text });
      setLessons((current) => current.map((row) => row.id === updated.id ? updated : row));
      setEditingLessonId(null);
      setEditingLessonText("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not update this lesson.");
    } finally {
      setSaving(false);
    }
  };

  const patchLessonStatus = async (lesson: AgentLesson) => {
    const status = lesson.status === "active" ? "archived" : "active";
    try {
      const updated = await api.lessons.update(agent.id, lesson.id, { status });
      setLessons((current) => current.map((row) => row.id === updated.id ? updated : row));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not update this lesson.");
    }
  };

  const deleteLesson = async (lesson: AgentLesson) => {
    try {
      await api.lessons.remove(agent.id, lesson.id);
      setLessons((current) => current.filter((row) => row.id !== lesson.id));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not delete this lesson.");
    }
  };

  const filteredMemories = memories.filter((item) => showArchived || item.status === "active");
  const filteredLessons = lessons.filter((item) => showArchived || item.status === "active");

  return (
    <section aria-label={section === "memory" ? "Agent memory" : "Agent lessons"} className="space-y-4">
      {section === "memory" ? (
        <>
          <div className="flex items-start justify-between gap-3 rounded border border-studio-800 bg-studio-950/50 p-3">
            <div>
              <h3 className="font-medium text-studio-100">Persistent memory</h3>
              <p className="mt-1 text-2xs text-studio-500">Active memories can be recalled in future runs. Deleted memories will not be available to the next run.</p>
            </div>
            <input
              aria-label="Enable persistent memory"
              type="checkbox"
              checked={agent.memory_enabled ?? false}
              disabled={saving}
              onChange={(event) => void changeMemorySetting(event.target.checked)}
              className="mt-1 h-4 w-4 accent-accent-500"
            />
          </div>

          <form onSubmit={(event) => { event.preventDefault(); void addMemory(); }} className="space-y-2 rounded border border-studio-800 p-3">
            <label className="block text-2xs font-medium text-studio-300" htmlFor="new-agent-memory">Add a memory (max 200 characters)</label>
            <textarea
              id="new-agent-memory"
              rows={2}
              maxLength={200}
              value={memoryText}
              onChange={(event) => setMemoryText(event.target.value)}
              placeholder="A stable fact, preference, or decision…"
              className="w-full resize-y rounded border border-studio-700 bg-studio-950 px-2.5 py-2 text-xs text-studio-100"
            />
            <div className="flex flex-wrap items-center justify-between gap-2">
              <select aria-label="Memory kind" value={memoryKind} onChange={(event) => setMemoryKind(event.target.value as MemoryKind)} className="rounded border border-studio-700 bg-studio-950 px-2 py-1.5 text-xs">
                <option value="fact">Fact</option><option value="preference">Preference</option><option value="decision">Decision</option>
              </select>
              <button type="submit" disabled={saving || !memoryText.trim()} className="rounded border border-studio-700 bg-studio-800 px-3 py-1.5 text-2xs text-studio-100 hover:bg-studio-700 disabled:opacity-50">Add memory</button>
            </div>
          </form>

          <div className="flex items-center justify-between gap-3">
            <span className="text-2xs text-studio-400">{filteredMemories.length} {showArchived ? "memory items" : "active memories"}</span>
            <div className="flex gap-2">
              <button type="button" onClick={() => setShowArchived((current) => !current)} className="text-2xs text-studio-400 hover:text-studio-100">{showArchived ? "Hide archived" : "Show archived"}</button>
              <button type="button" onClick={() => void clearMemory()} disabled={saving || memories.length === 0} className="text-2xs text-red-300 hover:text-red-200 disabled:opacity-50">Clear all</button>
            </div>
          </div>

          {loading ? <p role="status" className="text-2xs text-studio-500">Loading memories…</p> : filteredMemories.length === 0 ? (
            <p className="rounded border border-dashed border-studio-800 p-4 text-2xs text-studio-500">No saved memory yet. Add a stable fact or preference, or enable memory for future runs.</p>
          ) : (
            <div className="space-y-2">
              {filteredMemories.map((item) => (
                <article key={item.id} className="rounded border border-studio-800 bg-studio-950/40 p-3">
                  {editingMemoryId === item.id ? (
                    <div className="space-y-2">
                      <textarea aria-label="Edit memory text" maxLength={200} rows={2} value={editingMemoryText} onChange={(event) => setEditingMemoryText(event.target.value)} className="w-full rounded border border-studio-700 bg-studio-950 px-2 py-2 text-xs" />
                      <div className="flex gap-2"><button type="button" disabled={saving || !editingMemoryText.trim()} onClick={() => void saveMemory(item)} className="text-2xs text-accent-300">Save</button><button type="button" onClick={() => setEditingMemoryId(null)} className="text-2xs text-studio-400">Cancel</button></div>
                    </div>
                  ) : <p className="break-words text-xs leading-5 text-studio-200">{item.text}</p>}
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-2xs text-studio-500">
                    <span className="rounded border border-studio-800 px-1.5 py-0.5">{item.kind}</span>
                    <span>{item.source_type.replace("_", " ")}</span>
                    <span>{new Date(item.created_at).toLocaleDateString()}</span>
                    {item.status !== "active" && <span className="text-amber-300">{item.status}</span>}
                    <span className="ml-auto flex flex-wrap gap-2">
                      <button type="button" aria-pressed={item.pinned} onClick={() => void patchMemory(item, { pinned: !item.pinned })} className={item.pinned ? "text-accent-300" : "text-studio-400"}>{item.pinned ? "Unpin" : "Pin"}</button>
                      {editingMemoryId !== item.id && <button type="button" onClick={() => { setEditingMemoryId(item.id); setEditingMemoryText(item.text); }} className="text-studio-300">Edit</button>}
                      <button type="button" onClick={() => void patchMemory(item, { status: item.status === "active" ? "archived" : "active" })} className="text-studio-300">{item.status === "active" ? "Archive" : "Restore"}</button>
                      <button type="button" onClick={() => void deleteMemory(item)} className="text-red-300">Delete</button>
                    </span>
                  </div>
                </article>
              ))}
            </div>
          )}
        </>
      ) : (
        <>
          <div className="flex items-start justify-between gap-3 rounded border border-studio-800 bg-studio-950/50 p-3">
            <div>
              <h3 className="font-medium text-studio-100">Lessons</h3>
              <p className="mt-1 text-2xs text-studio-500">Active lessons can guide future runs. Archive or edit them whenever they stop being useful.</p>
            </div>
            <input
              aria-label="Enable lessons"
              type="checkbox"
              checked={agent.lessons_enabled ?? false}
              disabled={saving}
              onChange={(event) => void changeLessonsSetting(event.target.checked)}
              className="mt-1 h-4 w-4 accent-accent-500"
            />
          </div>

          <form onSubmit={(event) => { event.preventDefault(); void addLesson(); }} className="space-y-2 rounded border border-studio-800 p-3">
            <label className="block text-2xs font-medium text-studio-300" htmlFor="new-agent-lesson">Add a lesson (max 300 characters)</label>
            <textarea id="new-agent-lesson" rows={2} maxLength={300} value={lessonText} onChange={(event) => setLessonText(event.target.value)} placeholder="A reusable lesson learned from a task…" className="w-full resize-y rounded border border-studio-700 bg-studio-950 px-2.5 py-2 text-xs text-studio-100" />
            <div className="flex justify-end"><button type="submit" disabled={saving || !lessonText.trim()} className="rounded border border-studio-700 bg-studio-800 px-3 py-1.5 text-2xs text-studio-100 hover:bg-studio-700 disabled:opacity-50">Add lesson</button></div>
          </form>

          <div className="flex items-center justify-between gap-3">
            <span className="text-2xs text-studio-400">{filteredLessons.length} {showArchived ? "lesson items" : "active lessons"}</span>
            <button type="button" onClick={() => setShowArchived((current) => !current)} className="text-2xs text-studio-400 hover:text-studio-100">{showArchived ? "Hide archived" : "Show archived"}</button>
          </div>

          {loading ? <p role="status" className="text-2xs text-studio-500">Loading lessons…</p> : filteredLessons.length === 0 ? (
            <p className="rounded border border-dashed border-studio-800 p-4 text-2xs text-studio-500">No lessons saved yet.</p>
          ) : (
            <div className="space-y-2">
              {filteredLessons.map((lesson) => (
                <article key={lesson.id} className="rounded border border-studio-800 bg-studio-950/40 p-3">
                  {editingLessonId === lesson.id ? (
                    <div className="space-y-2">
                      <textarea aria-label="Edit lesson text" maxLength={300} rows={2} value={editingLessonText} onChange={(event) => setEditingLessonText(event.target.value)} className="w-full rounded border border-studio-700 bg-studio-950 px-2 py-2 text-xs" />
                      <div className="flex gap-2"><button type="button" disabled={saving || !editingLessonText.trim()} onClick={() => void saveLesson(lesson)} className="text-2xs text-accent-300">Save</button><button type="button" onClick={() => setEditingLessonId(null)} className="text-2xs text-studio-400">Cancel</button></div>
                    </div>
                  ) : <p className="break-words text-xs leading-5 text-studio-200">{lesson.text}</p>}
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-2xs text-studio-500">
                    <span className="rounded border border-studio-800 px-1.5 py-0.5">{lesson.status}</span>
                    <span>Score {lesson.score.toFixed(2)}</span>
                    <span>{new Date(lesson.created_at).toLocaleDateString()}</span>
                    <span className="ml-auto flex gap-2">
                      {editingLessonId !== lesson.id && <button type="button" onClick={() => { setEditingLessonId(lesson.id); setEditingLessonText(lesson.text); }} className="text-studio-300">Edit</button>}
                      <button type="button" onClick={() => void patchLessonStatus(lesson)} className="text-studio-300">{lesson.status === "active" ? "Archive" : "Restore"}</button>
                      <button type="button" onClick={() => void deleteLesson(lesson)} className="text-red-300">Delete</button>
                    </span>
                  </div>
                </article>
              ))}
            </div>
          )}

          {agent.learned_experience?.trim() && (
            <section aria-label="Legacy notes not used by the v2 Runner" className="space-y-2 border-t border-studio-800 pt-3">
              <h3 className="text-xs font-medium text-studio-300">Legacy notes (not used by the v2 Runner)</h3>
              <p className="text-2xs text-studio-500">Read-only notes retained for compatibility with older runtime data.</p>
              <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded border border-studio-800 bg-studio-950 p-3 font-mono text-2xs text-studio-400">{agent.learned_experience}</pre>
            </section>
          )}
        </>
      )}

      {error && <p role="alert" className="rounded border border-red-800 bg-red-950/30 p-3 text-2xs text-red-200">{error}</p>}
      {saving && <p role="status" className="text-2xs text-studio-500">Saving changes…</p>}
    </section>
  );
}
