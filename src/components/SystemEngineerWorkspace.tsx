import { useEffect, useMemo, useState } from "react";
import type React from "react";
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
export function SystemEngineerWorkspace({ onOpenToolCatalog }: { onOpenToolCatalog: () => void }) {
  const project = useStore((s) => s.project);
  const agents = useStore((s) => s.agents);
  const tools = useStore((s) => s.tools);
  const selectedAgentId = useStore((s) => s.selectedAgentId);
  const updateProjectSettings = useStore((s) => s.updateProjectSettings);
  const [tab, setTab] = useState<WorkspaceTab>("home");
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
  const [diagnosingId, setDiagnosingId] = useState<string | null>(null);
  const [customToolName, setCustomToolName] = useState("");
  const [customToolDescription, setCustomToolDescription] = useState("");
  const [customToolUrl, setCustomToolUrl] = useState("");
  const [customToolMethod, setCustomToolMethod] = useState<"GET" | "POST">("POST");
  const [customToolSchema, setCustomToolSchema] = useState("{\n  \"type\": \"object\",\n  \"properties\": {\n    \"query\": { \"type\": \"string\", \"description\": \"The value to send to the endpoint\" }\n  },\n  \"required\": [\"query\"]\n}");

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

  const createCustomTool = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!project || !customToolName.trim() || !customToolDescription.trim() || !customToolUrl.trim()) {
      setError("Tool name, description, and endpoint URL are required.");
      return;
    }
    let inputSchema: Record<string, unknown>;
    try {
      inputSchema = JSON.parse(customToolSchema) as Record<string, unknown>;
    } catch {
      setError("Input JSON Schema is not valid JSON.");
      return;
    }
    if (inputSchema.type !== "object" || !inputSchema.properties || typeof inputSchema.properties !== "object") {
      setError('Input JSON Schema must be an object with type "object" and a properties object.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const created = await api.tools.create({
        project_id: project.id,
        name: customToolName.trim(),
        description: customToolDescription.trim(),
        kind: "custom_http",
        input_schema: inputSchema,
        config: { url: customToolUrl.trim(), method: customToolMethod, input_schema: inputSchema },
      });
      if (selectedAgent) await api.agents.attachTool(selectedAgent.id, created.id);
      const refreshedTools = await api.tools.list(project.id);
      useStore.setState({ tools: refreshedTools });
      setCustomToolName("");
      setCustomToolDescription("");
      setCustomToolUrl("");
      setNotice(selectedAgent
        ? `Custom tool created and attached to ${selectedAgent.name}.`
        : "Custom tool created. Select an agent to attach it.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create the custom HTTP tool.");
    } finally {
      setBusy(false);
    }
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

  const prepareDiagnosis = async (run: ExecutionSummary) => {
    if (diagnosingId) return;
    setDiagnosingId(run.id);
    setError(null);
    setNotice("Loading execution evidence…");
    try {
      const [detail, events] = await Promise.all([
        api.executions.get(run.id),
        api.executions.getEvents(run.id),
      ]);
      const redact = (value: unknown, key = ""): unknown => {
        if (/api.?key|token|secret|password|authorization|credential/i.test(key)) return "[REDACTED]";
        if (typeof value === "string") return value.slice(0, 1200);
        if (Array.isArray(value)) return value.slice(0, 30).map((item) => redact(item));
        if (value && typeof value === "object") return Object.fromEntries(
          Object.entries(value as Record<string, unknown>).map(([childKey, child]) => [childKey, redact(child, childKey)]),
        );
        return value;
      };
      const evidence = {
        execution_id: run.id,
        status: detail.status,
        task: (detail.input_task ?? run.task_preview).slice(0, 2000),
        error: (detail.error ?? "").slice(0, 2000),
        final_output: (detail.final_output ?? "").slice(0, 3000),
        recent_events: events.slice(-30).map((event) => ({
          seq: event.seq,
          type: event.type,
          name: event.name,
          status: event.status,
          data: redact(event.data),
        })),
      };
      window.dispatchEvent(new CustomEvent("agentforge:system-engineer-prompt", {
        detail: {
          prompt: [
            "Diagnose this existing AgentForge execution using the evidence below.",
            "Separate observed facts from hypotheses. Identify the likely failure point, explain why, and use the agentforge_control tool to inspect or make a safe project-level correction if appropriate. Verify any changes.",
            "Execution evidence (sensitive-looking fields were redacted):",
            JSON.stringify(evidence, null, 2).slice(0, 12000),
          ].join("\n"),
        },
      }));
      setNotice("Execution evidence sent to the floating System Engineer.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load execution evidence.");
    } finally {
      setDiagnosingId(null);
    }
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
          <p className="mt-1 text-[11px] leading-relaxed text-studio-500">Model settings are borrowed from this agent. Planning runs through a dedicated System Engineer agent.</p>
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

        <nav className="flex gap-2 overflow-x-auto border-b border-studio-800 px-4 py-2 md:hidden" aria-label="System Engineer sections">
          {navItems.map((item) => <button key={item.id} onClick={() => { setTab(item.id); setNotice(null); setError(null); if (item.id === "debug") void loadDebugInfo(); }} className={`shrink-0 rounded-md border px-3 py-2 text-xs ${tab === item.id ? "border-accent-500/40 bg-accent-500/10 text-accent-200" : "border-studio-800 text-studio-400"}`}>{item.label}</button>)}
        </nav>
        <div className="mx-auto max-w-5xl space-y-5 p-5 md:p-7">
          {notice && <div role="status" className="rounded-lg border border-emerald-800/70 bg-emerald-950/30 px-4 py-3 text-sm text-emerald-300">{notice}</div>}
          {error && <div role="alert" className="rounded-lg border border-red-900/70 bg-red-950/30 px-4 py-3 text-sm text-red-300">{error}</div>}

          {tab === "home" && <div className="space-y-5">
            <div className="rounded-2xl border border-studio-700 bg-studio-900/70 p-6">
              <h3 className="text-xl font-semibold text-studio-100">Project tools and skills</h3>
              <p className="mt-2 max-w-2xl text-sm leading-relaxed text-studio-400">Use the floating System Engineer button to ask for changes in natural language. This workspace is for reviewing reusable skills, configuring custom tools, and inspecting execution failures.</p>
              <div className="mt-4 flex flex-wrap gap-2">
                <Button onClick={() => setTab("skills")}>Manage skills</Button>
                <Button variant="secondary" onClick={() => setTab("tools")}>Manage tools</Button>
                <Button variant="secondary" onClick={() => { setTab("debug"); void loadDebugInfo(); }}>Inspect failures</Button>
              </div>
            </div>
          </div>}

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
            <form onSubmit={createCustomTool} className="grid gap-4 rounded-xl border border-studio-700 bg-studio-900/60 p-5 lg:grid-cols-2">
              <div className="lg:col-span-2"><h3 className="text-base font-semibold text-studio-100">Create custom HTTP tool</h3><p className="mt-1 text-xs leading-relaxed text-studio-400">Create a reusable operation for a public HTTP GET or POST endpoint. The JSON schema becomes the model-visible input form. Requests use the existing SSRF-safe HTTP implementation.</p></div>
              <label className="block text-xs text-studio-300">Tool name<input required maxLength={120} value={customToolName} onChange={(event) => setCustomToolName(event.target.value)} placeholder="e.g. Search public catalogue" className="mt-1.5 w-full rounded-lg border border-studio-700 bg-studio-950 px-3 py-2.5 text-sm text-studio-100 outline-none focus:border-accent-500" /></label>
              <label className="block text-xs text-studio-300">Endpoint URL<input required type="url" value={customToolUrl} onChange={(event) => setCustomToolUrl(event.target.value)} placeholder="https://api.example.com/search" className="mt-1.5 w-full rounded-lg border border-studio-700 bg-studio-950 px-3 py-2.5 text-sm text-studio-100 outline-none focus:border-accent-500" /></label>
              <label className="block text-xs text-studio-300">Method<select value={customToolMethod} onChange={(event) => setCustomToolMethod(event.target.value as "GET" | "POST")} className="mt-1.5 w-full rounded-lg border border-studio-700 bg-studio-950 px-3 py-2.5 text-sm text-studio-100 outline-none focus:border-accent-500"><option value="GET">GET — arguments become query parameters</option><option value="POST">POST — arguments sent as JSON</option></select></label>
              <label className="block text-xs text-studio-300">Description for the agent<input required maxLength={2000} value={customToolDescription} onChange={(event) => setCustomToolDescription(event.target.value)} placeholder="Explain when to use this tool and what it returns" className="mt-1.5 w-full rounded-lg border border-studio-700 bg-studio-950 px-3 py-2.5 text-sm text-studio-100 outline-none focus:border-accent-500" /></label>
              <label className="block text-xs text-studio-300 lg:col-span-2">Input JSON Schema<textarea required rows={8} value={customToolSchema} onChange={(event) => setCustomToolSchema(event.target.value)} spellCheck={false} className="mt-1.5 w-full resize-y rounded-lg border border-studio-700 bg-studio-950 px-3 py-2.5 font-mono text-xs leading-relaxed text-studio-100 outline-none focus:border-accent-500" /></label>
              <div className="flex flex-wrap items-center justify-between gap-3 lg:col-span-2"><p className="max-w-xl text-[11px] leading-relaxed text-studio-500">If an agent is selected, the new tool will be attached immediately. Do not put API keys or secrets in the URL or schema.</p><Button type="submit" disabled={busy}>{busy ? "Creating…" : "Create custom tool"}</Button></div>
            </form>
            <div className="grid gap-3 md:grid-cols-2">
              {tools.map((tool) => <article key={tool.id} className="rounded-xl border border-studio-800 bg-studio-900/60 p-4"><div className="flex items-start justify-between gap-3"><div><h4 className="text-sm font-semibold text-studio-100">{tool.name}</h4><p className="mt-1 text-[11px] text-studio-500">{tool.kind}</p></div><span className={`rounded-full px-2 py-1 text-[10px] ${assignedTools.has(tool.id) ? "bg-emerald-950 text-emerald-300" : "bg-studio-800 text-studio-400"}`}>{assignedTools.has(tool.id) ? "Attached" : "Project only"}</span></div><p className="mt-3 text-xs leading-relaxed text-studio-400">{tool.description || "No description"}</p></article>)}
              {tools.length === 0 && <p className="rounded-xl border border-dashed border-studio-700 p-6 text-sm text-studio-400">No project tools yet. Open the catalog to add one.</p>}
            </div>
            <p className="text-xs leading-relaxed text-studio-500">Custom tools in this version are limited to public HTTP GET/POST endpoints. Authentication secrets, custom headers, OAuth flows, and non-HTTP custom code are not supported by this builder yet.</p>
          </div>}

          {tab === "debug" && <div className="space-y-5">
            <div><h3 className="text-base font-semibold text-studio-100">Runtime checks</h3><p className="mt-1 text-xs text-studio-400">These checks come from the running backend. A green check does not replace an end-to-end execution test.</p></div>
            {debugLoading && <p className="text-sm text-studio-400">Loading runtime diagnostics…</p>}
            {!debugLoading && checks.length === 0 && <div className="rounded-xl border border-dashed border-studio-700 p-5"><p className="text-sm text-studio-300">Run diagnostics to inspect the runtime.</p><Button className="mt-3" size="sm" onClick={() => void loadDebugInfo()}>Run checks</Button></div>}
            {checks.map((check) => <article key={check.name} className="rounded-lg border border-studio-800 bg-studio-900/60 p-4"><div className="flex items-center gap-2"><span className={`h-2 w-2 rounded-full ${check.ok ? "bg-emerald-400" : "bg-red-400"}`} /><h4 className="text-sm font-medium text-studio-100">{check.name}</h4><span className={`ml-auto text-[11px] ${check.ok ? "text-emerald-300" : "text-red-300"}`}>{check.ok ? "OK" : "Needs attention"}</span></div><p className="mt-2 text-xs text-studio-400">{check.detail}</p>{check.fix && <p className="mt-2 text-xs text-accent-300">Suggested fix: {check.fix}</p>}</article>)}
            <div><h3 className="text-base font-semibold text-studio-100">Recent executions</h3><p className="mt-1 text-xs text-studio-400">Failed runs are shown first in the list below when available.</p></div>
            {[...executions].sort((a, b) => Number(b.status === "error") - Number(a.status === "error")).map((run) => <article key={run.id} className="rounded-lg border border-studio-800 bg-studio-900/60 p-4"><div className="flex items-center gap-2"><span className={`rounded px-2 py-1 text-[10px] ${run.status === "error" ? "bg-red-950 text-red-300" : "bg-studio-800 text-studio-300"}`}>{run.status}</span><span className="text-[11px] text-studio-500">{new Date(run.started_at).toLocaleString()}</span></div><p className="mt-2 text-sm text-studio-200">{run.task_preview || "Untitled execution"}</p><p className="mt-2 break-all font-mono text-[10px] text-studio-600">{run.id}</p><div className="mt-3"><Button size="sm" variant="secondary" disabled={Boolean(diagnosingId)} onClick={() => void prepareDiagnosis(run)}>{diagnosingId === run.id ? "Loading evidence…" : "Prepare diagnosis"}</Button></div></article>)}
            {!debugLoading && checks.length > 0 && executions.length === 0 && <p className="text-xs text-studio-500">No executions found for this project.</p>}
          </div>}
        </div>
      </section>
    </main>
  );
}
