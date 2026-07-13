import { Outlet } from 'react-router-dom';
import Logo from '../components/ui/Logo';

export default function AuthLayout() {
  return (
    <div className="min-h-screen relative flex items-center justify-center p-4 bg-background overflow-hidden">

      {/* Ambient background glows */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -top-1/4 -left-1/4 w-[60%] h-[60%] rounded-full
                        bg-accent/4 blur-[120px] animate-pulse" style={{ animationDuration: '8s' }} />
        <div className="absolute -bottom-1/4 -right-1/4 w-[60%] h-[60%] rounded-full
                        bg-accent/3 blur-[120px] animate-pulse" style={{ animationDuration: '12s' }} />
        {/* Grid overlay */}
        <div className="absolute inset-0 opacity-[0.02]"
             style={{ backgroundImage: 'linear-gradient(hsl(var(--border)) 1px, transparent 1px), linear-gradient(90deg, hsl(var(--border)) 1px, transparent 1px)', backgroundSize: '40px 40px' }} />
      </div>

      {/* Card */}
      <div className="w-full max-w-[400px] relative z-10">
        <div className="glass-heavy rounded-2xl shadow-2xl p-8 border border-border animate-fade-in">

          {/* Branding */}
          <div className="flex flex-col items-center mb-8 space-y-2">
            <div className="mb-1">
              <Logo size={36} />
            </div>
            <h1 className="text-xl font-semibold text-foreground tracking-tight">Omni AI Workspace</h1>
            <p className="text-foreground-3 text-xs">Production-grade agent orchestrator</p>
          </div>

          <Outlet />
        </div>

        <p className="text-center text-foreground-3 text-[11px] mt-5">
          © {new Date().getFullYear()} Omni Systems. All rights reserved.
        </p>
      </div>
    </div>
  );
}
