import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// Served by Flask under /ide/. Everything (Monaco and its worker included) is bundled: no CDN, no outside requests.
export default defineConfig({
  base: '/ide/',
  plugins: [react()],
  resolve: {
    alias: {
      '@monaco-codicon.css': new URL(
        '../node_modules/monaco-editor/esm/vs/base/browser/ui/codicons/codicon/codicon.css',
        import.meta.url,
      ).pathname,
    },
  },
  worker: { format: 'es' },
  build: { outDir: 'dist', chunkSizeWarningLimit: 4000 },
  server: { proxy: { '/api': 'http://127.0.0.1:5000' } },
});
