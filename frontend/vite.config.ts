/// <reference types="vitest/config" />
import { readFileSync, existsSync } from "node:fs";
import { resolve } from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Em desenvolvimento no browser, o proxy injecta o token do backend do lado do servidor.
// O token nunca é incluído no bundle do frontend.
const tokenFile = resolve(__dirname, "../.dev-token");
const devToken = existsSync(tokenFile) ? readFileSync(tokenFile, "utf8").trim() : "";
const backendPort = process.env.UANJI_PORT ?? "8765";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": resolve(__dirname, "src") } },
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
    host: "127.0.0.1",
    proxy: {
      "/api": {
        target: `http://127.0.0.1:${backendPort}`,
        changeOrigin: true,
        headers: devToken ? { Authorization: `Bearer ${devToken}` } : {},
      },
      "/health": { target: `http://127.0.0.1:${backendPort}`, changeOrigin: true },
    },
  },
  build: {
    // WebView do macOS 14 (Safari 17).
    target: "safari15",
    chunkSizeWarningLimit: 900,
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    // MacBook Air 2015: renderizações com React Flow e páginas lazy podem exceder 5 s em paralelo.
    testTimeout: 20_000,
  },
});
