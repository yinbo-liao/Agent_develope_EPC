import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'path';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '');
  // Local dev backend target. There are two backend entry points:
  //   - backend/dev_main.py (standalone SQLite) listens on 8080 and is what the
  //     endpoint-connectivity suite targets — the default below.
  //   - backend/main.py (PostgreSQL) must be started with `--port 8080` for the
  //     default to work; to point at another port, set VITE_API_PROXY_TARGET,
  //     e.g. VITE_API_PROXY_TARGET=http://127.0.0.1:8000.
  const apiTarget = env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8080';
  const wsTarget = apiTarget.replace(/^http/, 'ws');

  return {
    plugins: [react()],
    resolve: {
      alias: { '@': resolve(__dirname, 'src') },
    },
    server: {
      port: 5173,
      proxy: {
        '/api': {
          target: apiTarget,
          changeOrigin: true,
        },
        '/ws': {
          target: wsTarget,
          ws: true,
          changeOrigin: true,
        },
      },
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks: {
            vendor: ['react', 'react-dom', 'react-router-dom'],
            charts: ['recharts'],
            query: ['@tanstack/react-query'],
            icons: ['lucide-react'],
          },
        },
      },
    },
  };
});
