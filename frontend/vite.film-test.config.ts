// UI test preview against a throwaway Film service on :8790 (a scratch library, never .local/film-studio).
// Start that service yourself: python -m last_light_radio studio --port 8790 --data <scratch folder>
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const target = 'http://127.0.0.1:8790'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5198,
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
