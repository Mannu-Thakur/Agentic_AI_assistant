import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    host: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
        secure: false,
        // Forward cookies between browser and backend through the proxy
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes) => {
            // Allow Set-Cookie headers to reach the browser
            const setCookie = proxyRes.headers['set-cookie'];
            if (setCookie) {
              proxyRes.headers['set-cookie'] = setCookie.map((cookie: string) =>
                cookie.replace(/; SameSite=None/gi, '; SameSite=Lax')
                      .replace(/; Secure/gi, '')
              );
            }
          });
        },
      },
    },
  },
});
