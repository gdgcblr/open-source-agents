import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'path';

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      input: {
        sidepanel: resolve(__dirname, 'src/sidepanel/index.html'),
        background: resolve(__dirname, 'src/background/index.ts'),
        content_meet: resolve(__dirname, 'src/content/meet.ts'),
        content_teams: resolve(__dirname, 'src/content/teams.ts'),
      },
      output: {
        entryFileNames: (chunkInfo) => {
          if (chunkInfo.name === 'background') return 'background.js';
          if (chunkInfo.name === 'content_meet') return 'content_meet.js';
          if (chunkInfo.name === 'content_teams') return 'content_teams.js';
          return 'assets/[name]-[hash].js';
        },
        chunkFileNames: 'chunks/[name]-[hash].js',
        assetFileNames: (assetInfo) => {
          if (assetInfo.name === 'index.html' || assetInfo.name === 'sidepanel.html') {
            return 'sidepanel.html';
          }
          return 'assets/[name]-[hash].[ext]';
        },
      },
    },
  },
});

