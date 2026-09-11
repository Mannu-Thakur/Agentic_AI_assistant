import { useEffect, useState, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { apiRequest } from '../services/api';
import { useAuthStore } from '../store/authStore';
import { Loader2, AlertCircle } from 'lucide-react';

export default function OAuthCallbackPage({ provider }: { provider: 'google' | 'github' }) {
  const [searchParams] = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const loginStore = useAuthStore((state) => state.login);
  const navigate = useNavigate();
  const exchangeInitiated = useRef(false);

  useEffect(() => {
    // Check if provider returned an explicit error parameter
    const errorParam = searchParams.get('error_description') || searchParams.get('error');
    if (errorParam) {
      setError(`${provider.toUpperCase()} authentication error: ${errorParam}`);
      return;
    }

    const code = searchParams.get('code');
    const state = searchParams.get('state');
    if (!code) {
      setError('Authorization code is missing from callback.');
      return;
    }

    // Prevent double execution in React 18 StrictMode
    if (exchangeInitiated.current) {
      return;
    }
    exchangeInitiated.current = true;

    async function exchangeCode() {
      try {
        // Build the same redirect_uri that was used during OAuth initiation
        const currentOrigin = window.location.origin;
        const redirectUri = encodeURIComponent(`${currentOrigin}/auth/${provider}/callback`);
        const encodedCode = encodeURIComponent(code!);
        const encodedState = state ? encodeURIComponent(state) : '';

        // Exchange authorization code for access token on backend
        let callbackUrl = `/auth/oauth/${provider}/callback?code=${encodedCode}&redirect_uri=${redirectUri}`;
        if (encodedState) {
          callbackUrl += `&state=${encodedState}`;
        }
        
        const data = await apiRequest(
          callbackUrl,
          { method: 'GET' }
        );

        // Retrieve user profile: use user from exchange payload if available, else fetch via /auth/me
        let user = data.user;
        if (!user) {
          user = await apiRequest('/auth/me', {
            headers: { Authorization: `Bearer ${data.access_token}` }
          });
        }
        
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
