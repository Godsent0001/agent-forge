import type React from "react";

export interface SegmentOption<T extends string> {
  value: T;
  label: string;
  badge?: string | number;
  icon?: React.ReactNode;
}

export interface SegmentedControlProps<T extends string> {
  options: SegmentOption<T>[];
  value: T;
  onChange: (val: T) => void;
  size?: "sm" | "md";
  className?: string;
}

export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  size = "sm",
  className = "",
}: SegmentedControlProps<T>) {
  return (
    <div
      className={`inline-flex items-center gap-0.5 p-1 bg-studio-900 neu-inset rounded-xl select-none ${className}`}
      role="tablist"
    >
      {options.map((opt) => {
        const isActive = opt.value === value;
        return (
          <button
            key={opt.value}
            type="button"
            role="tab"
            aria-selected={isActive}
            onClick={() => onChange(opt.value)}
            className={`inline-flex items-center gap-1.5 transition-all font-medium rounded-lg cursor-pointer whitespace-nowrap shrink-0 ${
              size === "sm" ? "px-2.5 py-1 text-xs" : "px-3.5 py-1.5 text-xs"
            } ${
              isActive
                ? "neu-accent text-white"
                : "text-studio-400 hover:text-studio-100 hover:bg-studio-850 hover:shadow-neu-xs"
            }`}
          >
            {opt.icon && <span className="shrink-0">{opt.icon}</span>}
            <span>{opt.label}</span>
            {opt.badge !== undefined && (
              <span
                className={`text-2xs font-mono px-1 py-0.2 rounded ${
                  isActive
                    ? "bg-white/20 text-white"
                    : "bg-studio-800 text-studio-400"
                }`}
              >
                {opt.badge}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
