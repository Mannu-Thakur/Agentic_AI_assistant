import { useAuthStore } from '../store/authStore';
import { ProviderKeyManager } from './providerKeyManager';

const API_BASE = (((import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_BACKEND_URL) as string | undefined) || '').replace(/\/+$/, '');
export const BASE_URL = `${API_BASE}/api/v1`;


interface RequestOptions extends RequestInit {
  json?: any;
  /** Override timeout in ms. Defaults: 120000 for uploads, 30000 for everything else. */
  timeoutMs?: number;
  /** Internal flag to skip the proactive-refresh & 401-refresh logic (used for the refresh call itself). */
  _skipRefresh?: boolean;
}

// ─── Cold-start / Wake-up Utilities ──────────────────────────────────────────

/** Returns true when the app is pointing at a remote backend (not localhost). */
function isRemoteBackend(): boolean {
  return !!API_BASE && !API_BASE.includes('localhost') && !API_BASE.includes('127.0.0.1');
}

/**
 * Pings the backend health endpoint until it responds or the max attempts are
 * exhausted.  Designed for Render free-tier cold starts (≈30-60 s spin-up).
 *
 * @param onProgress  Optional callback fired every attempt with the current
 *                    attempt index (0-based) and the max.
 * @returns           true if the backend is alive, false if all attempts failed.
 */
export async function wakeUpBackend(
  onProgress?: (attempt: number, max: number) => void,
): Promise<boolean> {
  // Only bother on remote deployments — localhost is always "awake".
  if (!isRemoteBackend()) return true;

  const HEALTH_URL = `${BASE_URL}/health`;
  const MAX_ATTEMPTS = 8;   // ≈ 60 s total (8 × ~7-8 s per attempt)
  const RETRY_DELAY_MS = 7_000;
  const ATTEMPT_TIMEOUT_MS = 8_000;

  for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
    onProgress?.(attempt, MAX_ATTEMPTS);
    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), ATTEMPT_TIMEOUT_MS);
      const res = await fetch(HEALTH_URL, {
        method: 'GET',
        signal: controller.signal,
        cache: 'no-store',
      }).finally(() => clearTimeout(timer));

      if (res.ok) return true;   // backend is alive ✓
    } catch {
      // network error / timeout / abort — keep retrying
    }

    if (attempt < MAX_ATTEMPTS - 1) {
      await new Promise((r) => setTimeout(r, RETRY_DELAY_MS));
    }
  }
  return false; // gave up
}

/**
 * Wraps `apiRequest` with an automatic cold-start wake-up phase.
 * If the backend is unreachable on the first attempt, it pings the health
 * endpoint (with retries) before re-trying the real request.
 *
 * @param endpoint   Same as `apiRequest`
 * @param options    Same as `apiRequest`
 * @param onWaking   Called when a cold start is detected and wake-up begins.
 *                   Receives (attempt, max) on each retry tick.
 */
export async function apiRequestWithWakeup<T = any>(
  endpoint: string,
  options: RequestOptions = {},
  onWaking?: (attempt: number, max: number) => void,
): Promise<T> {
  try {
    // Optimistic first attempt — works fine when the backend is already warm.
    return await apiRequest<T>(endpoint, options);
  } catch (err: any) {
    // Only trigger the wake-up flow for network-level failures on remote hosts.
    const isNetworkError =
      err?.message?.includes('Failed to fetch') ||
      err?.message?.includes('NetworkError') ||
      err?.message?.includes('Load failed') ||
      err?.message?.toLowerCase().includes('abort');

    if (!isNetworkError || !isRemoteBackend()) throw err;

    // Backend seems cold — try to wake it up before retrying.
    const alive = await wakeUpBackend(onWaking);
    if (!alive) {
      throw new Error(
        `Unable to reach the backend server (${BASE_URL}). ` +
        `It may still be waking up from sleep. Please wait a moment and try again.`,
      );
    }

    // One final retry now that the backend is confirmed alive.
    return await apiRequest<T>(endpoint, options);
  }
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
    const storedRefresh = useAuthStore.getState().getRefreshToken();
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (storedRefresh) {
      headers['x-refresh-token'] = storedRefresh;
    }

    const refreshResponse = await fetchWithTimeout(
      `${BASE_URL}/auth/refresh`,
      {
        method: 'POST',
        credentials: 'include',
        headers,
        body: JSON.stringify({ refresh_token: storedRefresh || undefined }),
      },
      15_000,
    );

    if (refreshResponse.ok) {
      const refreshData = await refreshResponse.json();
      const newToken: string = refreshData.access_token;
      const expiresIn: number | undefined = refreshData.expires_in;
      const newRefreshToken: string | undefined = refreshData.refresh_token;
      useAuthStore.getState().updateToken(newToken, expiresIn, newRefreshToken);
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

  if (activeToken && !headers.has('Authorization')) {
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

  const cleanEndpoint = endpoint.startsWith(BASE_URL)
    ? endpoint.slice(BASE_URL.length)
    : endpoint.startsWith('/api/v1')
    ? endpoint.slice(7)
    : endpoint;
  const url = `${BASE_URL}${cleanEndpoint.startsWith('/') ? cleanEndpoint : `/${cleanEndpoint}`}`;

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
      // BUG-12 FIX: Refresh failed — the session is dead. Previously the code
      // retried the original request with the same expired token (guaranteed 401)
      // which wasted the full 30s timeout before giving up. Skip straight to logout.
      forceLogout('Session expired. Please log in again.');
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

  // 204 No Content (and similar) responses have no body — avoid JSON parse error
  const contentLength = response.headers.get('content-length');
  const contentType = response.headers.get('content-type') || '';
  
  if (response.status === 204 || contentLength === '0') {
    return null as T;
  }

  if (contentType.includes('application/json')) {
    return response.json();
  }

  if (contentType.includes('text/')) {
    return response.text() as unknown as T;
  }

  return response.blob() as unknown as T;
}
