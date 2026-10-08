import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ArtifactCard } from "./ArtifactCard";

const FILE_PATH_REGEX = /(?:\.\/|\/|[A-Za-z]:\\)[^\s"'<>]+?\.(?:png|jpg|jpeg|gif|webm|mp4|wav|mp3|ogg|json|txt|csv|pdf|srt)/gi;

export function ArtifactViewer({ content }: { content: string }) {
  if (!content) return null;
  const matches = Array.from(new Set(content.match(FILE_PATH_REGEX) || []));

  return (
    <div className="space-y-3 min-w-0">
      <div className="text-sm text-slate-800 leading-relaxed font-sans [&_a]:text-accent-600 [&_a]:underline [&_code]:rounded [&_code]:bg-slate-100 [&_code]:px-1 [&_code]:py-0.5 [&_pre]:overflow-x-auto [&_pre]:rounded-lg [&_pre]:bg-slate-900 [&_pre]:p-3 [&_pre]:text-slate-100 [&_table]:w-full [&_table]:text-xs [&_th]:border [&_th]:border-slate-200 [&_th]:bg-slate-50 [&_th]:p-2 [&_td]:border [&_td]:border-slate-200 [&_td]:p-2">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
      </div>

      {matches.length > 0 && (
        <div className="mt-3 pt-3 border-t border-slate-200/80 space-y-2">
          <p className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
            <span>📁</span> Generated Files & Artifacts
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {matches.map((filepath, idx) => <ArtifactCard key={idx} filepath={filepath} />)}
          </div>
        </div>
      )}
    </div>
  );
}
