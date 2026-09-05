import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Tauri expects a fixed port and strict-port so the shell doesn't silently
// fall back to a different port during dev.
export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
    watch: {
      // Don't watch the Rust/Python backends, only the frontend
      ignored: ["**/src-tauri/**", "**/python-runtime/**"],
    },
  },
});
