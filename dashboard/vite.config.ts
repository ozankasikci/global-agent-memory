import path from "node:path"
import { fileURLToPath } from "node:url"

import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"
import { defineConfig } from "vite"

const dashboardRoot = path.dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  base: "/ui/",
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(dashboardRoot, "src"),
    },
  },
  build: {
    outDir: path.resolve(dashboardRoot, "../src/global_memory/_dashboard"),
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks: {
          icons: ["@phosphor-icons/react", "lucide-react"],
          primitives: ["radix-ui", "sonner"],
        },
      },
    },
  },
  server: {
    host: "0.0.0.0",
    allowedHosts: ["terminal.local"],
    proxy: {
      "/ui/api": "http://127.0.0.1:8765",
    },
  },
})
