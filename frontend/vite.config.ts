import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'

// base './' keeps asset URLs relative so the build works from any path
// (Vercel root, a sub-folder, or a static file host).
export default defineConfig({
  base: './',
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      // monaco's package exports hide its CSS; editor.api does not pull the icon font in.
      'monaco-codicon.css': fileURLToPath(
        new URL('./node_modules/monaco-editor/esm/vs/base/browser/ui/codicons/codicon/codicon.css', import.meta.url),
      ),
    },
  },
  server: {
    proxy: {
      '/api': { target: process.env.VITE_DEV_API ?? 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
  build: {
    chunkSizeWarningLimit: 4000,
  },
})
