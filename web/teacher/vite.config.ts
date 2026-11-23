import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  base: '/teacher/',
  plugins: [react()],
  build: { outDir: 'dist', chunkSizeWarningLimit: 2000 },
  server: { proxy: { '/api': 'http://127.0.0.1:5000' } },
});
