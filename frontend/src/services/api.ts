import { useAuthStore } from '../store/authStore';
import { ProviderKeyManager } from './providerKeyManager';

const BASE_URL = '/api/v1';

interface RequestOptions extends RequestInit {
  json?: any;
  /** Override timeout in ms. Defaults: 120000 for uploads, 30000 for everything else. */
  timeoutMs?: number;
  /** Internal flag to skip the proactive-refresh & 401-refresh logic (used for the refresh call itself). */
  _skipRefresh?: boolean;
}

async function fetchWithTimeout(url: string, options: RequestInit, timeoutMs: number): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

/** Attempt a token refresh. Returns the new access token, or null on failure. */
async function attemptTokenRefresh(): Promise<string | null> {
  try {
    const refreshResponse = await fetchWithTimeout(
      `${BASE_URL}/auth/refresh`,
      { method: 'POST', credentials: 'include' },
      15_000,
    );

    if (refreshResponse.ok) {
      const refreshData = await refreshResponse.json();
      const newToken: string = refreshData.access_token;
      const expiresIn: number | undefined = refreshData.expires_in;
      useAuthStore.getState().updateToken(newToken, expiresIn);
      return newToken;
    }
  } catch {
    // Network error during refresh — don't log out yet, just return null
  }
  return null;
}

/** Redirect to login and clear auth state. Only fires when not already on /login. */
function forceLogout(reason: string) {
  if (window.location.pathname === '/login') return; // prevent redirect loop
  useAuthStore.getState().logout();
  window.location.href = '/login';
  throw new Error(reason);
}

export async function apiRequest<T = any>(
  endpoint: string,
  options: RequestOptions = {}
): Promise<T> {
  const { token, isAuthenticated, isTokenExpiringSoon } = useAuthStore.getState();

  // --- Proactive token refresh (if expiring within 5 minutes) ---
  // Only attempt proactive refresh when the user IS authenticated and we're
  // not already inside a refresh call.
  let activeToken = token;
  if (!options._skipRefresh && isAuthenticated && token && isTokenExpiringSoon(300)) {
    const newToken = await attemptTokenRefresh();
    if (newToken) {
      activeToken = newToken;
    }
    // If refresh failed, still try with the old token — the 401 handler below
    // will make a final reactive attempt before giving up.
  }

  const headers = new Headers(options.headers || {});

  if (activeToken) {
    headers.set('Authorization', `Bearer ${activeToken}`);
  }

  // Always refresh and inject all API keys into x-api-keys header
  const allKeys = ProviderKeyManager.refresh();
  headers.set('x-api-keys', JSON.stringify(allKeys));

  if (options.json) {
    headers.set('Content-Type', 'application/json');
    options.body = JSON.stringify(options.json);
  }

  // Uploads need a long timeout; all other requests use 30s
  const isUpload = options.body instanceof FormData;
  const timeoutMs = options.timeoutMs ?? (isUpload ? 120_000 : 30_000);

  const url = `${BASE_URL}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`;

  if (localStorage.getItem('developer_mode') === 'true') {
    console.log(`[API REQUEST] ${options.method || 'GET'} ${url}`, {
      hasAuthToken: !!activeToken,
      keysCount: Object.keys(allKeys).length,
    });
  }

  let response = await fetchWithTimeout(url, { ...options, headers, credentials: 'include' }, timeoutMs);

  // --- Reactive 401 refresh (token expired mid-request) ---
  if (response.status === 401 && activeToken && !options._skipRefresh) {
    const newToken = await attemptTokenRefresh();

    if (newToken) {
      // Retry the original request with the fresh token
      headers.set('Authorization', `Bearer ${newToken}`);
      response = await fetchWithTimeout(url, { ...options, headers, credentials: 'include' }, timeoutMs);
    } else {
      // Refresh failed — try once more with current token before giving up.
      // This handles transient network errors on the refresh endpoint.
      response = await fetchWithTimeout(url, { ...options, headers, credentials: 'include' }, timeoutMs);
      if (response.status === 401) {
        // Confirmed dead session — only NOW force logout
        forceLogout('Session expired. Please log in again.');
      }
    }
  }

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: `HTTP ${response.status} Request failed` }));
    const errorMessage = errorData.detail || errorData.message || `API request failed (${response.status})`;

    if (localStorage.getItem('developer_mode') === 'true') {
      console.error(`[API ERROR] ${options.method || 'GET'} ${url} -> ${response.status}`, errorData);
    }
    throw new Error(errorMessage);
  }

  return response.json();
}
