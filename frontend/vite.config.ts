import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The app is opened through the gateway (infra/gateway), which serves this dev server and /api
// on one origin, so no dev proxy is configured here.
export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    strictPort: true,
    // File change events don't propagate into docker bind mounts on Windows/macOS.
    watch: { usePolling: process.env.VITE_USE_POLLING === "true" },
  },
});
