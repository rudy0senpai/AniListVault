import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Phase 1 foundation: React + Vite.  The renderer layer is JavaScript
// (React) only; type-strictness can be added in Phase 2 without changing
// the component contract.

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    sourcemap: true,
  },
  server: {
    port: 5173,
    host: true,
  },
});
