import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { apiRequest } from '../services/api';
import { useAuthStore } from '../store/authStore';
import { KeyRound, Mail, UserPlus, LogIn, AlertCircle } from 'lucide-react';

export default function LoginPage() {
  const [isLogin, setIsLogin] = useState<boolean>(true);
  const [email, setEmail] = useState<string>('');
  const [password, setPassword] = useState<string>('');
  const [fullName, setFullName] = useState<string>('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [rememberMe, setRememberMe] = useState<boolean>(true);
  const loginStore = useAuthStore((state) => state.login);
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      if (isLogin) {
        // Authenticate login
        const data = await apiRequest('/auth/login', {
          method: 'POST',
          json: { email, password }
        });
        
        // Query user info
        const user = await apiRequest('/auth/me', {
          headers: { Authorization: `Bearer ${data.access_token}` }
        });
        
        loginStore(data.access_token, user, rememberMe, data.expires_in);
        navigate('/');
      } else {
        // Register account
        await apiRequest('/auth/register', {
          method: 'POST',
          json: { email, password, full_name: fullName }
        });
        
        // Auto log in after register
        const data = await apiRequest('/auth/login', {
          method: 'POST',
          json: { email, password }
        });
        
        const user = await apiRequest('/auth/me', {
          headers: { Authorization: `Bearer ${data.access_token}` }
        });
        
        loginStore(data.access_token, user, rememberMe, data.expires_in);
        navigate('/');
      }
    } catch (err: any) {
      setError(err.message || 'Authentication failed');
    } finally {
      setLoading(false);
    }
  };

  const handleOAuth = (provider: 'google' | 'github') => {
    // Initiate OAuth redirection with dynamic callback URL based on active origin
    const currentOrigin = window.location.origin;
    const redirectUri = encodeURIComponent(`${currentOrigin}/auth/${provider}/callback`);
    apiRequest(`/auth/oauth/${provider}?redirect_uri=${redirectUri}`)
      .then((res) => {
        if (res.url) {
          window.location.href = res.url;
        }
      })
      .catch(() => {
        setError(`${provider} login could not be initialized`);
      });
  };

  return (
    <div className="space-y-6">
      
      {/* Title */}
      <div className="text-center">
        <h3 className="text-xl font-semibold text-foreground">
          {isLogin ? 'Welcome Back' : 'Create Account'}
        </h3>
        <p className="text-muted-foreground text-xs mt-1">
          {isLogin ? 'Log in to access your agent workspace' : 'Scaffold a new dev session workspace'}
        </p>
      </div>

      {/* Error Message */}
      {error && (
        <div className="flex items-center space-x-2 p-3.5 rounded-xl border border-red-500/20 bg-red-500/5 text-red-400 text-xs">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Auth Form */}
      <form onSubmit={handleSubmit} className="space-y-4">
        {!isLogin && (
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-muted-foreground">Full Name</label>
            <div className="relative">
              <input
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Alex Omni"
                className="w-full bg-secondary/30 border border-border rounded-xl py-2 px-3 pl-10 text-sm focus:outline-none focus:border-primary text-foreground"
                required
              />
              <UserPlus className="absolute left-3.5 top-3 w-4 h-4 text-muted-foreground" />
            </div>
          </div>
        )}

        <div className="space-y-1.5">
          <label className="text-xs font-semibold text-muted-foreground">Email Address</label>
          <div className="relative">
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="developer@omni.ai"
              className="w-full bg-secondary/30 border border-border rounded-xl py-2 px-3 pl-10 text-sm focus:outline-none focus:border-primary text-foreground"
              required
            />
            <Mail className="absolute left-3.5 top-3 w-4 h-4 text-muted-foreground" />
          </div>
        </div>

        <div className="space-y-1.5">
          <label className="text-xs font-semibold text-muted-foreground">Password</label>
          <div className="relative">
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••••••"
              className="w-full bg-secondary/30 border border-border rounded-xl py-2 px-3 pl-10 text-sm focus:outline-none focus:border-primary text-foreground"
              required
            />
            <KeyRound className="absolute left-3.5 top-3 w-4 h-4 text-muted-foreground" />
          </div>
        </div>

        {isLogin && (
          <div className="flex items-center justify-between mt-2">
            <label className="flex items-center space-x-2 text-xs text-muted-foreground cursor-pointer select-none">
              <input
                type="checkbox"
                checked={rememberMe}
                onChange={(e) => setRememberMe(e.target.checked)}
                className="w-4 h-4 rounded border border-gray-600 bg-[#0B0F19] text-violet-600 focus:ring-violet-500 cursor-pointer accent-violet-600"
              />
              <span>Remember Me</span>
            </label>

            <Link
              to="/forgot-password"
              className="text-xs text-primary font-medium hover:underline transition-all"
            >
              Forgot password?
            </Link>
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          className="w-full flex items-center justify-center space-x-2 py-2.5 rounded-xl bg-primary text-primary-foreground font-semibold text-sm transition-all hover:opacity-95 disabled:opacity-50 mt-6 shadow-lg shadow-primary/20"
        >
          {isLogin ? <LogIn className="w-4 h-4" /> : <UserPlus className="w-4 h-4" />}
          <span>{loading ? 'Authenticating...' : isLogin ? 'Sign In' : 'Sign Up'}</span>
        </button>
      </form>

      {/* Divider */}
      <div className="relative flex items-center justify-center py-2">
        <div className="absolute inset-0 flex items-center"><div className="w-full border-t border-border" /></div>
        <span className="relative z-10 px-3 bg-card text-muted-foreground text-[10px] uppercase font-semibold">Or Connect With</span>
      </div>

      {/* OAuth Buttons */}
      <div className="grid grid-cols-2 gap-3">
        <button
          onClick={() => handleOAuth('google')}
          className="flex items-center justify-center space-x-2 py-2 px-3 rounded-xl border border-border bg-secondary/20 hover:bg-secondary/40 text-xs font-medium transition-all"
        >
          <span>Google</span>
        </button>
        <button
          onClick={() => handleOAuth('github')}
          className="flex items-center justify-center space-x-2 py-2 px-3 rounded-xl border border-border bg-secondary/20 hover:bg-secondary/40 text-xs font-medium transition-all"
        >
          <span>GitHub</span>
        </button>
      </div>

      {/* Toggle View Link */}
      <p className="text-center text-xs text-muted-foreground">
        {isLogin ? "Don't have an account? " : "Already have an account? "}
        <button
          type="button"
          onClick={() => {
            setIsLogin(!isLogin);
            setError(null);
          }}
          className="text-primary font-semibold hover:underline"
        >
          {isLogin ? 'Sign Up' : 'Sign In'}
        </button>
      </p>
    </div>
  );
}
