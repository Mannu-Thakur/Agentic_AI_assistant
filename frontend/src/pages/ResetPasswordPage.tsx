import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { apiRequest } from '../services/api';
import { KeyRound, Lock, CheckCircle2, AlertCircle, Eye, EyeOff, Loader2, ShieldAlert, Check, X } from 'lucide-react';

export default function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const urlToken = searchParams.get('token');
  const navigate = useNavigate();

  const [token, setToken] = useState<string>(urlToken || '');
  const [verifyingToken, setVerifyingToken] = useState<boolean>(!!urlToken);
  const [tokenValid, setTokenValid] = useState<boolean>(!urlToken); // If no token in URL, allow manual entry
  const [tokenError, setTokenError] = useState<string | null>(null);

  const [newPassword, setNewPassword] = useState<string>('');
  const [confirmPassword, setConfirmPassword] = useState<string>('');
  const [showPassword, setShowPassword] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(false);
  const [success, setSuccess] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    if (!urlToken) {
      setVerifyingToken(false);
      setTokenValid(true);
      return;
    }

    const checkToken = async () => {
      try {
        setVerifyingToken(true);
        await apiRequest(`/auth/verify-reset-token?token=${encodeURIComponent(urlToken)}`);
        if (isMounted) {
          setTokenValid(true);
          setTokenError(null);
        }
      } catch (err: any) {
        if (isMounted) {
          setTokenValid(false);
          setTokenError(err.message || 'This password reset link is invalid or has expired.');
        }
      } finally {
        if (isMounted) {
          setVerifyingToken(false);
        }
      }
    };

    checkToken();
    return () => {
      isMounted = false;
    };
  }, [urlToken]);

  const rules = {
    minLength: newPassword.length >= 8,
    hasUpper: /[A-Z]/.test(newPassword),
    hasLower: /[a-z]/.test(newPassword),
    hasNumber: /[0-9]/.test(newPassword),
    matchesConfirm: confirmPassword.length > 0 && newPassword === confirmPassword,
  };

  const getPasswordStrength = (pwd: string) => {
    if (!pwd) return { score: 0, label: '', color: '' };
    let score = 0;
    if (pwd.length >= 8) score += 1;
    if (/[A-Z]/.test(pwd) && /[a-z]/.test(pwd)) score += 1;
    if (/[0-9]/.test(pwd)) score += 1;
    if (/[^A-Za-z0-9]/.test(pwd)) score += 1;

    if (score <= 1) return { score: 1, label: 'Weak', color: 'bg-red-500' };
    if (score === 2) return { score: 2, label: 'Fair', color: 'bg-yellow-500' };
    if (score === 3) return { score: 3, label: 'Good', color: 'bg-blue-500' };
    return { score: 4, label: 'Strong', color: 'bg-emerald-500' };
  };

  const strength = getPasswordStrength(newPassword);
  const isFormValid = rules.minLength && rules.matchesConfirm && token.trim().length > 0;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!token.trim()) {
      setError('Please provide a valid security token or verification code.');
      return;
    }

    if (!isFormValid) {
      setError('Please ensure all password requirements are satisfied before continuing.');
      return;
    }

    setLoading(true);

    try {
      await apiRequest('/auth/reset-password', {
        method: 'POST',
        json: {
          token: token.trim(),
          new_password: newPassword,
        },
      });
      setSuccess(true);
      setTimeout(() => {
        navigate('/login');
      }, 3000);
    } catch (err: any) {
      setError(err.message || 'Failed to reset password. The link or token may have expired.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4 animate-in fade-in-0 duration-200 text-left">
      
      {/* Top Logo Badge */}
      <div className="flex justify-center">
        <div className="w-12 h-12 rounded-xl bg-[#232731] border border-white/10 flex items-center justify-center shadow-md">
          <KeyRound className="w-6 h-6 text-white" />
        </div>
      </div>

      {/* Header Title & Subtitle */}
      <div className="text-center">
        <h2 className="text-xl font-bold text-white tracking-tight">
          Reset your password
        </h2>
        <p className="text-gray-400 text-xs mt-1 font-normal">
          Remember your password?{' '}
          <Link
            to="/login"
            className="text-[#2563eb] hover:text-blue-400 font-semibold hover:underline transition-colors"
          >
            Sign in here
          </Link>
        </p>
      </div>

      {/* Step Indicator Bar */}
      <div className="flex items-center justify-center gap-2.5 my-5 select-none">
        {/* Step 1: Identity (Completed) */}
        <div className="flex items-center space-x-1.5">
          <span className="w-5 h-5 rounded-full bg-emerald-600 text-white text-[11px] font-bold flex items-center justify-center border border-emerald-500">
            ✓
          </span>
          <span className="text-xs font-semibold text-emerald-400">Identity</span>
        </div>

        {/* Connecting Line */}
        <div className="h-[1px] w-16 bg-blue-500/50" />

        {/* Step 2: New Password (Active) */}
        <div className="flex items-center space-x-1.5">
          <span className="w-5 h-5 rounded-full bg-[#2563eb] text-white text-[11px] font-bold flex items-center justify-center border border-blue-400">
            2
          </span>
          <span className="text-xs font-semibold text-blue-400">New Password</span>
        </div>
      </div>

      {verifyingToken ? (
        <div className="text-center py-8 space-y-3">
          <Loader2 className="w-7 h-7 text-blue-500 animate-spin mx-auto" />
          <h3 className="text-sm font-semibold text-white">Verifying Security Token</h3>
        </div>
      ) : !tokenValid ? (
        <div className="text-center space-y-4 py-3">
          <div className="w-10 h-10 rounded-full bg-red-500/10 border border-red-500/20 text-red-400 flex items-center justify-center mx-auto">
            <ShieldAlert className="w-5 h-5" />
          </div>
          <div className="space-y-1">
            <h3 className="text-sm font-bold text-white">Link Expired or Invalid</h3>
            <p className="text-xs text-gray-400 max-w-xs mx-auto">
              {tokenError || 'This reset token is invalid or has expired.'}
            </p>
          </div>
          <Link
            to="/forgot-password"
            className="w-full h-11 flex items-center justify-center rounded-xl bg-[#2563eb] hover:bg-[#1d4ed8] text-white font-semibold text-xs transition-all shadow-md mt-4"
          >
            Request New Reset Code
          </Link>
        </div>
      ) : success ? (
        <div className="text-center space-y-4 py-3 animate-in fade-in zoom-in-95 duration-300">
          <div className="w-10 h-10 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 flex items-center justify-center mx-auto">
            <CheckCircle2 className="w-5 h-5" />
          </div>
          <div className="space-y-1">
            <h3 className="text-sm font-bold text-white">Password Reset Successful!</h3>
            <p className="text-xs text-gray-300 max-w-xs mx-auto">
              Your password has been updated. Redirecting to login...
            </p>
          </div>
          <Link
            to="/login"
            className="w-full h-11 flex items-center justify-center rounded-xl bg-[#16a34a] hover:bg-[#15803d] text-white font-semibold text-xs transition-all shadow-md mt-4"
          >
            Sign In Now
          </Link>
        </div>
      ) : (
        <form onSubmit={handleSubmit} noValidate className="space-y-3.5">
          {error && (
            <div role="alert" className="flex items-center space-x-2 p-3 rounded-xl border border-red-500/25 bg-red-500/10 text-red-400 text-xs">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Token / Verification Code input if not present in URL */}
          {!urlToken && (
            <div className="space-y-1">
              <label className="text-xs font-semibold text-gray-200 select-none block">
                Verification Code / Security Token
              </label>
              <input
                type="text"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                placeholder="Enter reset token or code"
                className="w-full h-11 bg-[#272a33]/80 border border-white/10 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 rounded-xl py-2 px-3.5 text-sm text-white placeholder:text-gray-500 transition-all duration-200"
                required
              />
            </div>
          )}

          {/* New Password */}
          <div className="space-y-1">
            <label className="text-xs font-semibold text-gray-200 select-none block">New Password</label>
            <div className="relative">
              <input
                type={showPassword ? 'text' : 'password'}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="••••••••••••"
                className="w-full h-11 bg-[#272a33]/80 border border-white/10 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 rounded-xl py-2 px-3.5 pl-10 pr-10 text-sm text-white placeholder:text-gray-500 transition-all duration-200"
                required
                minLength={8}
              />
              <KeyRound className="absolute left-3.5 top-3.5 w-4 h-4 text-gray-400 pointer-events-none" />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3.5 top-3 p-0.5 text-gray-400 hover:text-white transition-colors"
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {/* Confirm New Password */}
          <div className="space-y-1">
            <label className="text-xs font-semibold text-gray-200 select-none block">Confirm Password</label>
            <div className="relative">
              <input
                type={showPassword ? 'text' : 'password'}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="••••••••••••"
                className="w-full h-11 bg-[#272a33]/80 border border-white/10 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 rounded-xl py-2 px-3.5 pl-10 text-sm text-white placeholder:text-gray-500 transition-all duration-200"
                required
              />
              <Lock className="absolute left-3.5 top-3.5 w-4 h-4 text-gray-400 pointer-events-none" />
            </div>
          </div>

          {/* Strength & Rules Indicators */}
          {newPassword && (
            <div className="p-3 rounded-xl border border-white/10 bg-[#272a33]/40 space-y-1.5 text-[11px]">
              <div className="flex items-center justify-between text-gray-400">
                <span>Strength: <strong className="text-white">{strength.label}</strong></span>
                <span>Min. 8 chars</span>
              </div>
              <div className="grid grid-cols-2 gap-1 pt-1">
                <div className={`flex items-center space-x-1 ${rules.minLength ? 'text-emerald-400' : 'text-red-400'}`}>
                  {rules.minLength ? <Check className="w-3 h-3" /> : <X className="w-3 h-3" />}
                  <span>8+ characters</span>
                </div>
                <div className={`flex items-center space-x-1 ${rules.matchesConfirm ? 'text-emerald-400' : 'text-gray-400'}`}>
                  {rules.matchesConfirm ? <Check className="w-3 h-3" /> : <span className="w-3 text-center">•</span>}
                  <span>Passwords match</span>
                </div>
              </div>
            </div>
          )}

          <button
            type="submit"
            disabled={loading || !isFormValid}
            className="w-full h-11 flex items-center justify-center space-x-2 mt-5 rounded-xl bg-[#2563eb] hover:bg-[#1d4ed8] text-white font-semibold text-xs transition-all duration-150 active:scale-[0.985] disabled:opacity-50 disabled:cursor-not-allowed shadow-md hover:shadow-lg focus:outline-none focus:ring-2 focus:ring-blue-500/40"
          >
            {loading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin text-white" />
                <span>Updating Password...</span>
              </>
            ) : (
              <span>Reset Password</span>
            )}
          </button>
        </form>
      )}
    </div>
  );
}

