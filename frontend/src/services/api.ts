/**
 * Centralized API endpoints configuration
 */

// Base API URL - can be configured via environment variables
export const BASE_URL = import.meta.env.VITE_APP_API_BASE_URL || 'http://localhost:8060';

/**
 * API Endpoints
 */
export const API = {
  // Authentication endpoints
  auth: {
    google: `${BASE_URL}/auth/google`,
    me: `${BASE_URL}/auth/me`,
    config: `${BASE_URL}/auth/config`,
    logout: `${BASE_URL}/auth/logout`,
  },

  // System endpoints
  system: {
    health: `${BASE_URL}/health`,
    status: `${BASE_URL}/status`,
  },

  // Activities endpoints
  activities: {
    list: `${BASE_URL}/activities`,
    vote: `${BASE_URL}/activities/vote`,
  },

  // Chat endpoints
  chat: {
    send: `${BASE_URL}/chat`,
  },

} as const;