import type React from "react";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "outline" | "ghost" | "danger";
  size?: "xs" | "sm" | "md";
  icon?: React.ReactNode;
}

export function Button({
  variant = "secondary",
  size = "sm",
  icon,
  children,
  className = "",
  disabled,
  ...props
}: ButtonProps) {
  const baseClasses =
    "inline-flex items-center justify-center gap-1.5 font-medium transition-colors select-none focus-visible:outline-2 focus-visible:outline-accent-500 whitespace-nowrap shrink-0 disabled:opacity-40 disabled:pointer-events-none cursor-pointer";

  const sizeClasses = {
    xs: "px-2 py-1 text-2xs rounded",
    sm: "px-2.5 py-1.5 text-xs rounded-md",
    md: "px-3.5 py-2 text-sm rounded-md",
  }[size];

  const variantClasses = {
    primary:
      "bg-accent-600 hover:bg-accent-500 active:bg-accent-700 text-white shadow-studio border border-accent-400/30",
    secondary:
      "bg-studio-800 hover:bg-studio-750 active:bg-studio-700 text-studio-100 border border-studio-700 hover:border-studio-600 shadow-studio",
    outline:
      "bg-transparent hover:bg-studio-800/80 active:bg-studio-800 text-studio-300 hover:text-studio-100 border border-studio-700",
    ghost:
      "bg-transparent hover:bg-studio-800/60 active:bg-studio-800 text-studio-400 hover:text-studio-100 border border-transparent",
    danger:
      "bg-red-950/40 hover:bg-red-900/60 active:bg-red-900 text-red-300 border border-red-800/60",
  }[variant];

  return (
    <button
      className={`${baseClasses} ${sizeClasses} ${variantClasses} ${className}`}
      disabled={disabled}
      {...props}
    >
      {icon && <span className="shrink-0">{icon}</span>}
      {children}
    </button>
  );
}
