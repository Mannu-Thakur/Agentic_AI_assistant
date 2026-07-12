import { Outlet } from 'react-router-dom';
import { Cpu } from 'lucide-react';

export default function AuthLayout() {
  return (
    <div className="min-h-screen relative flex items-center justify-center p-4 bg-background overflow-hidden">
      
      {/* Dynamic Background Gradients */}
      <div className="absolute top-[-20%] left-[-10%] w-[50%] h-[50%] rounded-full bg-violet-600/10 blur-[120px] pointer-events-none" />
      <div className="absolute bottom-[-20%] right-[-10%] w-[50%] h-[50%] rounded-full bg-indigo-600/10 blur-[120px] pointer-events-none" />

      {/* Main Container Card */}
      <div className="w-full max-w-md relative z-10 glass rounded-3xl shadow-2xl p-8 border border-border">
        
        {/* Title branding logo */}
        <div className="flex flex-col items-center mb-8">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-violet-600 to-indigo-600 flex items-center justify-center shadow-lg shadow-violet-900/30 mb-3">
            <Cpu className="w-6 h-6 text-white" />
          </div>
          <h2 className="text-2xl font-bold tracking-tight text-foreground">Omni Workspace</h2>
          <p className="text-muted-foreground text-xs mt-1">Production-Grade Agent Orchestrator</p>
        </div>

        {/* Children routers */}
        <Outlet />
      </div>
    </div>
  );
}
