import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

// Print environment variables on boot
console.log('=== Environment Variables ===');
console.log('ENVIRONMENT:', import.meta.env.MODE);
console.log('VITE_APP_API_BASE_URL:', import.meta.env.VITE_APP_API_BASE_URL);
console.log('VITE_GOOGLE_MAPS_API_KEY:', import.meta.env.VITE_GOOGLE_MAPS_API_KEY);
console.log('============================');

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
