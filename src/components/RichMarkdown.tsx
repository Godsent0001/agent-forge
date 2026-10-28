import { Children, isValidElement, type ReactElement, type ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

type DiagramNode = { id: string; label: string };
type DiagramEdge = { from: string; to: string; label?: string };

function mermaidParts(source: string): { nodes: DiagramNode[]; edges: DiagramEdge[]; direction: "LR" | "TB" } {
  const nodes = new Map<string, string>();
  const edges: DiagramEdge[] = [];
  const lines = source.split("\n").map((line) => line.trim()).filter((line) => line && !line.startsWith("%%"));
  const direction: "LR" | "TB" = lines.some((line) => /^(flowchart|graph)\s+LR\b/i.test(line)) ? "LR" : "TB";
  const tokenPattern = "([A-Za-z][A-Za-z0-9_-]*(?:\\[[^\\]]*\\]|\\([^)]*\\)|\\{[^}]*\\})?)";
  const edgePattern = new RegExp("^" + tokenPattern + "\\s*(?:-->|---|==>|-.->)(?:\\|([^|]*)\\|)?\\s*" + tokenPattern);
  const addNode = (token: string) => {
    const match = /^([A-Za-z][A-Za-z0-9_-]*)(?:\\[([^\\]]*)\\]|\\(([^)]*)\\)|\\{([^}]*)\\})?$/.exec(token.trim());
    if (!match) return;
    const id = match[1];
    const label = (match[2] ?? match[3] ?? match[4] ?? id).trim();
    if (!nodes.has(id)) nodes.set(id, label || id);
  };
  for (const line of lines) {
    if (/^(flowchart|graph)\b/i.test(line) || line.startsWith("subgraph ") || line === "end") continue;
    const edge = edgePattern.exec(line);
    if (edge) {
      addNode(edge[1]);
      addNode(edge[3]);
      edges.push({ from: edge[1].match(/^[A-Za-z][A-Za-z0-9_-]*/)?.[0] ?? edge[1], to: edge[3].match(/^[A-Za-z][A-Za-z0-9_-]*/)?.[0] ?? edge[3], label: edge[2]?.trim() || undefined });
      continue;
    }
    const declaration = /^([A-Za-z][A-Za-z0-9_-]*(?:\\[[^\\]]*\\]|\\([^)]*\\)|\\{[^}]*\\})?)/.exec(line);
    if (declaration) addNode(declaration[1]);
  }
  return { nodes: [...nodes].map(([id, label]) => ({ id, label })), edges, direction };
}

function MermaidDiagram({ source }: { source: string }) {
  const { nodes, edges, direction } = mermaidParts(source);
  if (!nodes.length) {
    return <pre className="overflow-x-auto rounded-md border border-line bg-studio-950 p-3 text-xs text-studio-300">{source}</pre>;
  }
  const nodeW = 184;
  const nodeH = 54;
  const gap = 48;
  const width = direction === "LR" ? 48 + nodes.length * (nodeW + gap) : 640;
  const height = direction === "LR" ? 180 : 40 + nodes.length * (nodeH + gap);
  const positions = new Map(nodes.map((node, index) => [node.id, direction === "LR"
    ? { x: 24 + index * (nodeW + gap), y: (height - nodeH) / 2 }
    : { x: (width - nodeW) / 2, y: 20 + index * (nodeH + gap) }]));
  return (
    <div className="my-3 max-w-full overflow-x-auto rounded-xl border border-line bg-studio-950 p-3" role="img" aria-label="Rendered Mermaid flowchart">
      <svg width={width} height={height} viewBox={"0 0 " + width + " " + height} role="presentation" className="max-w-none">
        <defs><marker id="mermaid-arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><path d="M0,0 L0,6 L6,3 z" fill="currentColor" /></marker></defs>
        {edges.map((edge, index) => {
          const from = positions.get(edge.from);
          const to = positions.get(edge.to);
          if (!from || !to) return null;
          const x1 = from.x + (direction === "LR" ? nodeW : nodeW / 2);
          const y1 = from.y + (direction === "LR" ? nodeH / 2 : nodeH);
          const x2 = to.x + (direction === "LR" ? 0 : nodeW / 2);
          const y2 = to.y + (direction === "LR" ? nodeH / 2 : 0);
          return <g key={index}><line x1={x1} y1={y1} x2={x2} y2={y2} stroke="currentColor" strokeOpacity="0.6" strokeWidth="1.5" markerEnd="url(#mermaid-arrow)" />{edge.label && <text x={(x1 + x2) / 2} y={(y1 + y2) / 2 - 5} fontSize="10" fill="currentColor" textAnchor="middle">{edge.label}</text>}</g>;
        })}
        {nodes.map((node) => {
          const p = positions.get(node.id)!;
          const label = node.label.length > 28 ? node.label.slice(0, 25) + "…" : node.label;
          return <g key={node.id}><rect x={p.x} y={p.y} width={nodeW} height={nodeH} rx="10" fill="#202734" stroke="#64748b" /><text x={p.x + nodeW / 2} y={p.y + 23} textAnchor="middle" fontSize="11" fill="#f1f5f9">{label}</text><text x={p.x + nodeW / 2} y={p.y + 40} textAnchor="middle" fontSize="9" fill="#94a3b8">{node.id}</text></g>;
        })}
      </svg>
      <p className="mt-1 text-[10px] text-studio-500">Mermaid flowchart · {nodes.length} nodes · {edges.length} connections</p>
    </div>
  );
}

