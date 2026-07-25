import { useState, useEffect } from 'react';
import { Terminal, Shield, Cpu, RefreshCw } from 'lucide-react';

function App() {
  const [healthStatus, setHealthStatus] = useState<string>('checking...');
  const [theme, setTheme] = useState<'dark' | 'light'>('dark');

  useEffect(() => {
    // Check local API health
    fetch('/health')
      .then((res) => res.json())
      .then((data) => {
        if (data.status === 'healthy') {
          setHealthStatus('API Connected');
        } else {
          setHealthStatus('API Unhealthy');
        }
      })
      .catch(() => {
        setHealthStatus('API Disconnected');
      });
  }, []);

  const toggleTheme = () => {
    const nextTheme = theme === 'dark' ? 'light' : 'dark';
    setTheme(nextTheme);
    document.documentElement.classList.toggle('light', nextTheme === 'light');
  };

  return (
    <div className={`min-h-screen flex flex-col justify-between transition-colors duration-300 ${theme === 'dark' ? 'bg-background text-foreground' : 'light bg-background text-foreground'}`}>
      
      {/* Header */}
      <header className="border-b border-border glass px-6 py-4 flex items-center justify-between sticky top-0 z-50">
        <div className="flex items-center space-x-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-violet-600 to-indigo-600 flex items-center justify-center shadow-lg shadow-violet-900/20">
            <Cpu className="w-5 h-5 text-white" />
          </div>
          <span className="font-semibold text-lg tracking-tight">openChat Workspace</span>
        </div>
        <button 
          onClick={toggleTheme}
          className="px-3 py-1.5 rounded-lg border border-border bg-secondary text-secondary-foreground hover:bg-muted text-sm transition-all"
        >
          Toggle {theme === 'dark' ? 'Light' : 'Dark'} Mode
        </button>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col items-center justify-center p-6 text-center max-w-4xl mx-auto space-y-8">
        <div className="space-y-4">
          <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-full border border-violet-500/20 bg-violet-500/5 text-violet-400 text-xs font-semibold">
            <span>Milestone 1 Complete</span>
          </div>
          <h1 className="text-4xl md:text-5xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-violet-400 to-indigo-500">
            Engineered for Production AI Platform Placements
          </h1>
          <p className="text-muted-foreground text-base max-w-xl mx-auto leading-relaxed">
            Welcome to your flagship agentic workspace. The scaffolding, container configurations, and developer routing channels are successfully configured.
          </p>
        </div>

        {/* Dashboard Status Metrics */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 w-full max-w-3xl">
          <div className="p-5 rounded-2xl border border-border bg-card shadow-sm flex flex-col items-center space-y-2">
            <div className="p-3 rounded-xl bg-violet-600/10 text-violet-400">
              <Terminal className="w-6 h-6" />
            </div>
            <h3 className="font-medium">Backend Server</h3>
            <span className="text-xs text-muted-foreground">FastAPI running on :8080</span>
          </div>

          <div className="p-5 rounded-2xl border border-border bg-card shadow-sm flex flex-col items-center space-y-2">
            <div className="p-3 rounded-xl bg-green-600/10 text-green-400">
              <Shield className="w-6 h-6" />
            </div>
            <h3 className="font-medium">Service Health</h3>
            <span className={`text-xs font-semibold uppercase ${healthStatus.includes('Connected') ? 'text-green-500' : 'text-yellow-500'}`}>
              {healthStatus}
            </span>
          </div>

          <div className="p-5 rounded-2xl border border-border bg-card shadow-sm flex flex-col items-center space-y-2">
            <div className="p-3 rounded-xl bg-indigo-600/10 text-indigo-400">
              <RefreshCw className="w-6 h-6" />
            </div>
            <h3 className="font-medium">Container Engine</h3>
            <span className="text-xs text-muted-foreground">Docker Compose Configured</span>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-border py-4 px-6 text-center text-xs text-muted-foreground bg-card/20">
        &copy; {new Date().getFullYear()} openChat Systems. Production flagship release.
      </footer>
    </div>
  );
}

export default App;
