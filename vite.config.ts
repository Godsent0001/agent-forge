import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const productionCsp = {
  name: "agentforge-production-csp",
  transformIndexHtml(html: string) {
    const content = [
      "default-src 'self'",
      "connect-src 'self' http://127.0.0.1:* ws://127.0.0.1:*",
      "img-src 'self' data: http://127.0.0.1:*",
      "media-src 'self' http://127.0.0.1:*",
      "style-src 'self' 'unsafe-inline'",
      "font-src 'self' data:",
      "object-src 'none'",
      "base-uri 'self'",
      "frame-ancestors 'none'",
    ].join("; ");
    return html.replace(/<head>/i, `<head><meta http-equiv="Content-Security-Policy" content="${content}">`);
  },
};

export default defineConfig(({ command }) => ({
  plugins: [react(), ...(command === "build" ? [productionCsp] : [])],
  base: "./",
  clearScreen: false,
  server: {
    port: 5173,
    strictPort: true,
    watch: {
      ignored: ["**/python-runtime/**"],
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
}));
