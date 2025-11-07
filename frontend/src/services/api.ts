/**
 * Centralized API endpoints configuration
 */

// Base API URL - can be configured via environment variables
export const VITE_APP_API_BASE_URL = import.meta.env.VITE_APP_API_BASE_URL || 'http://localhost:8060';

/**
 * API Endpoints
 */
export const API = {
  // Authentication endpoints
  auth: {
    google: `${VITE_APP_API_BASE_URL}/auth/google`,
    me: `${VITE_APP_API_BASE_URL}/auth/me`,
    config: `${VITE_APP_API_BASE_URL}/auth/config`,
    logout: `${VITE_APP_API_BASE_URL}/auth/logout`,
  },

  // System endpoints
  system: {
    health: `${VITE_APP_API_BASE_URL}/health`,
    status: `${VITE_APP_API_BASE_URL}/status`,
  },

} as const;