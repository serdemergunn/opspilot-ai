/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The browser only ever talks to the .NET API (ADR 0002). In development Vite proxies /api to it,
// so there is a single origin and no CORS configuration to maintain.
export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: { "/api": process.env.OPSPILOT_API_URL ?? "http://127.0.0.1:8080" },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          react: ["react", "react-dom", "react-router-dom", "@tanstack/react-query"],
          charts: ["recharts"],
        },
      },
    },
  },
  test: { environment: "node" },
});
