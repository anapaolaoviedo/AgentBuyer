import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      // Las llamadas del frontend a /api/* se reenvían al backend FastAPI.
      // El backend no usa prefijo /api (rutas: /mandates, /verify, ...),
      // así que se quita el prefijo al reenviar:
      //   fetch('/api/mandates')  ->  http://localhost:8000/mandates
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
