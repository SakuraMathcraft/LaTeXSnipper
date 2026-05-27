import basicSsl from "@vitejs/plugin-basic-ssl";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [
    basicSsl({
      name: "latexsnipper-office-dev",
      domains: ["localhost", "127.0.0.1"],
      ttlDays: 3650,
      certDir: ".certs/basic-ssl"
    })
  ],
  server: {
    host: "localhost",
    port: 3000,
    strictPort: true
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: {
      input: {
        taskpane: "taskpane.html",
        dialog: "src/dialog/editorDialog.html",
        help: "help.html"
      }
    }
  }
});
