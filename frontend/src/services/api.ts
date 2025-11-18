/**
 * Centralized API endpoints configuration
 */

// Base API URL - can be configured via environment variables
export const BASE_URL = import.meta.env.VITE_APP_API_BASE_URL || 'http://localhost:8060';

// Derive WebSocket base URL from BASE_URL
export const WS_BASE_URL = BASE_URL.startsWith('https')
  ? BASE_URL.replace(/^https/, 'wss')
  : BASE_URL.replace(/^http/, 'ws');

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

  // Chatbot endpoints
  chatBot: {
    send: `${BASE_URL}/chatbot`,
  },

  // Trip endpoints
  trip: {
    create: `${BASE_URL}/trips`,
    join: `${BASE_URL}/trips/join`,
    get: `${BASE_URL}/trips`,
    user:`${BASE_URL}/trips/user`,
    allIn: `${BASE_URL}/trips/all-in`,
    delete: `${BASE_URL}/trips`,
  },

  // Preferences endpoints
  preferences: {
    create: `${BASE_URL}/preferences/`, // POST
    aggregate: `${BASE_URL}/preferences/aggregate`, // GET ?trip_id=
    user: `${BASE_URL}/preferences/user`, // GET ?user_id=&trip_id=
  },

  // Activities endpoints
  activities: {
    list: `${BASE_URL}/activities`,
    vote: `${BASE_URL}/activities/vote`,
  },

  // Locations endpoints
  locations: {
    autocomplete: `${BASE_URL}/locations/autocomplete`,
  },

  // Chat endpoints (WebSocket)
  chat: {
    chat: `${WS_BASE_URL}/chat`,
  },
} as const;
