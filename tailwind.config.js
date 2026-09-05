/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      // Phase 3 design system. Premium-feel decisions baked in as tokens,
      // not left to per-component ad hoc styling:
      //   - Desaturated near-black surfaces instead of pure #000/#111 grays,
      //     so panels read as "material" rather than "default dark mode".
      //   - A single accent (indigo) used sparingly — restraint is what
      //     reads as premium, not saturation.
      //   - Type scale capped and deliberate; no ad hoc text-[13px] sprinkled
      //     through components.
      colors: {
        surface: {
          950: "#0b0b0f",
          900: "#131317",
          800: "#1b1b21",
          700: "#26262e",
          600: "#34343f",
        },
        accent: {
          500: "#6366f1",
          400: "#818cf8",
          300: "#a5b4fc",
        },
        status: {
          running: "#f59e0b",
          success: "#10b981",
          error: "#ef4444",
          idle: "#52525b",
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
        panel: "0 1px 2px rgba(0,0,0,0.4), 0 8px 24px -8px rgba(0,0,0,0.5)",
      },
      transitionDuration: {
        150: "150ms",
      },
    },
  },
  plugins: [],
};
