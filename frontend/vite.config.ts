import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev, the UI runs on Vite's server and proxies to the backend container.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8787",
      "/ws": { target: "ws://127.0.0.1:8787", ws: true },
    },
  },
});
