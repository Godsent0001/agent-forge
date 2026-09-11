import React from "react";
import { ArtifactCard } from "./ArtifactCard";

const FILE_PATH_REGEX = /(?:\.\/|\/|[A-Za-z]:\\)[^\s"'<>]+?\.(?:png|jpg|jpeg|gif|webm|mp4|wav|mp3|ogg|json|txt|csv|pdf|srt)/gi;

function renderInlineMarkdown(text: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  let keyIdx = 0;
  const pattern = /(`[^`]+`|\*\*[^*]+\*\*|__[^_]+__|\*[^*]+\*|_[^_]+_)/g;
  let match;
  let lastIndex = 0;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }
    const token = match[0];
    if (token.startsWith("`") && token.endsWith("`")) {
      parts.push(
        <code key={keyIdx++} className="bg-slate-100 text-pink-600 px-1 py-0.5 rounded text-xs font-mono">
          {token.slice(1, -1)}
        </code>
      );
    } else if ((token.startsWith("**") && token.endsWith("**")) || (token.startsWith("__") && token.endsWith("__"))) {
      parts.push(
        <strong key={keyIdx++} className="font-bold text-slate-900">
          {token.slice(2, -2)}
        </strong>
      );
    } else if ((token.startsWith("*") && token.endsWith("*")) || (token.startsWith("_") && token.endsWith("_"))) {
      parts.push(
        <em key={keyIdx++} className="italic text-slate-800">
          {token.slice(1, -1)}
        </em>
      );
    }
    lastIndex = pattern.lastIndex;
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  return parts;
}

function TextBlock({ text }: { text: string }) {
  const lines = text.split("\n");
  const renderedElements: React.ReactNode[] = [];
  let key = 0;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    if (line.startsWith("### ")) {
      renderedElements.push(
        <h3 key={key++} className="text-sm font-bold text-slate-900 mt-2 mb-1">
          {renderInlineMarkdown(line.slice(4))}
        </h3>
      );
    } else if (line.startsWith("## ")) {
      renderedElements.push(
        <h2 key={key++} className="text-base font-bold text-slate-900 mt-3 mb-1">
          {renderInlineMarkdown(line.slice(3))}
        </h2>
      );
    } else if (line.startsWith("# ")) {
      renderedElements.push(
        <h1 key={key++} className="text-lg font-extrabold text-slate-900 mt-3 mb-1">
          {renderInlineMarkdown(line.slice(2))}
        </h1>
      );
    } else if (line.trim().startsWith("- ") || line.trim().startsWith("* ")) {
      renderedElements.push(
        <li key={key++} className="ml-4 list-disc text-slate-800 my-0.5">
          {renderInlineMarkdown(line.trim().slice(2))}
        </li>
      );
    } else if (/^\d+\.\s/.test(line.trim())) {
      const match = line.trim().match(/^\d+\.\s/);
      const prefixLength = match ? match[0].length : 3;
      renderedElements.push(
        <li key={key++} className="ml-4 list-decimal text-slate-800 my-0.5">
          {renderInlineMarkdown(line.trim().slice(prefixLength))}
        </li>
      );
    } else if (line.trim() === "") {
      renderedElements.push(<div key={key++} className="h-1" />);
    } else {
      renderedElements.push(
        <p key={key++} className="my-1 leading-normal">
          {renderInlineMarkdown(line)}
        </p>
      );
    }
  }

  return <div>{renderedElements}</div>;
}

function SimpleMarkdown({ content }: { content: string }) {
  if (!content) return null;

  const blocks: React.ReactNode[] = [];
  const codeBlockRegex = /```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g;
  let lastIndex = 0;
  let match;
  let blockKey = 0;

  while ((match = codeBlockRegex.exec(content)) !== null) {
    const textBefore = content.slice(lastIndex, match.index);
    if (textBefore.trim()) {
      blocks.push(<TextBlock key={blockKey++} text={textBefore} />);
    }

    const lang = match[1] || "";
    const codeText = match[2];

    blocks.push(
      <div key={blockKey++} className="my-2 rounded-lg bg-slate-900 text-slate-100 p-3 overflow-x-auto text-xs font-mono shadow-sm border border-slate-800">
        {lang && <div className="text-[10px] text-slate-400 uppercase tracking-wider mb-1 font-semibold">{lang}</div>}
        <pre className="whitespace-pre">{codeText}</pre>
      </div>
    );

    lastIndex = codeBlockRegex.lastIndex;
  }

  const remainingText = content.slice(lastIndex);
  if (remainingText.trim()) {
    blocks.push(<TextBlock key={blockKey++} text={remainingText} />);
  }

  return <div className="space-y-2 text-sm text-slate-800 leading-relaxed font-sans">{blocks}</div>;
}

export function ArtifactViewer({ content }: { content: string }) {
  if (!content) return null;

  const matches = Array.from(new Set(content.match(FILE_PATH_REGEX) || []));

  return (
    <div className="space-y-3 min-w-0">
      <SimpleMarkdown content={content} />

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
