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
    "inline-flex items-center justify-center gap-1.5 font-medium transition-all select-none focus-visible:outline-2 focus-visible:outline-accent-500 whitespace-nowrap shrink-0 disabled:opacity-40 disabled:pointer-events-none cursor-pointer";

  const sizeClasses = {
    xs: "px-2 py-1 text-2xs rounded-md",
    sm: "px-3 py-1.5 text-xs rounded-lg",
    md: "px-4 py-2 text-sm rounded-xl",
  }[size];

  // Soft UI: controls rise out of the surface and press into it when active.
  const variantClasses = {
    primary:
      "neu-accent text-white hover:brightness-110 active:brightness-95 active:shadow-neu-pressed",
    secondary:
      "bg-studio-850 neu-raised-sm text-studio-100 hover:text-white hover:bg-studio-800 active:shadow-neu-pressed",
    outline:
      "bg-transparent text-studio-300 hover:text-studio-100 border border-line-strong hover:shadow-neu-xs active:shadow-neu-pressed",
    ghost:
      "bg-transparent text-studio-400 hover:text-studio-100 hover:bg-studio-850 hover:shadow-neu-xs active:shadow-neu-pressed",
    danger:
      "bg-red-950/40 neu-raised-sm text-red-300 hover:text-red-200 hover:bg-red-950/60 active:shadow-neu-pressed",
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
