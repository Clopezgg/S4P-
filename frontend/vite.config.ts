import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'
import { VitePWA } from 'vite-plugin-pwa'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg', 'pwa-icon.svg'],
      manifest: {
        name: 'S4P Enterprise Platform',
        short_name: 'S4P',
        description: 'S4P Enterprise Platform: proyectos, finanzas, operaciones y analítica.',
        theme_color: '#101D35',
        background_color: '#101D35',
        display: 'standalone',
        start_url: '/',
        icons: [
          {
            src: '/pwa-icon.svg',
            sizes: 'any',
            type: 'image/svg+xml',
            purpose: 'any',
          },
          {
            src: '/pwa-icon.svg',
            sizes: 'any',
            type: 'image/svg+xml',
            purpose: 'maskable',
          },
        ],
      },
      workbox: {
        // S4P is an online transactional ERP. Never precache the SPA HTML
        // or JavaScript/CSS application shell: doing so can keep an old bundle
        // alive after a deployment and make it call the obsolete same-origin
        // /api proxy. Static Web Apps owns navigation fallback and HTTP cache
        // headers; the service worker only keeps install metadata/icons.
        globPatterns: ['**/*.{svg,png,webmanifest}'],
        navigateFallback: null,
        cleanupOutdatedCaches: true,
        clientsClaim: true,
        skipWaiting: true,
        runtimeCaching: [
          {
            urlPattern: /\/api\//,
            handler: 'NetworkOnly',
          },
        ],
      },
    }),
  ],
  server: {
    proxy: {
      '/api': {
        target: process.env.VITE_API_PROXY_TARGET ?? 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'happy-dom',
    globals: true,
    setupFiles: ['./tests/setup.ts'],
    css: true,
    exclude: ['**/node_modules/**', 'e2e/**'],
  },
})
