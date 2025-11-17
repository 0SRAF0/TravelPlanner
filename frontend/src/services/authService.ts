import { API } from './api.ts';

export interface UserInfo {
  id: string;
  email: string;
  name: string;
  given_name?: string;
  family_name?: string;
  picture?: string;
  email_verified: boolean;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: UserInfo;
}

export interface AuthConfig {
  google_client_id: string;
  redirect_uri: string;
  scopes: string[];
}

/**
 * Authentication service for handling Google OAuth and JWT tokens
 */
export const authService = {
  /**
   * Exchange Google authorization code for JWT token
   */
  async exchangeCodeForToken(code: string): Promise<AuthResponse> {
    const url = `${API.auth.google}?code=${encodeURIComponent(code)}`;
    const response = await fetch(url, { method: 'POST' });

    if (!response.ok) {
      const error = await response.json().catch(() => null);
      throw new Error(error?.detail || 'Failed to authenticate');
    }

    const json = await response.json();
    return json?.data as AuthResponse;
  },

  /**
   * Get current authenticated user information
   */
  async getCurrentUser(token: string): Promise<UserInfo> {
    const response = await fetch(API.auth.me, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });

    if (!response.ok) {
      throw new Error('Failed to get user info');
    }

    const json = await response.json();
    return json?.data as UserInfo;
  },

  /**
   * Get OAuth configuration from backend
   */
  async getAuthConfig(): Promise<AuthConfig> {
    const response = await fetch(API.auth.config);

    if (!response.ok) {
      throw new Error('Failed to get auth config');
    }

    const json = await response.json();
    return json?.data as AuthConfig;
  },

  /**
   * Logout user
   */
  async logout(token: string): Promise<void> {
    try {
      await fetch(API.auth.logout, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });
    } catch (error) {
      console.error('Logout error:', error);
    } finally {
      // Always remove token, even if API call fails
      this.removeToken();
      this.removeUser();
    }
  },

  /**
   * Save JWT token to localStorage
   */
  saveToken(token: string): void {
    localStorage.setItem('auth_token', token);
  },

  /**
   * Get JWT token from localStorage
   */
  getToken(): string | null {
    return localStorage.getItem('auth_token');
  },

  /**
   * Remove JWT token from localStorage
   */
  removeToken(): void {
    localStorage.removeItem('auth_token');
  },

  /**
   * Save user info to localStorage
   */
  saveUser(user: UserInfo): void {
    localStorage.setItem('user_info', JSON.stringify(user));
  },

  /**
   * Get user info from localStorage
   */
  getUser(): UserInfo | null {
    const userStr = localStorage.getItem('user_info');
    if (!userStr) return null;

    try {
      return JSON.parse(userStr);
    } catch {
      return null;
    }
  },

  /**
   * Remove user info from localStorage
   */
  removeUser(): void {
    localStorage.removeItem('user_info');
  },

  /**
   * Check if user is authenticated
   */
  isAuthenticated(): boolean {
    return !!this.getToken();
  },

  /**
   * Initialize Google OAuth flow
   */
  async initiateGoogleLogin(): Promise<void> {
    try {
      const config = await this.getAuthConfig();

      const authUrl =
        `https://accounts.google.com/o/oauth2/v2/auth?` +
        `client_id=${config.google_client_id}&` +
        `redirect_uri=${encodeURIComponent(config.redirect_uri)}&` +
        `response_type=code&` +
        `scope=${encodeURIComponent(config.scopes.join(' '))}&` +
        `access_type=offline&` +
        `prompt=consent`;

      window.location.href = authUrl;
    } catch (error) {
      console.error('Failed to initiate Google login:', error);
      throw error;
    }
  },
};
