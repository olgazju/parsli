import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

const BACKEND_URL = process.env.PARSLI_BACKEND_URL ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: BACKEND_URL,
        changeOrigin: true,
      },
    },
  },
});
