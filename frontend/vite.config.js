import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/ws':  { target: 'ws://localhost:8000',  ws: true },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    chunkSizeWarningLimit: 1000,
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            {
              name: 'vendor-react',
              test: /node_modules\/(react|react-dom|react-router-dom)/,
            },
            {
              name: 'vendor-recharts',
              test: /node_modules\/recharts/,
            },
            {
              name: 'vendor-xterm',
              test: /node_modules\/xterm/,
            },
            {
              name: 'vendor-lucide',
              test: /node_modules\/lucide-react/,
            },
            {
              name: 'vendor-codemirror',
              test: /node_modules\/(@codemirror|@uiw\/react-codemirror|codemirror)/,
            },
            {
              name: 'vendor-motion',
              test: /node_modules\/framer-motion/,
            },
            {
              name: 'vendor-tanstack',
              test: /node_modules\/@tanstack/,
            },
            {
              name: 'vendor-datefns',
              test: /node_modules\/date-fns/,
            },
            {
              name: 'vendor-others',
              test: /node_modules/,
            },
          ],
        },
      },
    },
  },
});
