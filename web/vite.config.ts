import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// dev: фронт на :5173 проксирует /api -> бэкенд :8000 (один origin, CORS не нужен)
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': 'http://localhost:8000' },
  },
})
