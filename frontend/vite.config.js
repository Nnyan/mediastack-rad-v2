import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// The backend serves static files from /app/static which is the
// output of `npm run build`. In dev we proxy API and WebSocket calls
// to a locally running backend (uvicorn on :8090).
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:8090', changeOrigin: true },
      '/ws': {
        target: 'ws://localhost:8090',
        ws: true,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    // Use relative asset paths so the built bundle works regardless
    // of where the backend mounts it.
    assetsDir: 'assets',
  },
})
