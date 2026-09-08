import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "./",
  clearScreen: false,
  server: {
    port: 5173,
    strictPort: true,
    watch: {
      // Don't watch the Python runtime directory
      ignored: ["**/python-runtime/**"],
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
