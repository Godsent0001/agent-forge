import { useEffect, useMemo, useState } from "react";
import { api, type ExecutionSummary, type SystemCheck } from "../api/client";
import { useStore } from "../store/useStore";
import { Button } from "./ui/Button";
import { Icon } from "./ui/Icon";

type Skill = {
  id: string;
  name: string;
  description: string;
  instructions: string;
  assigned_agent_ids: string[];
  enabled: boolean;
  updated_at: string;
};
type WorkspaceTab = "home" | "skills" | "tools" | "debug";

const skillList = (settings: Record<string, unknown> | undefined): Skill[] => {
  const value = settings?.skills;
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is Skill => Boolean(item && typeof item === "object" &&
    typeof (item as Skill).id === "string" && typeof (item as Skill).name === "string" &&
    typeof (item as Skill).instructions === "string"));
};

const makeId = () => globalThis.crypto?.randomUUID?.() ?? `skill-${Date.now()}-${Math.random().toString(16).slice(2)}`;

export function SystemEngineerWorkspace({ onOpenToolCatalog, onOpenChat }: {
  onOpenToolCatalog: () => void;
  onOpenChat: () => void;
}) {
  const project = useStore((s) => s.project);
  const agents = useStore((s) => s.agents);
  const tools = useStore((s) => s.tools);
  const selectedAgentId = useStore((s) => s.selectedAgentId);
  const updateProjectSettings = useStore((s) => s.updateProjectSettings);
  const queueTask = useStore((s) => s.queueTask);
  const [tab, setTab] = useState<WorkspaceTab>("home");
  const [goal, setGoal] = useState("");
  const [skills, setSkills] = useState<Skill[]>([]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [skillName, setSkillName] = useState("");
  const [skillDescription, setSkillDescription] = useState("");
  const [skillInstructions, setSkillInstructions] = useState("");
  const [assignedAgentIds, setAssignedAgentIds] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [checks, setChecks] = useState<SystemCheck[]>([]);
  const [executions, setExecutions] = useState<ExecutionSummary[]>([]);
  const [debugLoading, setDebugLoading] = useState(false);

  useEffect(() => setSkills(skillList(project?.settings)), [project?.id, project?.settings]);
  const selectedAgent = agents.find((agent) => agent.id === selectedAgentId) ?? agents[0];
  const assignedTools = useMemo(() => new Set(selectedAgent?.tool_ids ?? []), [selectedAgent?.tool_ids]);

  const persistSkills = async (next: Skill[]) => {
    if (!project) return;
    setBusy(true);
    setError(null);
    try {
      await updateProjectSettings({ settings: { ...(project.settings ?? {}), skills: next } });
      setSkills(next);
      setNotice("Skills saved. Assigned skills are loaded into RunnerCore when the agent starts a new execution.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save skills.");
    } finally {
      setBusy(false);
    }
  };

  const resetSkillForm = () => {
    setEditingId(null);
    setSkillName("");
    setSkillDescription("");
    setSkillInstructions("");
    setAssignedAgentIds(selectedAgentId ? [selectedAgentId] : []);
  };

  const beginEdit = (skill: Skill) => {
    setEditingId(skill.id);
    setSkillName(skill.name);
    setSkillDescription(skill.description);
    setSkillInstructions(skill.instructions);
    setAssignedAgentIds(skill.assigned_agent_ids ?? []);
    setNotice(null);
    setError(null);
  };

  const saveSkill = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!skillName.trim() || !skillInstructions.trim()) {
      setError("A skill name and instructions are required.");
      return;
    }
    const existing = editingId ? skills.find((skill) => skill.id === editingId) : undefined;
    const nextSkill: Skill = {
      id: editingId ?? makeId(),
      name: skillName.trim(),
      description: skillDescription.trim(),
      instructions: skillInstructions.trim(),
      assigned_agent_ids: assignedAgentIds,
      enabled: existing?.enabled ?? true,
      updated_at: new Date().toISOString(),
    };
    const next = existing
      ? skills.map((skill) => skill.id === existing.id ? nextSkill : skill)
      : [...skills, nextSkill];
    await persistSkills(next);
    resetSkillForm();
  };

  const loadDebugInfo = async () => {
    if (!project) return;
    setDebugLoading(true);
    setError(null);
    try {
      const [nextChecks, nextExecutions] = await Promise.all([
        api.system.check(),
        api.executions.list(project.id, 20),
      ]);
      setChecks(nextChecks);
      setExecutions(nextExecutions);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load diagnostics.");
    } finally {
      setDebugLoading(false);
    }
  };

  const startWithGoal = () => {
    if (!goal.trim() || !selectedAgent) {
      setError(selectedAgent ? "Describe what you want to build first." : "Create or select an agent first.");
      return;
    }
    const task = [
      "Act as a careful systems engineer helping design an AgentForge workflow.",
      "First clarify assumptions if essential information is missing. Otherwise provide a concrete plan with numbered steps, required agents, skills and tools, dependencies, failure handling, and a test plan.",
      "Do not claim to have changed the application, created resources, or run tests unless the available tools actually did so.",
      "",
      "User request:",
      goal.trim(),
    ].join("\n");
    queueTask(selectedAgent.id, task);
    onOpenChat();
  };

  const exportSkills = () => {
    const blob = new Blob([JSON.stringify({ version: 1, skills }, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "agentforge-skills.json";
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const importSkills = async (file?: File) => {
    if (!file) return;
    try {
      const parsed = JSON.parse(await file.text()) as { skills?: unknown };
      if (!Array.isArray(parsed.skills)) throw new Error("Expected a JSON object containing a skills array.");
      const incoming = parsed.skills.map((raw, index) => {
        if (!raw || typeof raw !== "object") throw new Error(`Skill ${index + 1} is invalid.`);
        const value = raw as Partial<Skill>;
        if (typeof value.name !== "string" || typeof value.instructions !== "string") {
          throw new Error(`Skill ${index + 1} must have a name and instructions.`);
        }
        return {
          id: makeId(), name: value.name.trim(), description: value.description ?? "",
          instructions: value.instructions, assigned_agent_ids: [], enabled: value.enabled !== false,
          updated_at: new Date().toISOString(),
        } satisfies Skill;
      });
      await persistSkills([...skills, ...incoming]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not import skills.");
    }
  };

  const navItems: { id: WorkspaceTab; label: string; hint: string }[] = [
    { id: "home", label: "Engineer", hint: "Plan a task" },
    { id: "skills", label: "Skills", hint: `${skills.length} saved` },
    { id: "tools", label: "Tools", hint: `${tools.length} available` },
    { id: "debug", label: "Diagnostics", hint: "Inspect failures" },
  ];

  return (
    <main className="flex h-full min-w-0 flex-1 overflow-hidden bg-studio-950">
      <aside className="hidden w-56 shrink-0 flex-col border-r border-studio-800 bg-studio-900/70 p-3 md:flex">
        <div className="mb-5 px-2 pt-2">
          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-accent-300">AgentForge</div>
          <h1 className="mt-2 text-lg font-semibold text-studio-100">System Engineer</h1>
          <p className="mt-1 text-xs leading-relaxed text-studio-400">Plan, equip, and troubleshoot your agents.</p>
        </div>
        <nav className="space-y-1" aria-label="System Engineer sections">
          {navItems.map((item) => (
            <button key={item.id} onClick={() => { setTab(item.id); setNotice(null); setError(null); if (item.id === "debug") void loadDebugInfo(); }}
              className={`w-full rounded-lg border px-3 py-2.5 text-left transition-colors ${tab === item.id ? "border-accent-500/30 bg-accent-500/10 text-studio-100" : "border-transparent text-studio-400 hover:bg-studio-800 hover:text-studio-100"}`}>
              <span className="block text-sm font-medium">{item.label}</span>
              <span className="mt-0.5 block text-[11px] text-studio-500">{item.hint}</span>
            </button>
          ))}
        </nav>
        <div className="mt-auto rounded-lg border border-studio-700 bg-studio-950/70 p-3">
          <div className="text-xs font-medium text-studio-200">Current agent</div>
          <div className="mt-1 truncate text-sm text-accent-300">{selectedAgent?.name ?? "No agent selected"}</div>
          <p className="mt-1 text-[11px] leading-relaxed text-studio-500">Plans are sent to this agent through the existing execution flow.</p>
        </div>
      </aside>

      <section className="min-w-0 flex-1 overflow-y-auto">
        <header className="sticky top-0 z-10 flex items-center justify-between gap-3 border-b border-studio-800 bg-studio-950/95 px-5 py-4 backdrop-blur">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-accent-300">Workspace / System Engineer</p>
            <h2 className="mt-1 text-lg font-semibold text-studio-100">{navItems.find((item) => item.id === tab)?.label}</h2>
          </div>
          {tab === "skills" && <div className="flex gap-2">
            <label className="cursor-pointer rounded-md border border-studio-700 px-3 py-2 text-xs text-studio-300 hover:bg-studio-800">
              Import JSON<input type="file" accept="application/json,.json" className="hidden" onChange={(event) => { void importSkills(event.target.files?.[0]); event.currentTarget.value = ""; }} />
            </label>
            <Button size="sm" variant="secondary" onClick={exportSkills}>Export</Button>
          </div>}
          {tab === "debug" && <Button size="sm" variant="secondary" onClick={() => void loadDebugInfo()} disabled={debugLoading}>{debugLoading ? "Checking…" : "Refresh checks"}</Button>}
        </header>

        <div className="mx-auto max-w-5xl space-y-5 p-5 md:p-7">
          {notice && <div role="status" className="rounded-lg border border-emerald-800/70 bg-emerald-950/30 px-4 py-3 text-sm text-emerald-300">{notice}</div>}
          {error && <div role="alert" className="rounded-lg border border-red-900/70 bg-red-950/30 px-4 py-3 text-sm text-red-300">{error}</div>}

          {tab === "home" && <>
            <div className="rounded-2xl border border-studio-700 bg-gradient-to-br from-studio-900 to-studio-950 p-6 md:p-8">
              <div className="max-w-2xl">
                <span className="rounded-full border border-accent-500/30 bg-accent-500/10 px-2.5 py-1 text-[11px] font-medium text-accent-300">Guided workflow design</span>
                <h3 className="mt-4 text-2xl font-semibold leading-tight text-studio-100 md:text-3xl">What are you trying to build?</h3>
                <p className="mt-2 text-sm leading-relaxed text-studio-400">Describe the outcome. The selected agent will help draft a plan, including steps, dependencies, tools, failure handling, and tests.</p>
              </div>
              <textarea value={goal} onChange={(event) => setGoal(event.target.value)} rows={5}
                placeholder="Example: Build a research workflow that searches the web, reads uploaded reports, verifies claims, and produces a cited brief…"
                className="mt-6 w-full resize-y rounded-xl border border-studio-700 bg-studio-950 p-4 text-sm text-studio-100 outline-none placeholder:text-studio-600 focus:border-accent-500" />
              <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <p className="text-xs text-studio-500">{selectedAgent ? `Plan will run through ${selectedAgent.name}.` : "Select or create an agent before planning."}</p>
                <Button onClick={startWithGoal} disabled={!goal.trim() || !selectedAgent}>Draft a plan <span className="ml-2">→</span></Button>
              </div>
            </div>
            <div className="grid gap-3 md:grid-cols-3">
              {[
                { title: "Reusable skills", text: "Save procedures once and assign them to the agents that need them.", action: "Manage skills", tab: "skills" as const },
                { title: "Tools", text: "Review the tools already available and attach catalog tools to agents.", action: "Manage tools", tab: "tools" as const },
                { title: "Debug failures", text: "Check runtime health and inspect recent failed executions.", action: "Open diagnostics", tab: "debug" as const },
              ].map((card) => <button key={card.tab} onClick={() => { setTab(card.tab); if (card.tab === "debug") void loadDebugInfo(); }}
                className="rounded-xl border border-studio-800 bg-studio-900/60 p-4 text-left hover:border-studio-600 hover:bg-studio-900">
                <h4 className="text-sm font-semibold text-studio-100">{card.title}</h4><p className="mt-2 min-h-10 text-xs leading-relaxed text-studio-400">{card.text}</p>
                <span className="mt-4 inline-block text-xs font-medium text-accent-300">{card.action} →</span>
              </button>)}
            </div>
          </>}

          {tab === "skills" && <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(300px,0.85fr)]">
            <div className="space-y-3">
              <div><h3 className="text-base font-semibold text-studio-100">Skill library</h3><p className="mt-1 text-xs text-studio-400">A skill is reusable instructions for how an agent should perform a procedure.</p></div>
              {skills.length === 0 && <div className="rounded-xl border border-dashed border-studio-700 p-6 text-center"><div className="text-sm text-studio-200">No skills yet</div><p className="mt-1 text-xs text-studio-500">Create one or import a skills JSON file.</p></div>}
              {skills.map((skill) => <article key={skill.id} className="rounded-xl border border-studio-800 bg-studio-900/60 p-4">
                <div className="flex items-start justify-between gap-3"><div className="min-w-0"><h4 className="truncate text-sm font-semibold text-studio-100">{skill.name}</h4><p className="mt-1 text-xs text-studio-400">{skill.description || "No description"}</p></div><span className="shrink-0 rounded-full bg-studio-800 px-2 py-1 text-[10px] text-studio-400">{(skill.assigned_agent_ids ?? []).length} agents</span></div>
                <p className="mt-3 line-clamp-3 whitespace-pre-wrap text-xs leading-relaxed text-studio-400">{skill.instructions}</p>
                <div className="mt-4 flex gap-2"><Button size="sm" variant="secondary" onClick={() => beginEdit(skill)}>Edit</Button><Button size="sm" variant="secondary" onClick={() => void persistSkills(skills.filter((item) => item.id !== skill.id))} disabled={busy}>Delete</Button></div>
              </article>)}
            </div>
            <form onSubmit={saveSkill} className="h-fit space-y-4 rounded-xl border border-studio-800 bg-studio-900/60 p-4">
              <div><h3 className="text-base font-semibold text-studio-100">{editingId ? "Edit skill" : "Create a skill"}</h3><p className="mt-1 text-xs text-studio-400">Instructions are added to the assigned agent's system context at the next run.</p></div>
              <label className="block text-xs text-studio-300">Name<input value={skillName} onChange={(event) => setSkillName(event.target.value)} maxLength={120} required placeholder="e.g. Verify research claims" className="mt-1.5 w-full rounded-lg border border-studio-700 bg-studio-950 px-3 py-2.5 text-sm text-studio-100 outline-none focus:border-accent-500" /></label>
              <label className="block text-xs text-studio-300">Short description<input value={skillDescription} onChange={(event) => setSkillDescription(event.target.value)} maxLength={500} placeholder="When and why to use this procedure" className="mt-1.5 w-full rounded-lg border border-studio-700 bg-studio-950 px-3 py-2.5 text-sm text-studio-100 outline-none focus:border-accent-500" /></label>
              <label className="block text-xs text-studio-300">Instructions<textarea value={skillInstructions} onChange={(event) => setSkillInstructions(event.target.value)} required rows={8} placeholder="Describe the procedure, decision rules, expected outputs, and how to handle failures…" className="mt-1.5 w-full resize-y rounded-lg border border-studio-700 bg-studio-950 px-3 py-2.5 text-sm leading-relaxed text-studio-100 outline-none focus:border-accent-500" /></label>
              <fieldset><legend className="text-xs text-studio-300">Assign to agents</legend><div className="mt-2 max-h-40 space-y-2 overflow-auto rounded-lg border border-studio-800 p-3">
                {agents.length === 0 && <p className="text-xs text-studio-500">Create an agent first.</p>}
                {agents.map((agent) => <label key={agent.id} className="flex items-center gap-2 text-xs text-studio-300"><input type="checkbox" checked={assignedAgentIds.includes(agent.id)} onChange={(event) => setAssignedAgentIds((current) => event.target.checked ? [...current, agent.id] : current.filter((id) => id !== agent.id))} className="accent-[var(--accent)]" />{agent.name}</label>)}
              </div></fieldset>
              <div className="flex gap-2"><Button type="submit" disabled={busy}>{busy ? "Saving…" : editingId ? "Save changes" : "Create skill"}</Button>{editingId && <Button type="button" variant="secondary" onClick={resetSkillForm}>Cancel</Button>}</div>
            </form>
          </div>}

          {tab === "tools" && <div className="space-y-5">
            <div className="rounded-xl border border-studio-800 bg-studio-900/60 p-5"><h3 className="text-base font-semibold text-studio-100">Tool library</h3><p className="mt-1 max-w-2xl text-sm leading-relaxed text-studio-400">Review project tools and add supported tools from the catalog. Select an agent to see what is attached to it.</p><div className="mt-4"><Button onClick={onOpenToolCatalog}><Icon name="tools" size={15} /> <span className="ml-2">Browse tool catalog</span></Button></div></div>
            <div className="grid gap-3 md:grid-cols-2">
              {tools.map((tool) => <article key={tool.id} className="rounded-xl border border-studio-800 bg-studio-900/60 p-4"><div className="flex items-start justify-between gap-3"><div><h4 className="text-sm font-semibold text-studio-100">{tool.name}</h4><p className="mt-1 text-[11px] text-studio-500">{tool.kind}</p></div><span className={`rounded-full px-2 py-1 text-[10px] ${assignedTools.has(tool.id) ? "bg-emerald-950 text-emerald-300" : "bg-studio-800 text-studio-400"}`}>{assignedTools.has(tool.id) ? "Attached" : "Project only"}</span></div><p className="mt-3 text-xs leading-relaxed text-studio-400">{tool.description || "No description"}</p></article>)}
              {tools.length === 0 && <p className="rounded-xl border border-dashed border-studio-700 p-6 text-sm text-studio-400">No project tools yet. Open the catalog to add one.</p>}
            </div>
            <p className="text-xs leading-relaxed text-studio-500">The custom implementation builder is not enabled in this first slice; this view currently manages registered catalog tools. We will not label a saved definition as executable until RunnerCore can build and validate it.</p>
          </div>}

          {tab === "debug" && <div className="space-y-5">
            <div><h3 className="text-base font-semibold text-studio-100">Runtime checks</h3><p className="mt-1 text-xs text-studio-400">These checks come from the running backend. A green check does not replace an end-to-end execution test.</p></div>
            {debugLoading && <p className="text-sm text-studio-400">Loading runtime diagnostics…</p>}
            {!debugLoading && checks.length === 0 && <div className="rounded-xl border border-dashed border-studio-700 p-5"><p className="text-sm text-studio-300">Run diagnostics to inspect the runtime.</p><Button className="mt-3" size="sm" onClick={() => void loadDebugInfo()}>Run checks</Button></div>}
            {checks.map((check) => <article key={check.name} className="rounded-lg border border-studio-800 bg-studio-900/60 p-4"><div className="flex items-center gap-2"><span className={`h-2 w-2 rounded-full ${check.ok ? "bg-emerald-400" : "bg-red-400"}`} /><h4 className="text-sm font-medium text-studio-100">{check.name}</h4><span className={`ml-auto text-[11px] ${check.ok ? "text-emerald-300" : "text-red-300"}`}>{check.ok ? "OK" : "Needs attention"}</span></div><p className="mt-2 text-xs text-studio-400">{check.detail}</p>{check.fix && <p className="mt-2 text-xs text-accent-300">Suggested fix: {check.fix}</p>}</article>)}
            <div><h3 className="text-base font-semibold text-studio-100">Recent executions</h3><p className="mt-1 text-xs text-studio-400">Failed runs are shown first in the list below when available.</p></div>
            {[...executions].sort((a, b) => Number(b.status === "error") - Number(a.status === "error")).map((run) => <article key={run.id} className="rounded-lg border border-studio-800 bg-studio-900/60 p-4"><div className="flex items-center gap-2"><span className={`rounded px-2 py-1 text-[10px] ${run.status === "error" ? "bg-red-950 text-red-300" : "bg-studio-800 text-studio-300"}`}>{run.status}</span><span className="text-[11px] text-studio-500">{new Date(run.started_at).toLocaleString()}</span></div><p className="mt-2 text-sm text-studio-200">{run.task_preview || "Untitled execution"}</p><p className="mt-2 break-all font-mono text-[10px] text-studio-600">{run.id}</p></article>)}
            {!debugLoading && checks.length > 0 && executions.length === 0 && <p className="text-xs text-studio-500">No executions found for this project.</p>}
          </div>}
        </div>
      </section>
    </main>
  );
}
