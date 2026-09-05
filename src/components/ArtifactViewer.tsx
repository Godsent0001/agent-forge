import { ArtifactCard } from "./ArtifactCard";

const FILE_PATH_REGEX = /(?:\.\/|\/|[A-Za-z]:\\)[^\s"'<>]+?\.(?:png|jpg|jpeg|gif|webm|mp4|wav|mp3|ogg|json|txt|csv|pdf|srt)/gi;

export function ArtifactViewer({ content }: { content: string }) {
  if (!content) return null;

  const matches = Array.from(new Set(content.match(FILE_PATH_REGEX) || []));

  return (
    <div className="space-y-3">
      <div className="whitespace-pre-wrap text-sm text-slate-800 leading-relaxed font-sans">
        {content}
      </div>

      {matches.length > 0 && (
        <div className="mt-3 pt-3 border-t border-slate-200/80 space-y-2">
          <p className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
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
