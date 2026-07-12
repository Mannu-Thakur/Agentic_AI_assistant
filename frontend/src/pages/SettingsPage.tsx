import { useUIStore } from '../store/uiStore';
import { 
  Sun, 
  Moon, 
  Terminal, 
  ShieldAlert, 
  User,
  Sliders
} from 'lucide-react';

export default function SettingsPage() {
  const { theme, toggleTheme, developerMode, toggleDeveloperMode } = useUIStore();

  return (
    <div className="max-w-3xl mx-auto px-6 py-8 space-y-8">
      
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">System Settings</h1>
        <p className="text-muted-foreground text-xs mt-1">Configure workspace parameters and user credentials</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        
        {/* Navigation Pane Side tabs */}
        <aside className="space-y-1">
          <button className="w-full flex items-center space-x-2.5 px-3 py-2 rounded-xl text-xs font-semibold bg-secondary/50 text-foreground">
            <Sliders className="w-4 h-4 text-violet-400" />
            <span>Preferences</span>
          </button>
          <button className="w-full flex items-center space-x-2.5 px-3 py-2 rounded-xl text-xs font-semibold text-muted-foreground hover:bg-secondary/20 hover:text-foreground transition-all">
            <User className="w-4 h-4" />
            <span>Account Profile</span>
          </button>
        </aside>

        {/* Configurations pane */}
        <div className="md:col-span-2 space-y-6">
          
          {/* Theme card */}
          <div className="p-5 rounded-2xl border border-border bg-card/40 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold">Interface Theme</h3>
                <p className="text-muted-foreground text-[10px] mt-0.5">Toggle between dark and light themes</p>
              </div>
              <button 
                onClick={toggleTheme}
                className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg border border-border bg-secondary hover:bg-muted text-xs transition-all"
              >
                {theme === 'dark' ? (
                  <>
                    <Moon className="w-3.5 h-3.5 text-violet-400" />
                    <span>Dark Mode</span>
                  </>
                ) : (
                  <>
                    <Sun className="w-3.5 h-3.5 text-yellow-400" />
                    <span>Light Mode</span>
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Dev Mode HUD */}
          <div className="p-5 rounded-2xl border border-border bg-card/40 space-y-4">
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <h3 className="text-sm font-semibold flex items-center space-x-1.5">
                  <Terminal className="w-4 h-4 text-violet-400" />
                  <span>Developer Mode HUD</span>
                </h3>
                <p className="text-muted-foreground text-[10px]">
                  Expose latency, cost estimation, token counts, and retrieval context metrics
                </p>
              </div>
              <button
                onClick={toggleDeveloperMode}
                className={`w-11 h-6 rounded-full transition-colors relative flex items-center px-1 ${
                  developerMode ? 'bg-primary' : 'bg-secondary'
                }`}
              >
                <div 
                  className={`w-4 h-4 rounded-full bg-white transition-transform ${
                    developerMode ? 'translate-x-5' : 'translate-x-0'
                  }`}
                />
              </button>
            </div>
          </div>

          {/* Advanced Info */}
          <div className="p-5 rounded-2xl border border-border bg-card/40 space-y-3">
            <h3 className="text-sm font-semibold flex items-center space-x-1.5 text-red-400">
              <ShieldAlert className="w-4 h-4" />
              <span>Advanced API Config</span>
            </h3>
            <p className="text-muted-foreground text-[10px] leading-relaxed">
              Provider API credentials (Groq, Gemini, OpenRouter) can be configured directly inside your system environmental files or injected dynamically per session in the future developer console view.
            </p>
          </div>

        </div>
      </div>
    </div>
  );
}
