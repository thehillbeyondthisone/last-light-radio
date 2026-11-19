// UI-only dev preview against the running Film editor service (OPEN_FILM_EDITOR.bat, port 8769).
// Lets styles/markup be iterated with HMR without rebuilding frontend/dist under a live session.
// It proxies /api unchanged; it does not start, restart or reconfigure the Python service.
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const target = 'http://127.0.0.1:8769'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5199,
    strictPort: true,
    proxy: {
      '/api': {
        target,
        changeOrigin: true,
        configure: (proxy) => proxy.on('proxyReq', (request) => {
          request.setHeader('Origin', target)
        }),
      },
    },
  },
})
