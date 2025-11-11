import { defineConfig, loadEnv, type ConfigEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig(({ mode }: ConfigEnv) => {
  // Load env file based on `mode` in the current working directory.
  const env = loadEnv(mode, process.cwd(), '')
  
  console.log('=== Vite Config - Loading Environment ===')
  console.log('Mode:', mode)
  console.log('VITE_APP_API_BASE_URL:', env.VITE_APP_API_BASE_URL)
  console.log('VITE_GOOGLE_MAPS_API_KEY:', env.VITE_GOOGLE_MAPS_API_KEY ? '***configured***' : 'undefined')
  console.log('=========================================')
  
  return {
    plugins: [
      react(),
      tailwindcss()
    ],
    // Expose env variables to your app
    define: {
      'import.meta.env.VITE_APP_API_BASE_URL': JSON.stringify(env.VITE_APP_API_BASE_URL),
      'import.meta.env.VITE_GOOGLE_MAPS_API_KEY': JSON.stringify(env.VITE_GOOGLE_MAPS_API_KEY),
    },
  }
})