import { useAuthStore } from '../store/authStore';

export interface ProviderState {
  id: string;
  status: 'VERIFIED' | 'INVALID' | 'UNCONFIGURED' | 'VERIFYING' | 'ERROR';
  saved: boolean;
  verified: boolean;
  enabled: boolean;
  lastChecked: string | null;
  availableModels: string[];
  lastError?: string | null;
}

const STORAGE_KEY = 'x_api_keys';

class ProviderKeyManagerClass {
  private keys: Record<string, string> = {};

  constructor() {
    this.refresh();
  }

  /**
   * Always reads fresh keys from localStorage to prevent stale in-memory state.
   */
  refresh(): Record<string, string> {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      this.keys = stored ? JSON.parse(stored) : {};
    } catch (e) {
      console.error('[ProviderKeyManager] Failed to parse x_api_keys from localStorage:', e);
      this.keys = {};
    }
    return this.getAllKeys();
  }

  cache(): void {
    this.refresh();
  }

  /**
   * Retrieves an API key for a provider with support for provider aliases (e.g., google <-> gemini).
   */
  getKey(provider: string): string {
    this.refresh();
    const prov = provider.toLowerCase().trim();
    const key = this.keys[prov];
    if (key && key.trim() !== '') return key;
    
    // Alias handling
    if (prov === 'google') return this.keys['gemini'] || '';
    if (prov === 'gemini') return this.keys['google'] || '';
    return '';
  }

  /**
   * Sets an API key for a provider and persists to single source of truth in localStorage.
   */
  setKey(provider: string, key: string): void {
    this.refresh();
    const prov = provider.toLowerCase().trim();
    const cleanKey = key.trim();

    if (cleanKey) {
      this.keys[prov] = cleanKey;
      if (prov === 'google') this.keys['gemini'] = cleanKey;
      if (prov === 'gemini') this.keys['google'] = cleanKey;
    } else {
      delete this.keys[prov];
      if (prov === 'google') delete this.keys['gemini'];
      if (prov === 'gemini') delete this.keys['google'];
    }

    localStorage.setItem(STORAGE_KEY, JSON.stringify(this.keys));
  }

  /**
   * Removes an API key for a provider and updates persistence.
   */
  removeKey(provider: string): void {
    this.refresh();
    const prov = provider.toLowerCase().trim();
    delete this.keys[prov];
    if (prov === 'google') delete this.keys['gemini'];
    if (prov === 'gemini') delete this.keys['google'];
    localStorage.setItem(STORAGE_KEY, JSON.stringify(this.keys));
  }

  /**
   * Checks whether a valid key exists for the provider.
   */
  hasKey(provider: string): boolean {
    const key = this.getKey(provider);
    return !!key && key.trim() !== '' && !key.startsWith('••••') && key !== '****';
  }

  /**
   * Returns a complete clone of all provider keys with symmetric aliases guaranteed.
   */
  getAllKeys(): Record<string, string> {
    const res = { ...this.keys };
    if (res['google'] && !res['gemini']) res['gemini'] = res['google'];
    if (res['gemini'] && !res['google']) res['google'] = res['gemini'];
    return res;
  }

  /**
   * Verifies an API key with the backend endpoint and persists locally if valid.
   * Decoupled from api.ts to prevent circular import issues.
   */
  async verifyKey(provider: string, key: string): Promise<boolean> {
    const token = useAuthStore.getState().token;
    const cleanProv = provider.toLowerCase().trim();
    
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch('/api/v1/api-keys', {
      method: 'POST',
      headers,
      body: JSON.stringify({ provider_name: cleanProv, api_key: key }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ detail: 'Verification failed' }));
      throw new Error(errorData.detail || `API key verification failed for ${provider.toUpperCase()}`);
    }

    this.setKey(cleanProv, key);
    return true;
  }

  /**
   * Syncs local keys with backend provider statuses.
   */
  async sync(): Promise<ProviderState[]> {
    const token = useAuthStore.getState().token;
    const headers: Record<string, string> = {};
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    const allKeys = this.getAllKeys();
    headers['x-api-keys'] = JSON.stringify(allKeys);

    try {
      const res = await fetch('/api/v1/providers', { headers });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const backendProviders: ProviderState[] = await res.json();
      
      let updated = false;
      for (const p of backendProviders) {
        const provId = p.id;
        const hasLocal = this.hasKey(provId);
        if (hasLocal && !p.saved) {
          const rawKey = this.getKey(provId);
          try {
            await this.verifyKey(provId, rawKey);
            p.saved = true;
            p.status = 'VERIFIED';
            p.verified = true;
            p.enabled = true;
            updated = true;
          } catch (e) {
            console.warn(`[ProviderKeyManager] Auto-sync failed for ${provId}:`, e);
          }
        }
      }

      if (updated) {
        const refreshedRes = await fetch('/api/v1/providers', { headers });
        if (refreshedRes.ok) {
          return await refreshedRes.json();
        }
      }

      return backendProviders;
    } catch (err) {
      console.error('[ProviderKeyManager] Failed to sync keys with backend:', err);
      throw err;
    }
  }

  /**
   * Canonical provider resolution from model ID.
   */
  resolveProvider(modelId: string): string {
    const m = modelId.toLowerCase().trim();
    if (m.startsWith('openrouter/')) return 'openrouter';
    if (m.includes('gemini') || m.includes('google')) return 'google';
    if (m.includes('gpt') || m.includes('o1-')) return 'openai';
    if (m.includes('claude')) return 'anthropic';
    if (m.includes('deepseek')) return 'deepseek';
    if (m.includes('llama') || m.includes('mixtral')) return 'groq';
    if (m.includes('glm')) return 'glm';
    if (m.includes('qwen')) return 'alibaba';
    // Search providers
    if (m === 'tavily' || m.includes('tavily')) return 'tavily';
    if (m === 'serpapi' || m.includes('serp')) return 'serpapi';
    if (m === 'exa' || m.includes('exa')) return 'exa';
    return 'google';
  }
}

export const ProviderKeyManager = new ProviderKeyManagerClass();
