import { useStore } from "../store/useStore";

export function WorkflowCanvas() {
  const agents = useStore((s) => s.agents) || [];
  const tools = useStore((s) => s.tools) || [];
  const selectedAgentId = useStore((s) => s.selectedAgentId);
  const selectAgent = useStore((s) => s.selectAgent);

  return (
    <div className="h-full w-full bg-studio-950 bg-grid-pattern relative flex flex-col overflow-hidden select-none">
      {/* Canvas Toolbar Controls */}
      <div className="absolute top-4 left-4 z-10 flex items-center gap-2 bg-studio-900/90 backdrop-blur-sm border border-studio-700/80 rounded-panel p-1.5 shadow-elevated">
        <span className="text-2xs font-mono font-semibold uppercase tracking-wider text-studio-400 px-2">
          Canvas Studio
        </span>
        <div className="h-4 w-px bg-studio-700" />
        <button className="px-2 py-1 text-xs font-mono text-studio-300 hover:text-white hover:bg-studio-800 rounded transition-colors">
          Fit View
        </button>
        <button className="px-2 py-1 text-xs font-mono text-studio-300 hover:text-white hover:bg-studio-800 rounded transition-colors">
          Auto Layout
        </button>
      </div>

      {/* Main Visual Node Workspace */}
      <div className="flex-1 overflow-auto p-12 flex flex-wrap items-start content-start gap-8 min-w-[800px]">
        {agents.length === 0 ? (
          <div className="m-auto text-center max-w-sm py-16">
            <div className="w-12 h-12 rounded-full bg-studio-800 border border-studio-700 flex items-center justify-center mx-auto mb-3 text-studio-400 text-lg">
              ⚙️
            </div>
            <h3 className="text-sm font-semibold text-studio-100 mb-1">No Agents in Canvas</h3>
            <p className="text-xs text-studio-400 leading-relaxed mb-4">
              Create an agent in the Project Explorer sidebar to begin composing your workflow.
            </p>
          </div>
        ) : (
          agents.map((agent) => {
            const isSelected = agent.id === selectedAgentId;
            const attachedTools = tools.filter((t) => agent.tool_ids?.includes(t.id));
            const childAgents = agents.filter((a) => agent.child_agent_ids?.includes(a.id));

            return (
              <div
                key={agent.id}
                onClick={() => selectAgent?.(agent.id)}
                className={`w-72 rounded-panel border transition-all cursor-pointer shadow-elevated bg-studio-900/95 ${
                  isSelected
                    ? "border-accent-500 ring-1 ring-accent-500 shadow-accent-900"
                    : "border-studio-700 hover:border-studio-600"
                }`}
              >
                {/* Node Header */}
                <div className="flex items-center justify-between px-3 py-2.5 border-b border-studio-800 bg-studio-850/50 rounded-t-panel">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="w-2 h-2 rounded-full bg-node-agent shrink-0" />
                    <span className="text-xs font-semibold text-studio-100 truncate">{agent.name}</span>
                  </div>
                  <span className="text-2xs font-mono uppercase bg-studio-800 text-studio-400 px-1.5 py-0.5 rounded border border-studio-700 shrink-0">
                    Agent
                  </span>
                </div>

                {/* Node Body */}
                <div className="p-3 space-y-3 text-xs">
                  <div>
                    <span className="text-2xs font-mono text-studio-500 uppercase block mb-1">Model</span>
                    <span className="font-mono text-studio-300 bg-studio-800 px-2 py-1 rounded block border border-studio-700/60 truncate">
                      {agent.provider} / {agent.model}
                    </span>
                  </div>

                  <div>
                    <span className="text-2xs font-mono text-studio-500 uppercase block mb-1">System Instructions</span>
                    <p className="text-studio-400 text-2xs line-clamp-2 italic bg-studio-950/60 p-2 rounded border border-studio-800">
                      {agent.system_prompt || "No custom instructions specified."}
                    </p>
                  </div>

                  {/* Connected Tools & Sub-Agents */}
                  {(attachedTools.length > 0 || childAgents.length > 0) && (
                    <div className="pt-2 border-t border-studio-800 space-y-1.5">
                      <span className="text-2xs font-mono text-studio-500 uppercase block">Capabilities</span>
                      <div className="flex flex-wrap gap-1">
                        {attachedTools.map((t) => (
                          <span
                            key={t.id}
                            className="text-2xs font-mono bg-emerald-950/50 text-emerald-400 border border-emerald-800/60 px-1.5 py-0.5 rounded"
                          >
                            🛠 {t.name}
                          </span>
                        ))}
                        {childAgents.map((ca) => (
                          <span
                            key={ca.id}
                            className="text-2xs font-mono bg-blue-950/50 text-blue-400 border border-blue-800/60 px-1.5 py-0.5 rounded"
                          >
                            🤖 {ca.name}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
