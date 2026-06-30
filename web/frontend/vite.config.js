import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `base: "./"` makes the built asset paths relative, so the bundle works when
// FastAPI serves it from "/". The dev server proxies /api to the FastAPI app.
export default defineConfig({
  plugins: [react()],
  base: "./",
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
