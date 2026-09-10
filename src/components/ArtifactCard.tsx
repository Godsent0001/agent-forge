export function ArtifactCard({ filepath }: { filepath: string }) {
  const cleanPath = filepath.trim().replace(/^['"]|['"]$/g, "");
  const filename = cleanPath.split("/").pop() || cleanPath;
  const ext = filename.split(".").pop()?.toLowerCase() || "";

  const fileUrl = cleanPath.startsWith("./output/")
    ? `http://127.0.0.1:8000/files/${cleanPath.replace("./output/", "")}`
    : `http://127.0.0.1:8000/files/${encodeURIComponent(filename)}`;

  const isImage = ["png", "jpg", "jpeg", "gif", "webp"].includes(ext);
  const isVideo = ["mp4", "webm"].includes(ext);
  const isAudio = ["wav", "mp3", "ogg"].includes(ext);

  return (
    <div className="bg-white border border-slate-200 rounded-lg p-2.5 shadow-sm space-y-2">
      <div className="flex items-center justify-between text-xs">
        <span className="font-semibold text-slate-700 truncate max-w-[180px]" title={filename}>
          {filename}
        </span>
        <a
          href={fileUrl}
          target="_blank"
          rel="noreferrer"
          className="text-accent-500 hover:text-accent-400 font-medium hover:underline text-[11px]"
        >
          Open ↗
        </a>
      </div>

      {isImage && (
        <div className="rounded overflow-hidden bg-slate-100 border border-slate-200 max-h-48 flex items-center justify-center">
          <img src={fileUrl} alt={filename} className="max-h-48 object-contain" />
        </div>
      )}

      {isVideo && (
        <div className="rounded overflow-hidden bg-black max-h-48">
          <video controls src={fileUrl} className="w-full max-h-48 object-contain" />
        </div>
      )}

      {isAudio && (
        <div className="pt-1">
          <audio controls src={fileUrl} className="w-full h-8" />
        </div>
      )}

      {!isImage && !isVideo && !isAudio && (
        <div className="bg-slate-50 border border-slate-200 rounded p-2 text-[11px] font-mono text-slate-600 truncate">
          {cleanPath}
        </div>
      )}
    </div>
  );
}
