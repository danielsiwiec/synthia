import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { resolve } from "node:path";

const BACKEND = process.env.SYNTHIA_BACKEND ?? "http://localhost:8003";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: "/static/app/",
  resolve: {
    alias: {
      "@": resolve(import.meta.dirname, "src"),
    },
  },
  build: {
    outDir: resolve(import.meta.dirname, "../synthia/static/app"),
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/chat/threads": { target: BACKEND, changeOrigin: true },
      "/push": { target: BACKEND, changeOrigin: true },
      "/sw.js": { target: BACKEND, changeOrigin: true },
    },
  },
});
