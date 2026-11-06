import { useEffect, useState } from "react";
import { api, type ExecutionArtifact } from "../api/client";
import { ArtifactCard } from "./ArtifactCard";
import { RichMarkdown } from "./RichMarkdown";

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
      if (active) setArtifacts(items.filter((item) => item.artifact_type === "tool_artifact"));
    }).catch(() => {
      if (active) setArtifacts([]);
    });
    return () => { active = false; };
  }, [executionId, content]);

  if (!content && artifacts.length === 0) return null;
  const matches = Array.from(new Set(content.match(FILE_PATH_REGEX) || []));

  return (
    <div className="space-y-3 min-w-0">
      <RichMarkdown content={content} />

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