function DataChart({ source }: { source: string }) {
  try {
    const parsed = JSON.parse(source) as Record<string, unknown>;
    const rows = Array.isArray(parsed.data) ? parsed.data as Record<string, unknown>[] : [];
    const series = Array.isArray(parsed.series) ? parsed.series as Record<string, unknown>[] : [];
    const xKey = typeof parsed.xKey === "string" ? parsed.xKey : "x";
    const yKey = typeof series[0]?.dataKey === "string" ? series[0].dataKey as string : "y";
    const labels = Array.isArray(parsed.labels) ? parsed.labels.map(String) : rows.map((row) => String(row[xKey] ?? ""));
    const values = Array.isArray(parsed.values) ? parsed.values.map(Number) : rows.map((row) => Number(row[yKey] ?? 0));
    if (!labels.length || labels.length !== values.length || values.some((value) => !Number.isFinite(value))) throw new Error("Expected labels and numeric values of equal length.");
    const width = Math.max(360, labels.length * 76 + 48);
    const height = 240;
    const left = 36, top = 24, plotW = width - 56, plotH = 160;
    const max = Math.max(1, ...values.map(Math.abs));
    const bar = String(parsed.type ?? parsed.chartType ?? "bar").toLowerCase() !== "line";
    const points = values.map((value, index) => ({ x: left + (index + 0.5) * plotW / values.length, y: top + plotH - (value / max) * plotH }));
    return (
      <div className="my-3 max-w-full overflow-x-auto rounded-xl border border-line bg-studio-950 p-3" role="img" aria-label={String(parsed.title ?? "Data chart")}>
        {typeof parsed.title === "string" && <p className="mb-2 text-xs font-semibold text-studio-100">{parsed.title}</p>}
        <svg width={width} height={height} viewBox={"0 0 " + width + " " + height}>
          <line x1={left} y1={top + plotH} x2={width - 12} y2={top + plotH} stroke="currentColor" strokeOpacity=".5" />
          {bar ? values.map((value, index) => {
            const bw = Math.max(8, plotW / values.length * 0.58);
            const point = points[index];
            return <g key={index}><rect x={point.x - bw / 2} y={point.y} width={bw} height={top + plotH - point.y} rx="3" fill="#60a5fa" /><text x={point.x} y={point.y - 5} fontSize="10" textAnchor="middle" fill="currentColor">{value}</text></g>;
          }) : <polyline points={points.map((point) => point.x + "," + point.y).join(" ")} fill="none" stroke="#60a5fa" strokeWidth="2.5" />}
          {points.map((point, index) => <g key={index}>{!bar && <circle cx={point.x} cy={point.y} r="3.5" fill="#60a5fa" />}<text x={point.x} y={top + plotH + 18} fontSize="10" textAnchor="middle" fill="currentColor">{labels[index].slice(0, 12)}</text></g>)}
        </svg>
      </div>
    );
  } catch {
    return <pre className="overflow-x-auto rounded-md border border-line bg-studio-950 p-3 text-xs text-studio-300">{source}</pre>;
  }
}

const markdownComponents: Components = {
  pre({ children }) {
    const child = Children.toArray(children).find(isValidElement);
    if (child && child.type === "code") {
      const code = child as ReactElement<{ className?: string; children?: ReactNode }>;
      const language = /language-([\w-]+)/.exec(code.props.className ?? "")?.[1]?.toLowerCase();
      const source = String(code.props.children ?? "").replace(/\n$/, "");
      if (language === "mermaid") return <MermaidDiagram source={source} />;
      if (language === "chart" || language === "graph-data") return <DataChart source={source} />;
    }
    return <pre className="overflow-x-auto rounded-md border border-line bg-studio-950 p-3 text-studio-200">{children}</pre>;
  },
};

export function RichMarkdown({ content }: { content: string }) {
  return (
    <div className="text-xs sm:text-sm text-studio-100 leading-relaxed font-sans [&_a]:text-accent-400 [&_a]:underline [&_code]:rounded [&_code]:bg-studio-800 [&_code]:text-accent-300 [&_code]:px-1 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-2xs [&_table]:w-full [&_table]:text-2xs [&_th]:border [&_th]:border-line [&_th]:bg-studio-850 [&_th]:p-2 [&_td]:border [&_td]:border-line [&_td]:p-2">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>{content}</ReactMarkdown>
    </div>
  );
}
