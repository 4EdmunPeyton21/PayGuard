import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Backend runs on 8080 (8000 is taken by DynamoDB Local, see docker-compose.yml)
    proxy: {
      '/api': 'http://localhost:8080',
    },
  },
})
