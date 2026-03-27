import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5174,
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/mathlive')) return 'mathlive';
          if (id.includes('node_modules/@cortex-js/compute-engine')) return 'compute-engine';
          if (id.includes('node_modules/@capacitor') || id.includes('node_modules/@capawesome')) {
            return 'capacitor-plugins';
          }
          return undefined;
        },
      },
    },
  },
});