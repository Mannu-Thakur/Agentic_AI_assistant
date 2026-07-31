import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { apiRequest } from '../services/api';
import { useAuthStore } from '../store/authStore';
import { Loader2, AlertCircle } from 'lucide-react';

export default function OAuthCallbackPage({ provider }: { provider: 'google' | 'github' }) {
  const [searchParams] = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const loginStore = useAuthStore((state) => state.login);
  const navigate = useNavigate();

  useEffect(() => {
    const code = searchParams.get('code');
    const state = searchParams.get('state');
    if (!code) {
      setError('Authorization code is missing from callback.');
      return;
    }

    async function exchangeCode() {
      try {
        // Build the same redirect_uri that was used during OAuth initiation
        const currentOrigin = window.location.origin;
        const redirectUri = encodeURIComponent(`${currentOrigin}/auth/${provider}/callback`);

        // Exchange authorization code for access token on backend
        let callbackUrl = `/auth/oauth/${provider}/callback?code=${code}&redirect_uri=${redirectUri}`;
        if (state) {
          callbackUrl += `&state=${state}`;
        }
        
        const data = await apiRequest(
          callbackUrl,
          { method: 'GET' }
        );
        
        // Fetch user profile info using the token
        const user = await apiRequest('/auth/me', {
          headers: { Authorization: `Bearer ${data.access_token}` }
        });
        
        // Save auth details in store (remember by default for OAuth)
        loginStore(data.access_token, user, true, data.expires_in);
        navigate('/');
      } catch (err: any) {
        setError(err.message || 'OAuth exchange failed.');
      }
    }

    exchangeCode();
  }, [searchParams, provider, loginStore, navigate]);

  return (
    <div className="min-h-screen bg-[#000000] text-foreground flex flex-col items-center justify-center p-6">
      <div className="max-w-md w-full rounded-2xl border border-border bg-[#0B0F19] p-8 flex flex-col items-center space-y-6 text-center shadow-xl">
        {!error ? (
          <>
            <div className="w-12 h-12 rounded-xl bg-accent/10 flex items-center justify-center text-accent">
              <Loader2 className="w-6 h-6 animate-spin" />
            </div>
            <div>
              <h3 className="text-lg font-semibold capitalize">Completing Sign-In</h3>
              <p className="text-xs text-muted-foreground mt-1">Exchanging authorization details with {provider}...</p>
            </div>
          </>
        ) : (
          <>
            <div className="w-12 h-12 rounded-xl bg-red-500/10 flex items-center justify-center text-red-500">
              <AlertCircle className="w-6 h-6" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-red-400">OAuth Sign-In Failed</h3>
              <p className="text-xs text-muted-foreground mt-1">{error}</p>
            </div>
            <button
              onClick={() => navigate('/login')}
              className="px-4 py-2 bg-accent hover:bg-accent/80 text-white rounded-lg text-xs font-semibold transition-colors"
            >
              Back to Login
            </button>
          </>
        )}
      </div>
    </div>
  );
}
