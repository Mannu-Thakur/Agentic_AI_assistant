import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { apiRequest } from '../services/api';
import { KeyRound, Lock, CheckCircle2, AlertCircle, ArrowLeft, Eye, EyeOff, Loader2, ShieldAlert, Check, X } from 'lucide-react';

export default function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');
  const navigate = useNavigate();

  const [verifyingToken, setVerifyingToken] = useState<boolean>(!!token);
  const [tokenValid, setTokenValid] = useState<boolean>(false);
  const [tokenError, setTokenError] = useState<string | null>(null);

  const [newPassword, setNewPassword] = useState<string>('');
  const [confirmPassword, setConfirmPassword] = useState<string>('');
  const [showPassword, setShowPassword] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(false);
  const [success, setSuccess] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Validate token in real-time on mount
  useEffect(() => {
    let isMounted = true;
    if (!token) {
      setVerifyingToken(false);
      setTokenValid(false);
      setTokenError('Missing password reset security token in URL.');
      return;
    }

    const checkToken = async () => {
      try {
        setVerifyingToken(true);
        await apiRequest(`/auth/verify-reset-token?token=${encodeURIComponent(token)}`);
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
  }, [token]);

  // Real-time password criteria verification
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
  const isFormValid = rules.minLength && rules.matchesConfirm;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!token || !tokenValid) {
      setError('Invalid or missing security token. Please request a new password reset link.');
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
          token,
          new_password: newPassword,
        },
      });
      setSuccess(true);
      setTimeout(() => {
        navigate('/login');
      }, 3500);
    } catch (err: any) {
      setError(err.message || 'Failed to reset password. The link may have expired.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Header / Back link */}
      <div>
        <Link
          to="/login"
          className="inline-flex items-center space-x-2 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors mb-2"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Back to Sign In</span>
        </Link>
      </div>

      {/* 1. Real-time Loading / Verifying Token State */}
      {verifyingToken ? (
        <div className="text-center py-10 space-y-3 animate-in fade-in duration-200">
          <Loader2 className="w-8 h-8 text-primary animate-spin mx-auto" />
          <h3 className="text-sm font-semibold text-foreground">Verifying Reset Security Token</h3>
          <p className="text-xs text-muted-foreground max-w-xs mx-auto">
            Checking validity in real-time with authentication server...
          </p>
        </div>
      ) : !tokenValid ? (
        /* 2. Invalid or Expired Token Error State */
        <div className="text-center space-y-5 py-3 animate-in fade-in zoom-in-95 duration-300">
          <div className="w-14 h-14 rounded-2xl bg-red-500/10 border border-red-500/20 text-red-400 flex items-center justify-center mx-auto shadow-lg shadow-red-500/5">
            <ShieldAlert className="w-7 h-7" />
          </div>

          <div className="space-y-2">
            <h3 className="text-xl font-semibold text-foreground">Link Invalid or Expired</h3>
            <p className="text-muted-foreground text-xs max-w-xs mx-auto leading-relaxed">
              {tokenError || 'This password reset link is invalid, has expired, or has already been used.'}
            </p>
          </div>

          <div className="pt-2">
            <Link
              to="/forgot-password"
              className="inline-flex items-center justify-center w-full py-2.5 rounded-xl bg-primary text-primary-foreground font-semibold text-xs transition-all hover:opacity-95 shadow-lg shadow-primary/20"
            >
              Request New Reset Link
            </Link>
          </div>
        </div>
      ) : success ? (
        /* 3. Success State */
        <div className="text-center space-y-4 py-2 animate-in fade-in zoom-in-95 duration-300">
          <div className="w-12 h-12 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 flex items-center justify-center mx-auto shadow-lg shadow-emerald-500/5">
            <CheckCircle2 className="w-6 h-6" />
          </div>

          <div className="space-y-1.5">
            <h3 className="text-xl font-semibold text-foreground">Password Reset Complete!</h3>
            <p className="text-muted-foreground text-xs max-w-xs mx-auto">
              Your password has been successfully updated. Active sessions have been invalidated for your security.
            </p>
          </div>

          <p className="text-xs text-primary font-medium animate-pulse">
            Redirecting to sign-in page in a few seconds...
          </p>

          <Link
            to="/login"
            className="block w-full py-2.5 rounded-xl bg-primary text-primary-foreground font-semibold text-xs transition-all hover:opacity-95 shadow-lg shadow-primary/20"
          >
            Go to Login Now
          </Link>
        </div>
      ) : (
        /* 4. Active Reset Password Form */
        <div className="space-y-6 animate-in fade-in duration-200">
          <div className="text-center space-y-1">
            <h3 className="text-xl font-semibold text-foreground">Set New Password</h3>
            <p className="text-muted-foreground text-xs max-w-xs mx-auto">
              Create a strong password to protect your account.
            </p>
          </div>

          {error && (
            <div className="flex items-center space-x-2 p-3.5 rounded-xl border border-red-500/20 bg-red-500/5 text-red-400 text-xs">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* New Password */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-muted-foreground">New Password</label>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="••••••••••••"
                  className="w-full bg-secondary/30 border border-border rounded-xl py-2 px-3 pl-10 pr-10 text-sm focus:outline-none focus:border-primary text-foreground"
                  required
                  minLength={8}
                  autoFocus
                />
                <KeyRound className="absolute left-3.5 top-3 w-4 h-4 text-muted-foreground" />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3.5 top-3 text-muted-foreground hover:text-foreground transition-colors"
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>

              {/* Strength Meter */}
              {newPassword && (
                <div className="space-y-1.5 pt-1">
                  <div className="flex items-center justify-between text-[10px] text-muted-foreground">
                    <span>
                      Password strength: <strong className="text-foreground">{strength.label}</strong>
                    </span>
                    <span>Min. 8 characters</span>
                  </div>
                  <div className="h-1.5 w-full bg-secondary/50 rounded-full overflow-hidden flex gap-1">
                    {[1, 2, 3, 4].map((level) => (
                      <div
                        key={level}
                        className={`h-full flex-1 rounded-full transition-all duration-300 ${
                          level <= strength.score ? strength.color : 'bg-secondary/40'
                        }`}
                      />
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Confirm Password */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-muted-foreground">Confirm New Password</label>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="••••••••••••"
                  className="w-full bg-secondary/30 border border-border rounded-xl py-2 px-3 pl-10 text-sm focus:outline-none focus:border-primary text-foreground"
                  required
                />
                <Lock className="absolute left-3.5 top-3 w-4 h-4 text-muted-foreground" />
              </div>
            </div>

            {/* Real-time Requirement Indicators */}
            {newPassword && (
              <div className="p-3 rounded-xl border border-border bg-secondary/20 space-y-1.5 text-[11px]">
                <div className="font-semibold text-muted-foreground mb-1">Password Requirements:</div>
                <div className="grid grid-cols-2 gap-1">
                  <div className={`flex items-center space-x-1.5 ${rules.minLength ? 'text-emerald-400' : 'text-red-400 font-semibold'}`}>
                    {rules.minLength ? <Check className="w-3.5 h-3.5" /> : <X className="w-3.5 h-3.5" />}
                    <span>8+ characters (Required)</span>
                  </div>
                  <div className={`flex items-center space-x-1.5 ${rules.hasUpper ? 'text-emerald-400' : 'text-muted-foreground'}`}>
                    {rules.hasUpper ? <Check className="w-3.5 h-3.5" /> : <span className="w-3.5 h-3.5 text-center">•</span>}
                    <span>Uppercase (Recommended)</span>
                  </div>
                  <div className={`flex items-center space-x-1.5 ${rules.hasLower ? 'text-emerald-400' : 'text-muted-foreground'}`}>
                    {rules.hasLower ? <Check className="w-3.5 h-3.5" /> : <span className="w-3.5 h-3.5 text-center">•</span>}
                    <span>Lowercase (Recommended)</span>
                  </div>
                  <div className={`flex items-center space-x-1.5 ${rules.hasNumber ? 'text-emerald-400' : 'text-muted-foreground'}`}>
                    {rules.hasNumber ? <Check className="w-3.5 h-3.5" /> : <span className="w-3.5 h-3.5 text-center">•</span>}
                    <span>Number 0-9 (Recommended)</span>
                  </div>
                </div>
                {confirmPassword && (
                  <div className={`flex items-center space-x-1.5 pt-1 border-t border-border/40 ${rules.matchesConfirm ? 'text-emerald-400' : 'text-red-400 font-semibold'}`}>
                    {rules.matchesConfirm ? <Check className="w-3.5 h-3.5" /> : <X className="w-3.5 h-3.5" />}
                    <span>Passwords match (Required)</span>
                  </div>
                )}
              </div>
            )}

            <button
              type="submit"
              disabled={loading || !isFormValid}
              className="w-full flex items-center justify-center space-x-2 py-2.5 rounded-xl bg-primary text-primary-foreground font-semibold text-sm transition-all hover:opacity-95 disabled:opacity-50 mt-6 shadow-lg shadow-primary/20"
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Updating Password...</span>
                </>
              ) : (
                <>
                  <KeyRound className="w-4 h-4" />
                  <span>Reset Password</span>
                </>
              )}
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
