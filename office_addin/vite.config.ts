import basicSsl from "@vitejs/plugin-basic-ssl";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [basicSsl()],
  server: {
    host: "localhost",
    port: 3000,
    strictPort: true,
    https: true
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: {
      input: {
        taskpane: "taskpane.html",
        commands: "commands.html"
      }
    }
  }
});
