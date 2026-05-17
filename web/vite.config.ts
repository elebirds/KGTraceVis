import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiHost = process.env.KGTRACE_API_HOST ?? "127.0.0.1";
const apiPort = process.env.KGTRACE_API_PORT ?? "8001";
const apiProxyTarget = process.env.VITE_API_PROXY_TARGET ?? `http://${apiHost}:${apiPort}`;

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": apiProxyTarget
    }
  }
});
