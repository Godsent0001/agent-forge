import { useEffect, useState } from "react";
import { getApiToken } from "../api/client";
import { useApiBase } from "../api/useApiBase";

export function ArtifactCard({ filepath, executionId, artifactId, artifactVersion }: { filepath: string; executionId?: string; artifactId?: string; artifactVersion?: number }) {
  const cleanPath = filepath.trim().replace(/^['"]|['"]$/g, "");
  const filename = cleanPath.split(/[\\/]/).pop() || cleanPath;
  const ext = filename.split(".").pop()?.toLowerCase() || "";
  const apiBase = useApiBase();
  const [fileToken, setFileToken] = useState("");

  useEffect(() => {
    let active = true;
    void getApiToken().then((token) => {
      if (active) setFileToken(token);
    }).catch(() => {
      if (active) setFileToken("");
    });
    return () => { active = false; };
  }, []);

  const relativePath = cleanPath.startsWith("./output/")
    ? cleanPath.slice("./output/".length)
    : cleanPath.replace(/^\.\//, "");
  const route = executionId
    ? "/v2/executions/" + encodeURIComponent(executionId) + "/files/"
    : "/files/";
  const isRegisteredArtifact = Boolean(executionId && artifactId && artifactVersion);
  const fileUrl = apiBase && fileToken && isRegisteredArtifact
    ? apiBase + "/v2/executions/" + encodeURIComponent(executionId!) +
      "/artifacts/" + encodeURIComponent(artifactId!) + "?version=" + artifactVersion +
      "&token=" + encodeURIComponent(fileToken)
    : apiBase && fileToken && relativePath && !/^[A-Za-z]:[\\/]/.test(relativePath) && !relativePath.startsWith("/")
      ? apiBase + route + relativePath.split(/[\\/]/).map(encodeURIComponent).join("/") +
        "?token=" + encodeURIComponent(fileToken)
      : "";

  const isImage = ["png", "jpg", "jpeg", "gif", "webp"].includes(ext);
  const isVideo = ["mp4", "webm"].includes(ext);
  const isAudio = ["wav", "mp3", "ogg"].includes(ext);

  return (
    <div className="bg-studio-850 border border-studio-700 rounded-md p-2.5 shadow-studio space-y-2 text-xs">
      <div className="flex items-center justify-between">
        <span className="font-medium text-studio-200 truncate max-w-[180px]" title={filename}>
          {filename}
        </span>
        {fileUrl ? (
          <a
            href={fileUrl}
            target="_blank"
            rel="noreferrer"
            className="text-accent-400 hover:text-accent-300 font-mono text-2xs hover:underline"
          >
            Open ↗
          </a>
        ) : (
          <span className="text-2xs font-mono text-studio-500">Loading…</span>
        )}
      </div>

      {isImage && fileUrl && (
        <div className="rounded overflow-hidden bg-studio-900 border border-studio-800 max-h-48 flex items-center justify-center">
          <img src={fileUrl} alt={filename} className="max-h-48 object-contain" />
        </div>
      )}

      {isVideo && fileUrl && (
        <div className="rounded overflow-hidden bg-black max-h-48">
          <video controls src={fileUrl} className="w-full max-h-48 object-contain" />
        </div>
      )}

      {isAudio && fileUrl && (
        <div className="pt-1">
          <audio controls src={fileUrl} className="w-full h-8" />
        </div>
      )}

      {!isImage && !isVideo && !isAudio && (
        <div className="bg-studio-900 border border-studio-800 rounded p-2 text-2xs font-mono text-studio-300 truncate">
          {cleanPath}
        </div>
      )}
    </div>
  );
}
