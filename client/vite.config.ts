import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  build: {
    chunkSizeWarningLimit: 800,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules')) {
            if (id.includes('@react-three')) {
              return 'react-three';
            }
            if (id.includes('/three')) {
              return 'three';
            }
            if (id.includes('react-dom') || id.includes('/react/')) {
              return 'react';
            }
          }
        },
      },
    },
  },
});
