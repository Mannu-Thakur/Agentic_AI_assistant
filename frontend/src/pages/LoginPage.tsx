import { useState, useId } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { apiRequest } from '../services/api';
import { useAuthStore } from '../store/authStore';
import { AlertCircle, Eye, EyeOff, Loader2, RefreshCw } from 'lucide-react';

export default function LoginPage() {
  const [isLogin, setIsLogin] = useState<boolean>(true);
  const [email, setEmail] = useState<string>('');
  const [password, setPassword] = useState<string>('');
  const [fullName, setFullName] = useState<string>('');
  const [showPassword, setShowPassword] = useState<boolean>(false);
  const [rememberMe, setRememberMe] = useState<boolean>(true);
  
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [oauthLoading, setOauthLoading] = useState<'google' | 'github' | null>(null);

  const loginStore = useAuthStore((state) => state.login);
  const navigate = useNavigate();

  const emailId = useId();
  const passwordId = useId();
  const fullNameId = useId();

  const isEmailValid = email.trim().length >= 3;
  const isPasswordValid = password.length >= 6;
  const isFullNameValid = fullName.trim().length >= 2;

  const handleSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setError(null);

    if (!isEmailValid) {
      setError('Please enter your username or email address.');
      return;
    }
    if (!isPasswordValid) {
      setError('Password must be at least 6 characters long.');
      return;
    }
    if (!isLogin && !isFullNameValid) {
      setError('Please enter your full name (at least 2 characters).');
      return;
    }

    setLoading(true);

    try {
      if (isLogin) {
        const data = await apiRequest('/auth/login', {
          method: 'POST',
          json: { email: email.trim(), password }
        });
        
        const user = await apiRequest('/auth/me', {
          headers: { Authorization: `Bearer ${data.access_token}` }
        });
        
        loginStore(data.access_token, user, rememberMe, data.expires_in);
        navigate('/');
      } else {
        await apiRequest('/auth/register', {
          method: 'POST',
          json: { email: email.trim(), password, full_name: fullName.trim() }
        });
        
        const data = await apiRequest('/auth/login', {
          method: 'POST',
          json: { email: email.trim(), password }
        });
        
        const user = await apiRequest('/auth/me', {
          headers: { Authorization: `Bearer ${data.access_token}` }
        });
        
        loginStore(data.access_token, user, rememberMe, data.expires_in);
        navigate('/');
      }
    } catch (err: any) {
      const msg = err.message || 'Authentication failed. Please check your credentials and try again.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleOAuth = (provider: 'google' | 'github') => {
    setOauthLoading(provider);
    setError(null);
    const currentOrigin = window.location.origin;
    const redirectUri = encodeURIComponent(`${currentOrigin}/auth/${provider}/callback`);
    
    apiRequest(`/auth/oauth/${provider}?redirect_uri=${redirectUri}`)
      .then((res) => {
        if (res.url) {
          window.location.href = res.url;
        } else {
          setError(`Failed to start ${provider} login session.`);
          setOauthLoading(null);
        }
      })
      .catch(() => {
        setError(`Unable to connect to ${provider} authentication provider.`);
        setOauthLoading(null);
      });
  };

  return (
    <div className="space-y-4 animate-in fade-in-0 duration-200 text-left">
      
      {/* Title & Subtitle */}
      <div>
        <h2 className="text-2xl font-bold text-white tracking-tight">
          {isLogin ? 'Log in' : 'Register'}
        </h2>
        <p className="text-gray-300 text-xs mt-1 font-normal">
          {isLogin ? (
            <>
              New user?{' '}
              <button
                type="button"
                onClick={() => {
                  setIsLogin(false);
                  setError(null);
                }}
                className="text-blue-400 font-semibold hover:text-blue-300 hover:underline transition-colors focus:outline-none"
              >
                Register Now
              </button>
            </>
          ) : (
            <>
              Already registered?{' '}
              <button
                type="button"
                onClick={() => {
                  setIsLogin(true);
                  setError(null);
                }}
                className="text-blue-400 font-semibold hover:text-blue-300 hover:underline transition-colors focus:outline-none"
              >
                Sign In
              </button>
            </>
          )}
        </p>
      </div>

      {/* Primary Social Button: Continue with Google */}
      <div className="pt-1">
        <button
          type="button"
          onClick={() => handleOAuth('google')}
          disabled={loading || oauthLoading !== null}
          className="w-full h-11 flex items-center justify-center space-x-2.5 px-4 rounded-xl border border-white/10 bg-[#272a33] hover:bg-[#313540] text-white text-xs font-medium transition-all duration-150 active:scale-[0.985] disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-1 focus:ring-blue-500/40"
        >
          {oauthLoading === 'google' ? (
            <Loader2 className="w-4 h-4 animate-spin text-gray-300" />
          ) : (
            <svg className="w-4 h-4 flex-shrink-0" viewBox="0 0 24 24">
              <path
                fill="#4285F4"
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
              />
              <path
                fill="#34A853"
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
              />
              <path
                fill="#FBBC05"
                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
              />
              <path
                fill="#EA4335"
                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
              />
            </svg>
          )}
          <span>Continue with Google</span>
        </button>

        {/* Circular Button Row: GitHub */}
        <div className="flex items-center justify-center gap-3.5 my-3">
          {/* GitHub Button */}
          <button
            type="button"
            onClick={() => handleOAuth('github')}
            disabled={loading || oauthLoading !== null}
            title="Continue with GitHub"
            className="w-10 h-10 rounded-full border border-white/10 bg-[#272a33] hover:bg-[#313540] text-white flex items-center justify-center transition-all duration-150 hover:scale-105 active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-1 focus:ring-blue-500/40"
          >
            {oauthLoading === 'github' ? (
              <Loader2 className="w-4 h-4 animate-spin text-gray-300" />
            ) : (
              <svg className="w-4 h-4 fill-current" viewBox="0 0 24 24">
                <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
              </svg>
            )}
          </button>
        </div>
      </div>

      {/* Styled Divider */}
      <div className="relative flex items-center justify-center my-3 select-none">
        <div className="flex-grow border-t border-white/10" />
        <span className="px-3 text-xs font-normal text-gray-400">
          or
        </span>
        <div className="flex-grow border-t border-white/10" />
      </div>

      {/* Error Announcement Banner */}
      {error && (
        <div
          role="alert"
          aria-live="polite"
          className="flex items-start justify-between space-x-2 p-3 rounded-xl border border-red-500/25 bg-red-500/10 text-red-400 text-xs transition-all duration-200"
        >
          <div className="flex items-start space-x-2">
            <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5 text-red-400" />
            <span className="leading-snug">{error}</span>
          </div>
          <button
            type="button"
            onClick={() => handleSubmit()}
            title="Retry authentication"
            className="text-[11px] font-semibold text-red-300 hover:text-white underline flex items-center space-x-1 flex-shrink-0 ml-1"
          >
            <RefreshCw className="w-3 h-3 inline mr-0.5" />
            Retry
          </button>
        </div>
      )}

      {/* Form Fields */}
      <form onSubmit={handleSubmit} noValidate className="space-y-3.5">
        
        {!isLogin && (
          <div className="space-y-1">
            <label htmlFor={fullNameId} className="text-xs font-semibold text-gray-200 select-none block">
              Full Name
            </label>
            <input
              id={fullNameId}
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Your Full Name"
              disabled={loading}
              className="w-full h-11 bg-[#272a33]/80 border border-white/10 rounded-xl py-2 px-3.5 text-sm text-white placeholder:text-gray-500 transition-all duration-200 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 disabled:opacity-50"
              required
            />
          </div>
        )}

        {/* Username or Email Field */}
        <div className="space-y-1">
          <label htmlFor={emailId} className="text-xs font-semibold text-gray-200 select-none block">
            Username or Email
          </label>
          <input
            id={emailId}
            type="text"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="Username or Email"
            disabled={loading}
            className="w-full h-11 bg-[#272a33]/80 border border-white/10 rounded-xl py-2 px-3.5 text-sm text-white placeholder:text-gray-500 transition-all duration-200 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 disabled:opacity-50"
            required
          />
        </div>

        {/* Password Field */}
        <div className="space-y-1">
          <label htmlFor={passwordId} className="text-xs font-semibold text-gray-200 select-none block">
            Password
          </label>
          <div className="relative">
            <input
              id={passwordId}
              type={showPassword ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter password"
              disabled={loading}
              className="w-full h-11 bg-[#272a33]/80 border border-white/10 rounded-xl py-2 px-3.5 pr-10 text-sm text-white placeholder:text-gray-500 transition-all duration-200 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 disabled:opacity-50"
              required
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              aria-label={showPassword ? 'Hide password' : 'Show password'}
              className="absolute right-3.5 top-3 p-0.5 text-gray-400 hover:text-white transition-colors focus:outline-none"
            >
              {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
        </div>

        {/* Remember Me & Forgot Password Row */}
        {isLogin && (
          <div className="flex items-center justify-between pt-0.5">
            <label className="flex items-center space-x-2 text-xs text-gray-300 cursor-pointer select-none group">
              <input
                type="checkbox"
                checked={rememberMe}
                onChange={(e) => setRememberMe(e.target.checked)}
                disabled={loading}
                className="w-4 h-4 rounded bg-[#272a33] border-white/20 text-blue-500 accent-blue-500 focus:ring-0 cursor-pointer"
              />
              <span className="group-hover:text-white transition-colors">Remember Me</span>
            </label>

            <Link
              to="/forgot-password"
              className="text-xs text-blue-400 hover:text-blue-300 font-medium hover:underline transition-colors focus:outline-none"
            >
              Forgot password
            </Link>
          </div>
        )}

        {/* Primary Submit Button: Green Sign In */}
        <button
          type="submit"
          disabled={loading}
          className="w-full h-11 flex items-center justify-center space-x-2 mt-5 rounded-xl bg-[#16a34a] hover:bg-[#15803d] text-white font-bold text-sm transition-all duration-150 active:scale-[0.985] disabled:opacity-50 disabled:cursor-not-allowed shadow-md hover:shadow-lg focus:outline-none focus:ring-2 focus:ring-emerald-500/40"
        >
          {loading ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin text-white" />
              <span>{isLogin ? 'Signing in...' : 'Registering...'}</span>
            </>
          ) : (
            <span>{isLogin ? 'Sign In' : 'Sign Up'}</span>
          )}
        </button>
      </form>

      {/* Card Footer: By using bugX... */}
      <div className="text-center text-[11px] text-gray-500 pt-3 mt-4 border-t border-white/[0.06]">
        By using bugX, you agree to our terms and policies.
      </div>
    </div>
  );
}

