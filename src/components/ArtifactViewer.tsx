import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { api, type ExecutionArtifact } from "../api/client";
import remarkGfm from "remark-gfm";
import { ArtifactCard } from "./ArtifactCard";

const FILE_PATH_REGEX = /(?:\.\/|\/|[A-Za-z]:\\)[^\s"'<>]+?\.(?:png|jpg|jpeg|gif|webm|mp4|wav|mp3|ogg|json|txt|csv|pdf|srt)/gi;

export function ArtifactViewer({ content, executionId }: { content: string; executionId?: string }) {
  const [artifacts, setArtifacts] = useState<ExecutionArtifact[]>([]);

  useEffect(() => {
    let active = true;
    if (!executionId) {
      setArtifacts([]);
      return () => { active = false; };
    }
    void api.artifacts.list(executionId).then((items) => {
      if (active) setArtifacts(items.filter((item) => item.artifact_type !== "tool_result"));
    }).catch(() => {
      if (active) setArtifacts([]);
    });
    return () => { active = false; };
  }, [executionId, content]);

  if (!content && artifacts.length === 0) return null;
  const matches = Array.from(new Set(content.match(FILE_PATH_REGEX) || []));

  return (
    <div className="space-y-3 min-w-0">
      <div className="text-xs sm:text-sm text-studio-100 leading-relaxed font-sans [&_a]:text-accent-400 [&_a]:underline [&_code]:rounded [&_code]:bg-studio-800 [&_code]:text-accent-300 [&_code]:px-1 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-2xs [&_pre]:overflow-x-auto [&_pre]:rounded-md [&_pre]:bg-studio-950 [&_pre]:p-3 [&_pre]:text-studio-200 [&_pre]:border [&_pre]:border-line [&_table]:w-full [&_table]:text-2xs [&_th]:border [&_th]:border-line [&_th]:bg-studio-850 [&_th]:p-2 [&_td]:border [&_td]:border-line [&_td]:p-2">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
      </div>

      {(matches.length > 0 || artifacts.length > 0) && (
        <div aria-label="Files attached to this response" className="mt-3 flex flex-wrap items-start gap-2">
            {matches.map((filepath, idx) => (
              <ArtifactCard key={`file-${idx}`} filepath={filepath} executionId={executionId} />
            ))}
            {artifacts.map((artifact) => (
              <ArtifactCard
                key={`artifact-${artifact.artifact_id}-${artifact.version}`}
                filepath={artifact.name}
                executionId={executionId}
                artifactId={artifact.artifact_id}
                artifactVersion={artifact.version}
              />
            ))}
        </div>
      )}
    </div>
  );
}
