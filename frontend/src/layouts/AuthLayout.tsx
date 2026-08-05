import { Outlet, useNavigate } from 'react-router-dom';
import { X } from 'lucide-react';

export default function AuthLayout() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen relative flex items-center justify-center p-4 sm:p-6 bg-[#0c0e14] text-foreground overflow-x-hidden selection:bg-blue-500/20 selection:text-white">

      {/* Subtle ambient background glow */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] rounded-full bg-blue-600/[0.03] blur-[140px]" />
      </div>

      {/* Main Elevated Card Container */}
      <div className="w-full max-w-[430px] relative z-10 my-auto">
        <div className="relative bg-[#1c1f26] rounded-2xl shadow-[0_25px_70px_-15px_rgba(0,0,0,0.8)] p-6 sm:p-8 border border-white/[0.09] transition-all duration-300 animate-in fade-in-0 zoom-in-95">

          {/* Close Button Top Right */}
          <button
            type="button"
            onClick={() => navigate('/')}
            className="absolute top-5 right-5 p-1 rounded-lg text-gray-400 hover:text-white hover:bg-white/5 transition-colors focus:outline-none focus:ring-1 focus:ring-blue-500/40"
            title="Close"
            aria-label="Close"
          >
            <X className="w-4 h-4" />
          </button>

          <main>
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
}


