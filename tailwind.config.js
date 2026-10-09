/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        surface: {
          950: "#f8fafc", // Main canvas / background
          900: "#ffffff", // Primary panel / card surface
          800: "#f1f5f9", // Secondary element / input surface
          700: "#e2e8f0", // Subtle border / hover surface
          600: "#cbd5e1", // Distinct border / neutral text
        },
        accent: {
          500: "#4f46e5", // Indigo primary
          400: "#6366f1", // Hover
          300: "#818cf8", // Soft highlight
          100: "#e0e7ff", // Very soft badge background
        },
        status: {
          running: "#d97706",
          success: "#059669",
          error: "#dc2626",
          idle: "#64748b",
        },
      },
      fontFamily: {
        sans: ["Inter", "-apple-system", "BlinkMacSystemFont", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      fontSize: {
        xs: ["0.75rem", { lineHeight: "1rem" }],
        sm: ["0.8125rem", { lineHeight: "1.25rem" }],
        base: ["0.875rem", { lineHeight: "1.5rem" }],
        lg: ["1rem", { lineHeight: "1.5rem" }],
        xl: ["1.125rem", { lineHeight: "1.75rem" }],
      },
      borderRadius: {
        panel: "0.75rem",
      },
      boxShadow: {
        panel: "0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1)",
        card: "0 4px 6px -1px rgb(0 0 0 / 0.05), 0 2px 4px -2px rgb(0 0 0 / 0.05)",
      },
      transitionDuration: {
        150: "150ms",
      },
    },
  },
  plugins: [],
};
