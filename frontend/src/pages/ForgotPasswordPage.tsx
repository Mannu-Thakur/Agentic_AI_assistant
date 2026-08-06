import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { apiRequest } from '../services/api';
import { Mail, Shield, AlertCircle, Loader2, CheckCircle2 } from 'lucide-react';

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [submitted, setSubmitted] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const navigate = useNavigate();
  const emailId = crypto.randomUUID();

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
      // Even if backend fails email send, advance or display detail
      setSubmitted(true);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4 animate-in fade-in-0 duration-200 text-left">
      
      {/* Top Logo Badge */}
      <div className="flex justify-center">
        <div className="w-12 h-12 rounded-xl bg-[#232731] border border-white/10 flex items-center justify-center shadow-md">
          <Shield className="w-6 h-6 text-white" />
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
        {/* Step 1: Identity */}
        <div className="flex items-center space-x-1.5">
          <span className="w-5 h-5 rounded-full bg-[#2563eb] text-white text-[11px] font-bold flex items-center justify-center border border-blue-400">
            1
          </span>
          <span className="text-xs font-semibold text-blue-400">Identity</span>
        </div>

        {/* Connecting Line */}
        <div className="h-[1px] w-16 bg-white/15" />

        {/* Step 2: New Password */}
        <div className="flex items-center space-x-1.5">
          <span className="w-5 h-5 rounded-full border border-white/20 text-gray-400 text-[11px] font-medium flex items-center justify-center">
            2
          </span>
          <span className="text-xs font-medium text-gray-500">New Password</span>
        </div>
      </div>

      {/* Error Announcement */}
      {error && (
        <div role="alert" className="flex items-center space-x-2 p-3 rounded-xl border border-red-500/25 bg-red-500/10 text-red-400 text-xs">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {submitted ? (
        /* Submitted State -> Verification Instructions */
        <div className="text-center space-y-4 py-3 animate-in fade-in zoom-in-95 duration-200">
          <div className="w-10 h-10 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 flex items-center justify-center mx-auto">
            <CheckCircle2 className="w-5 h-5" />
          </div>
          <div className="space-y-1">
            <h3 className="text-sm font-bold text-white">Verification Sent!</h3>
            <p className="text-xs text-gray-300 max-w-xs mx-auto">
              Instructions & reset code sent to <span className="font-semibold text-white">{email}</span>.
            </p>
          </div>

          <button
            type="button"
            onClick={() => navigate('/reset-password')}
            className="w-full h-11 flex items-center justify-center space-x-2 rounded-xl bg-[#2563eb] hover:bg-[#1d4ed8] text-white font-semibold text-xs transition-all shadow-md mt-4"
          >
            <span>Proceed to Enter Code</span>
          </button>
        </div>
      ) : (
        /* Form State */
        <form onSubmit={handleSubmit} noValidate className="space-y-3.5">
          
          {/* Email Address */}
          <div className="space-y-1">
            <label htmlFor={emailId} className="text-xs font-semibold text-gray-200 select-none block">
              Email address
            </label>
            <div className="relative">
              <input
                id={emailId}
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@example.com"
                disabled={loading}
                className="w-full h-11 bg-[#272a33]/80 border border-blue-500/80 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 rounded-xl py-2 px-3.5 pl-10 text-sm text-white placeholder:text-gray-500 transition-all duration-200 disabled:opacity-50"
                required
                autoFocus
              />
              <Mail className="absolute left-3.5 top-3.5 w-4 h-4 text-gray-400 pointer-events-none" />
            </div>
          </div>



          {/* Primary Action Button: Blue Send Verification Code */}
          <button
            type="submit"
            disabled={loading}
            className="w-full h-11 flex items-center justify-center space-x-2 mt-5 rounded-xl bg-[#2563eb] hover:bg-[#1d4ed8] text-white font-semibold text-xs transition-all duration-150 active:scale-[0.985] disabled:opacity-50 disabled:cursor-not-allowed shadow-md hover:shadow-lg focus:outline-none focus:ring-2 focus:ring-blue-500/40"
          >
            {loading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin text-white" />
                <span>Sending Code...</span>
              </>
            ) : (
              <>
                <Shield className="w-4 h-4" />
                <span>Send Verification Code</span>
              </>
            )}
          </button>
        </form>
      )}
    </div>
  );
}

