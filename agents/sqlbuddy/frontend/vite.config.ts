import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', 'VITE_')
  return {
    plugins: [react()],
    server: {
      host: '0.0.0.0',
      proxy: { '/api': env.VITE_API_PROXY ?? 'http://localhost:8000' },
    },
  }
})
