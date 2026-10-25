import type React from "react";

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  hint?: string;
}

export function Input({
  label,
  error,
  hint,
  className = "",
  id,
  ...props
}: InputProps) {
  const inputId = id || (label ? label.toLowerCase().replace(/\s+/g, "-") : undefined);

  return (
    <div className="w-full space-y-1">
      {label && (
        <label
          htmlFor={inputId}
          className="block text-2xs font-mono uppercase tracking-wider text-studio-400 select-none"
        >
          {label}
        </label>
      )}
      <input
        id={inputId}
        className={`w-full bg-studio-900 text-studio-100 border rounded-lg px-3 py-2 text-xs font-sans transition-colors placeholder:text-studio-500 focus:outline-none focus:border-accent-500/60 ${
          error ? "border-red-500/70" : "border-transparent"
        } ${className}`}
        {...props}
      />
      {error && <p className="text-2xs text-red-400 font-mono">{error}</p>}
      {hint && !error && <p className="text-2xs text-studio-500">{hint}</p>}
    </div>
  );
}

export interface TextareaProps
  extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
}

export function Textarea({
  label,
  error,
  className = "",
  id,
  ...props
}: TextareaProps) {
  const textareaId = id || (label ? label.toLowerCase().replace(/\s+/g, "-") : undefined);

  return (
    <div className="w-full space-y-1">
      {label && (
        <label
          htmlFor={textareaId}
          className="block text-2xs font-mono uppercase tracking-wider text-studio-400 select-none"
        >
          {label}
        </label>
      )}
      <textarea
        id={textareaId}
        className={`w-full bg-studio-900 text-studio-100 border rounded-lg p-3 text-xs font-mono transition-colors placeholder:text-studio-500 focus:outline-none focus:border-accent-500/60 resize-none ${
          error ? "border-red-500/70" : "border-transparent"
        } ${className}`}
        {...props}
      />
      {error && <p className="text-2xs text-red-400 font-mono">{error}</p>}
    </div>
  );
}
