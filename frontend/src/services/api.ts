import { useAuthStore } from '../store/authStore';

const BASE_URL = '/api/v1';

interface RequestOptions extends RequestInit {
  json?: any;
}

export async function apiRequest<T = any>(
  endpoint: string,
  options: RequestOptions = {}
): Promise<T> {
  const { token, logout, login } = useAuthStore.getState();
  
  const headers = new Headers(options.headers || {});
  
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  
  if (options.json) {
    headers.set('Content-Type', 'application/json');
    options.body = JSON.stringify(options.json);
  }

  const url = `${BASE_URL}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`;
  
  let response = await fetch(url, { ...options, headers });

  // Token expired / 401 Unauthorized -> Attempt token refresh rotation
  if (response.status === 401 && token) {
    try {
      const refreshResponse = await fetch(`${BASE_URL}/auth/refresh`, {
        method: 'POST',
      });
      
      if (refreshResponse.ok) {
        const refreshData = await refreshResponse.json();
        const newToken = refreshData.access_token;
        
        // Save new token in auth store
        const user = useAuthStore.getState().user;
        if (user) {
          login(newToken, user);
        }
        
        // Retry the original request with new token
        headers.set('Authorization', `Bearer ${newToken}`);
        response = await fetch(url, { ...options, headers });
      } else {
        // Refresh token failed -> Logout user
        logout();
        window.location.href = '/login';
        throw new Error('Session expired');
      }
    } catch (err) {
      logout();
      window.location.href = '/login';
      throw err;
    }
  }

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(errorData.detail || 'API request failed');
  }

  return response.json();
}
