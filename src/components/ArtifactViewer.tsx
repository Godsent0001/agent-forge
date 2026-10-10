import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ArtifactCard } from "./ArtifactCard";

const FILE_PATH_REGEX = /(?:\.\/|\/|[A-Za-z]:\\)[^\s"'<>]+?\.(?:png|jpg|jpeg|gif|webm|mp4|wav|mp3|ogg|json|txt|csv|pdf|srt)/gi;

export function ArtifactViewer({ content }: { content: string }) {
  if (!content) return null;
  const matches = Array.from(new Set(content.match(FILE_PATH_REGEX) || []));

  return (
    <div className="space-y-3 min-w-0">
      <div className="text-xs sm:text-sm text-studio-100 leading-relaxed font-sans [&_a]:text-accent-400 [&_a]:underline [&_code]:rounded [&_code]:bg-studio-800 [&_code]:text-accent-300 [&_code]:px-1 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-2xs [&_pre]:overflow-x-auto [&_pre]:rounded-md [&_pre]:bg-studio-950 [&_pre]:p-3 [&_pre]:text-studio-200 [&_pre]:border [&_pre]:border-studio-800 [&_table]:w-full [&_table]:text-2xs [&_th]:border [&_th]:border-studio-800 [&_th]:bg-studio-850 [&_th]:p-2 [&_td]:border [&_td]:border-studio-800 [&_td]:p-2">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
      </div>

      {matches.length > 0 && (
        <div className="mt-3 pt-3 border-t border-studio-800 space-y-2">
          <p className="text-2xs font-mono font-semibold uppercase tracking-wider text-studio-400 flex items-center gap-1.5">
            <span>📁</span> Generated Files & Artifacts
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {matches.map((filepath, idx) => (
              <ArtifactCard key={idx} filepath={filepath} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
