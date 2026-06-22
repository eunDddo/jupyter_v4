import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// We call the backend directly using the full base URL from `VITE_API_BASE`
// (see src/api.js). A dev proxy for `/api` is also configured below as an
// optional alternative: requests to `/api/*` are forwarded to VITE_API_BASE
// with the `/api` prefix stripped. By default the app uses the full base URL.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const target = env.VITE_API_BASE || 'http://localhost:8000'
  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        '/api': {
          target,
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/api/, ''),
        },
      },
    },
  }
})
