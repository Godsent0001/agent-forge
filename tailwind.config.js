/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        studio: {
          950: "#0b0f17", // Main application shell & canvas background
          900: "#111827", // Primary panel / card surface
          850: "#161f30", // Active item / elevated card
          800: "#1f293d", // Input surface / secondary container
          700: "#2d3a54", // Borders & separators
          600: "#475569", // Muted text / secondary borders
          500: "#64748b", // Subtle details
          400: "#94a3b8", // Secondary text
          300: "#cbd5e1", // Sub-headers
          200: "#e2e8f0",
          100: "#f1f5f9", // Primary text
        },
        surface: {
          950: "#0b0f17",
          900: "#111827",
          850: "#161f30",
          800: "#1f293d",
          700: "#2d3a54",
          600: "#475569",
        },
        accent: {
          600: "#4f46e5",
          500: "#6366f1",
          400: "#818cf8",
          300: "#a5b4fc",
          100: "#e0e7ff",
          900: "rgba(99, 102, 241, 0.15)",
        },
        node: {
          agent: "#3b82f6",
          tool: "#10b981",
          input: "#8b5cf6",
          output: "#f59e0b",
        },
        status: {
          running: "#f59e0b",
          success: "#10b981",
          error: "#ef4444",
          idle: "#64748b",
        },
      },
      fontFamily: {
        sans: ["Inter", "-apple-system", "BlinkMacSystemFont", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "0.875rem" }],
        xs: ["0.75rem", { lineHeight: "1rem" }],
        sm: ["0.8125rem", { lineHeight: "1.25rem" }],
        base: ["0.875rem", { lineHeight: "1.5rem" }],
        lg: ["1rem", { lineHeight: "1.5rem" }],
        xl: ["1.125rem", { lineHeight: "1.75rem" }],
      },
      borderRadius: {
        panel: "0.5rem",
        node: "0.375rem",
      },
      boxShadow: {
        studio: "0 1px 2px 0 rgba(0, 0, 0, 0.3)",
        elevated: "0 10px 15px -3px rgba(0, 0, 0, 0.5), 0 4px 6px -2px rgba(0, 0, 0, 0.3)",
        card: "0 4px 6px -1px rgba(0, 0, 0, 0.3)",
      },
    },
  },
  plugins: [],
};
