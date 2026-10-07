import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: [
    { find: "@", replacement: path.resolve(__dirname, "./src") },
    { find: /^lucide-react$/, replacement: path.resolve(__dirname, "./src/lib/lucide-react.tsx") },
    { find: "lucide-react-upstream", replacement: path.resolve(__dirname, "./node_modules/lucide-react") },
    { find: /^recharts$/, replacement: path.resolve(__dirname, "./src/lib/recharts.tsx") },
    { find: "recharts-upstream", replacement: path.resolve(__dirname, "./node_modules/recharts") },
  ] },
  server: { host: "127.0.0.1", port: 3000, strictPort: true,
    proxy: { "/api": { target: process.env.API_TARGET ?? "http://127.0.0.1:8001", changeOrigin: false } } },
});
