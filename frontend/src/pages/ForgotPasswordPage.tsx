import { useState } from 'react';
import { Link } from 'react-router-dom';
import { apiRequest } from '../services/api';
import { Mail, ArrowLeft, Send, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react';

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [submitted, setSubmitted] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const isEmailValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!isEmailValid) {
      setError('Please enter a valid email address.');
      return;
    }

    setLoading(true);

    try {
      await apiRequest<{ detail: string }>('/auth/forgot-password', {
        method: 'POST',
        json: { email: email.trim() },
      });

      setSubmitted(true);
    } catch (err: any) {
      setError(err.message || 'Failed to request password reset. Please try again.');
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
          className="inline-flex items-center space-x-2 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors mb-4"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Back to Sign In</span>
        </Link>
      </div>

      {submitted ? (
        /* Success State */
        <div className="text-center space-y-4 py-2 animate-in fade-in zoom-in-95 duration-300">
          <div className="w-12 h-12 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 flex items-center justify-center mx-auto shadow-lg shadow-emerald-500/5">
            <CheckCircle2 className="w-6 h-6" />
          </div>

          <div className="space-y-1.5">
            <h3 className="text-xl font-semibold text-foreground">Check Your Email</h3>
            <p className="text-muted-foreground text-xs max-w-sm mx-auto leading-relaxed">
              If an account is associated with <span className="font-semibold text-foreground">{email}</span>, we've sent instructions to reset your password.
            </p>
          </div>

          <div className="p-3.5 rounded-xl border border-border bg-secondary/20 text-xs text-muted-foreground space-y-1 text-left">
            <div className="font-medium text-foreground">Didn't receive the email?</div>
            <ul className="list-disc list-inside space-y-0.5 text-[11px]">
              <li>Check your spam or junk folder</li>
              <li>Make sure you entered the correct email address</li>
              <li>In development mode, check your backend server console</li>
            </ul>
          </div>

          <div className="pt-2 flex flex-col space-y-2">
            <button
              onClick={() => {
                setSubmitted(false);
                setError(null);
              }}
              className="w-full py-2.5 rounded-xl border border-border bg-secondary/30 hover:bg-secondary/60 text-xs font-semibold text-foreground transition-all"
            >
              Try Another Email
            </button>

            <Link
              to="/login"
              className="w-full py-2.5 rounded-xl bg-primary text-primary-foreground text-center font-semibold text-xs transition-all hover:opacity-95 shadow-lg shadow-primary/20"
            >
              Return to Login
            </Link>
          </div>
        </div>
      ) : (
        /* Request Form State */
        <div className="space-y-6">
          <div className="text-center space-y-1">
            <h3 className="text-xl font-semibold text-foreground">Forgot Password?</h3>
            <p className="text-muted-foreground text-xs max-w-xs mx-auto">
              Enter your registered email address and we'll send you a link to reset your password.
            </p>
          </div>

          {error && (
            <div className="flex items-center space-x-2 p-3.5 rounded-xl border border-red-500/20 bg-red-500/5 text-red-400 text-xs">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-muted-foreground">Email Address</label>
              <div className="relative">
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="developer@omni.ai"
                  className={`w-full bg-secondary/30 border rounded-xl py-2 px-3 pl-10 text-sm focus:outline-none text-foreground transition-colors ${
                    email && !isEmailValid ? 'border-red-500/60 focus:border-red-500' : 'border-border focus:border-primary'
                  }`}
                  required
                  autoFocus
                />
                <Mail className="absolute left-3.5 top-3 w-4 h-4 text-muted-foreground" />
              </div>
              {email && !isEmailValid && (
                <p className="text-[11px] text-red-400">Please enter a valid email address format</p>
              )}
            </div>

            <button
              type="submit"
              disabled={loading || !isEmailValid}
              className="w-full flex items-center justify-center space-x-2 py-2.5 rounded-xl bg-primary text-primary-foreground font-semibold text-sm transition-all hover:opacity-95 disabled:opacity-50 mt-6 shadow-lg shadow-primary/20"
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Sending Request...</span>
                </>
              ) : (
                <>
                  <Send className="w-4 h-4" />
                  <span>Send Reset Link</span>
                </>
              )}
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
