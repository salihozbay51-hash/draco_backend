import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 3000
  },
  preview: {
    host: "0.0.0.0",
    port: 8080,
    allowedHosts: ["dracofrontend-production.up.railway.app"]
  }
})