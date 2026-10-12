import { useEffect } from 'react';
import { Outlet } from 'react-router-dom';
import { useUIStore } from '../store/uiStore';

// Accent colour → CSS variable mapping
const ACCENT_VARS: Record<string, string> = {
  default: '217 91% 60%',
  emerald: '158 64% 52%',
  indigo:  '239 84% 67%',
  amber:   '38 92% 50%',
  rose:    '350 89% 60%',
  violet:  '258 90% 66%',
};

export default function AppLayout() {
  const { theme, accentColor, fontSize, compactMode } = useUIStore();

  useEffect(() => {
    const root = document.documentElement;

    // Theme class
    root.classList.remove('light', 'dark');
    if (theme === 'system') {
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      root.classList.add(prefersDark ? 'dark' : 'light');
    } else {
      root.classList.add(theme);
    }

    // Accent colour CSS variable
    const hsl = ACCENT_VARS[accentColor] ?? ACCENT_VARS.default;
    root.style.setProperty('--accent', hsl);

    // Font size class
    root.classList.remove('font-sm', 'font-lg');
    if (fontSize === 'sm') root.classList.add('font-sm');
    if (fontSize === 'lg') root.classList.add('font-lg');

    // Compact mode
    root.classList.toggle('compact', compactMode);
  }, [theme, accentColor, fontSize, compactMode]);

  return (
    <div className="h-screen h-[100dvh] w-screen flex flex-col overflow-hidden bg-background text-foreground">
      {/* ─── Main content fills remaining height ─── */}
      <main className="flex-1 min-h-0 flex overflow-hidden" role="main">
        <Outlet />
      </main>
    </div>
  );
}
