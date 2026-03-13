import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/apidocs': 'http://localhost:8000',
      '/openapi.json': 'http://localhost:8000',
    },
  },
})
