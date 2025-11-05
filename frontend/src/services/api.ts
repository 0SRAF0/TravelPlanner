/**
 * Centralized API endpoints configuration
 */

// Base API URL - can be configured via environment variables
export const API_BASE_URL = import.meta.env.API_BASE_URL || 'http://localhost:8060';

/**
 * API Endpoints
 */
export const API = {
  // Authentication endpoints
  auth: {
    google: `${API_BASE_URL}/auth/google`,
    me: `${API_BASE_URL}/auth/me`,
    config: `${API_BASE_URL}/auth/config`,
    logout: `${API_BASE_URL}/auth/logout`,
  },

  // System endpoints
  system: {
    health: `${API_BASE_URL}/health`,
    status: `${API_BASE_URL}/status`,
  },

} as const;