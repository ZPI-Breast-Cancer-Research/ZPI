import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The browser calls the backend directly at VITE_API_URL (CORS is enabled on the backend
// via CORS_ALLOWED_ORIGINS), so no dev proxy is configured here.
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
