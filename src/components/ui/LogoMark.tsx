import { useId } from "react";

/**
 * AgentForge app mark: a gradient app-icon tile with a small agent graph
 * (one orchestrator delegating to two workers). Same artwork as public/favicon.svg and build/icon.*.
 */
export function LogoMark({ size = 32, className = "" }: { size?: number; className?: string }) {
  const id = useId().replace(/:/g, "");
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      role="img"
      aria-label="AgentForge"
      className={`shrink-0 ${className}`}
    >
      <defs>
        <linearGradient id={`${id}-bg`} x1="6" y1="4" x2="58" y2="60" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#60a5fa" />
          <stop offset="0.55" stopColor="#2563eb" />
          <stop offset="1" stopColor="#4338ca" />
        </linearGradient>
        <linearGradient id={`${id}-sheen`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#fff" stopOpacity="0.28" />
          <stop offset="1" stopColor="#fff" stopOpacity="0" />
        </linearGradient>
      </defs>
      <rect x="2" y="2" width="60" height="60" rx="15" fill={`url(#${id}-bg)`} />
      <rect x="2" y="2" width="60" height="60" rx="15" fill={`url(#${id}-sheen)`} />
      <g stroke="#fff" strokeWidth="3.4" strokeLinecap="round" fill="none" opacity="0.95">
        <path d="M32 24 L19 43" />
        <path d="M32 24 L45 43" />
      </g>
      <circle cx="32" cy="22" r="8" fill="#fff" />
      <circle cx="32" cy="22" r="3.2" fill="#2563eb" />
      <circle cx="18" cy="45" r="5.6" fill="#fff" fillOpacity="0.95" />
      <circle cx="46" cy="45" r="5.6" fill="#fff" fillOpacity="0.95" />
    </svg>
  );
}
