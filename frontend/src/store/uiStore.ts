import { create } from 'zustand';

type ViewMode = 'chat' | 'memories' | 'documents';

interface UIState {
  theme: 'dark' | 'light';
  developerMode: boolean;
  sidebarOpen: boolean;
  activeView: ViewMode;
  toggleTheme: () => void;
  setTheme: (theme: 'dark' | 'light') => void;
  toggleDeveloperMode: () => void;
  setDeveloperMode: (enabled: boolean) => void;
  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  setActiveView: (view: ViewMode) => void;
}

export const useUIStore = create<UIState>((set) => ({
  theme: (localStorage.getItem('theme') as 'dark' | 'light') || 'dark',
  developerMode: localStorage.getItem('developer_mode') === 'true',
  sidebarOpen: true,
  activeView: 'chat',

  toggleTheme: () => set((state) => {
    const nextTheme = state.theme === 'dark' ? 'light' : 'dark';
    localStorage.setItem('theme', nextTheme);
    document.documentElement.classList.toggle('light', nextTheme === 'light');
    return { theme: nextTheme };
  }),

  setTheme: (theme) => {
    localStorage.setItem('theme', theme);
    document.documentElement.classList.toggle('light', theme === 'light');
    set({ theme });
  },

  toggleDeveloperMode: () => set((state) => {
    const nextVal = !state.developerMode;
    localStorage.setItem('developer_mode', String(nextVal));
    return { developerMode: nextVal };
  }),

  setDeveloperMode: (enabled) => {
    localStorage.setItem('developer_mode', String(enabled));
    set({ developerMode: enabled });
  },

  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
  
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  
  setActiveView: (view) => set({ activeView: view })
}));
