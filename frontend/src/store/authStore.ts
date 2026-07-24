import { create } from 'zustand';

interface User {
  id: string;
  email: string;
  full_name: string | null;
  avatar_url: string | null;
  is_active: boolean;
  created_at: string;
}

interface AuthState {
  token: string | null;
  tokenExpiry: number | null; // Unix ms timestamp when the access token expires
  user: User | null;
  isAuthenticated: boolean;
  login: (token: string, user: User, rememberMe?: boolean, expiresIn?: number) => void;
  logout: () => void;
  updateUser: (user: User) => void;
  updateToken: (token: string, expiresIn?: number) => void;
  isTokenExpiringSoon: (thresholdSeconds?: number) => boolean;
}

const getStorageItem = (key: string): string | null => {
  return localStorage.getItem(key) || sessionStorage.getItem(key);
};

export const useAuthStore = create<AuthState>((set, get) => ({
  token: getStorageItem('access_token'),
  tokenExpiry: getStorageItem('token_expiry') ? parseInt(getStorageItem('token_expiry')!, 10) : null,
  user: getStorageItem('user_info') ? JSON.parse(getStorageItem('user_info')!) : null,
  isAuthenticated: !!getStorageItem('access_token'),

  login: (token, user, rememberMe = true, expiresIn) => {
    const storage = rememberMe ? localStorage : sessionStorage;
    storage.setItem('access_token', token);
    storage.setItem('user_info', JSON.stringify(user));

    // Persist token expiry (ms since epoch) so it survives page refresh
    const expiry = expiresIn ? Date.now() + expiresIn * 1000 : null;
    if (expiry !== null) {
      storage.setItem('token_expiry', String(expiry));
    } else {
      storage.removeItem('token_expiry');
    }

    // Clear the other storage type to avoid stale data
    const otherStorage = rememberMe ? sessionStorage : localStorage;
    otherStorage.removeItem('access_token');
    otherStorage.removeItem('user_info');
    otherStorage.removeItem('token_expiry');

    set({ token, tokenExpiry: expiry, user, isAuthenticated: true });
  },

  logout: () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('user_info');
    localStorage.removeItem('token_expiry');
    sessionStorage.removeItem('access_token');
    sessionStorage.removeItem('user_info');
    sessionStorage.removeItem('token_expiry');
    set({ token: null, tokenExpiry: null, user: null, isAuthenticated: false });
  },

  updateUser: (user) => {
    if (localStorage.getItem('access_token')) {
      localStorage.setItem('user_info', JSON.stringify(user));
    } else {
      sessionStorage.setItem('user_info', JSON.stringify(user));
    }
    set({ user });
  },

  /** Silently update the stored token (e.g. after a background refresh) */
  updateToken: (token, expiresIn) => {
    const expiry = expiresIn ? Date.now() + expiresIn * 1000 : get().tokenExpiry;
    const storage = localStorage.getItem('access_token') ? localStorage : sessionStorage;
    storage.setItem('access_token', token);
    if (expiry !== null && expiry !== undefined) {
      storage.setItem('token_expiry', String(expiry));
    }
    set({ token, tokenExpiry: expiry ?? null });
  },

  /** Returns true if the token will expire within `thresholdSeconds` (default 60s). */
  isTokenExpiringSoon: (thresholdSeconds = 60) => {
    const { tokenExpiry } = get();
    if (!tokenExpiry) return false;
    return tokenExpiry - Date.now() < thresholdSeconds * 1000;
  },
}));
