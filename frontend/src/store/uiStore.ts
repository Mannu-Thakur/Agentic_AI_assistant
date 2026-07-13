import { create } from 'zustand';

type ViewMode = 'chat' | 'memories' | 'documents';
type ThemeType = 'dark' | 'light-dark' | 'light';

interface UIState {
  theme: ThemeType;
  developerMode: boolean;
  sidebarOpen: boolean;   // true = expanded, false = icon-only (desktop)
  activeView: ViewMode;
  toggleTheme: () => void;
  setTheme: (theme: ThemeType) => void;
  toggleDeveloperMode: () => void;
  setDeveloperMode: (enabled: boolean) => void;
  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  setActiveView: (view: ViewMode) => void;
}


function applyTheme(theme: ThemeType) {
  const root = document.documentElement;
  root.classList.remove('dark', 'light-dark', 'light');
  if (theme === 'light-dark') root.classList.add('light-dark');
  if (theme === 'light') root.classList.add('light');
}

// Apply theme immediately on module load so it's set before first render
const _savedTheme = (localStorage.getItem('theme') as ThemeType) || 'dark';
applyTheme(_savedTheme);

export const useUIStore = create<UIState>((set) => ({
  theme: _savedTheme,
  developerMode: localStorage.getItem('developer_mode') === 'true',
  // Default: sidebar expanded on desktop
  sidebarOpen: localStorage.getItem('sidebar_open') !== 'false',
  activeView: 'chat',

  toggleTheme: () => set((state) => {
    const next: ThemeType = state.theme === 'dark' ? 'light-dark' : state.theme === 'light-dark' ? 'light' : 'dark';
    localStorage.setItem('theme', next);
    applyTheme(next);
    return { theme: next };
  }),

  setTheme: (theme) => {
    localStorage.setItem('theme', theme);
    applyTheme(theme);
    set({ theme });
  },

  toggleDeveloperMode: () => set((state) => {
    const next = !state.developerMode;
    localStorage.setItem('developer_mode', String(next));
    return { developerMode: next };
  }),

  setDeveloperMode: (enabled) => {
    localStorage.setItem('developer_mode', String(enabled));
    set({ developerMode: enabled });
  },

  toggleSidebar: () => set((state) => {
    const next = !state.sidebarOpen;
    localStorage.setItem('sidebar_open', String(next));
    return { sidebarOpen: next };
  }),

  setSidebarOpen: (open) => {
    localStorage.setItem('sidebar_open', String(open));
    set({ sidebarOpen: open });
  },

  setActiveView: (view) => set({ activeView: view }),
}));
