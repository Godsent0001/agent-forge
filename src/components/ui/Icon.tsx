import type { ReactNode } from "react";
export type IconName = "agents" | "tools" | "settings" | "catalog" | "sidebar-collapse" | "chevron-left" | "chevron-right" | "inspector" | "logs" | "close" | "chat" | "editor" | "play" | "plus" | "workflow";
const glyphs: Record<IconName, ReactNode> = {
  agents: <><circle cx="9" cy="8" r="3" /><path d="M3.5 20v-1.5A4.5 4.5 0 0 1 8 14h2a4.5 4.5 0 0 1 4.5 4.5V20" /><path d="M16 5.5a3 3 0 0 1 0 5.8M17 14h.5a3.5 3.5 0 0 1 3.5 3.5V20" /></>,
  tools: <><path d="M14.5 6.5a4 4 0 0 0-5.3 5.3L3.5 17.5a2.1 2.1 0 0 0 3 3l5.7-5.7a4 4 0 0 0 5.3-5.3l-2.4 2.4-3.1-3.1z" /><path d="m15 5 4-1 1 4" /></>,
  settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 13.5a7.7 7.7 0 0 0 0-3l1.5-1.2-1.7-2.9-1.8.7a7.5 7.5 0 0 0-2.5-1.4L14.6 4h-3.2l-.3 1.7a7.5 7.5 0 0 0-2.5 1.4l-1.8-.7-1.7 2.9 1.5 1.2a7.7 7.7 0 0 0 0 3l-1.5 1.2 1.7 2.9 1.8-.7a7.5 7.5 0 0 0 2.5 1.4l.3 1.7h3.2l.3-1.7a7.5 7.5 0 0 0 2.5-1.4l1.8.7 1.7-2.9z" /></>,
  catalog: <><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16H6.5A2.5 2.5 0 0 0 4 21z" /><path d="M4 5.5v13A2.5 2.5 0 0 1 6.5 16H20M8 7h8M8 10h6" /></>,
  "sidebar-collapse": <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M9 4v16M15 9l-3 3 3 3" /></>,
  "chevron-left": <path d="m15 18-6-6 6-6" />, "chevron-right": <path d="m9 18 6-6-6-6" />,
  inspector: <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M15 4v16M7 8h4M7 12h4" /></>,
  logs: <><path d="M9 5h11M9 12h11M9 19h11" /><circle cx="4.5" cy="5" r=".5" /><circle cx="4.5" cy="12" r=".5" /><circle cx="4.5" cy="19" r=".5" /></>,
  close: <path d="m6 6 12 12M18 6 6 18" />,
  chat: <><path d="M20 11.5a7.5 7.5 0 0 1-8 7.5 8.8 8.8 0 0 1-3.5-.7L4 20l1.5-3.5A7.5 7.5 0 1 1 20 11.5Z" /><path d="M8 11h8M8 14h5" /></>,
  editor: <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M7 8h10M7 12h10M7 16h6" /></>,
  play: <path d="m8 5 11 7-11 7z" />, plus: <path d="M12 5v14M5 12h14" />,
  workflow: <><rect x="3" y="4" width="6" height="6" rx="1" /><rect x="15" y="14" width="6" height="6" rx="1" /><path d="M9 7h4a2 2 0 0 1 2 2v5M12 14l3 3" /></>,
};
export function Icon({ name, size = 18, className = "" }: { name: IconName; size?: number; className?: string }) {
  return <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" className={className}>{glyphs[name]}</svg>;
}
