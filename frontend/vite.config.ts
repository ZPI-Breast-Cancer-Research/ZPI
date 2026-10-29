import { viteCommonjs } from "@originjs/vite-plugin-commonjs";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The app is opened through the gateway (infra/gateway), which serves this dev server and /api
// on one origin, so no dev proxy is configured here.
export default defineConfig({
  // Cornerstone's image codecs are CommonJS + wasm and its decoders run in ES workers
  plugins: [react(), viteCommonjs()],
  optimizeDeps: {
    exclude: ["@cornerstonejs/dicom-image-loader"],
    include: ["dicom-parser"],
  },
  // @icr/polyseg-wasm is an optional Cornerstone add-on (contour/surface conversion) we don't use
  worker: { format: "es", rollupOptions: { external: ["@icr/polyseg-wasm"] } },
  build: { rollupOptions: { external: ["@icr/polyseg-wasm"] } },
  define: { __APP_VERSION__: JSON.stringify(process.env.npm_package_version ?? "dev") },
  server: {
    host: "0.0.0.0",
    port: 5173,
    strictPort: true,
    // File change events don't propagate into docker bind mounts on Windows/macOS.
    watch: { usePolling: process.env.VITE_USE_POLLING === "true" },
  },
});
