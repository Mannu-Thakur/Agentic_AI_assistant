import { create } from 'zustand';

export type ThemeType = 'dark' | 'light' | 'system';
type ViewMode = 'chat' | 'memories' | 'documents';

export type ContrastType = 'system' | 'default' | 'high';
export type AccentColorType = 'default' | 'emerald' | 'indigo' | 'amber' | 'rose' | 'violet';
export type FontSizeType = 'sm' | 'base' | 'lg';

interface UIState {
  theme: ThemeType;
  contrastMode: ContrastType;
  accentColor: AccentColorType;
  fontSize: FontSizeType;
  language: string;
  higherIntelligence: boolean;
  enableDictation: boolean;
  mfaEnabled: boolean;
  compactMode: boolean;
  developerMode: boolean;
  sidebarOpen: boolean;
  activeView: ViewMode;
  toggleTheme: () => void;
  setTheme: (theme: ThemeType) => void;
  setContrastMode: (contrast: ContrastType) => void;
  setAccentColor: (accent: AccentColorType) => void;
  setFontSize: (size: FontSizeType) => void;
  setLanguage: (lang: string) => void;
  setHigherIntelligence: (enabled: boolean) => void;
  setEnableDictation: (enabled: boolean) => void;
  setMfaEnabled: (enabled: boolean) => void;
  toggleCompactMode: () => void;
  setCompactMode: (enabled: boolean) => void;
  toggleDeveloperMode: () => void;
  setDeveloperMode: (enabled: boolean) => void;
  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  setActiveView: (view: ViewMode) => void;
}

// ── Accent & Contrast & Font Size helpers ──────────────────────────────────
function applyAccentColor(accent: AccentColorType) {
  const root = document.documentElement;
  if (accent === 'emerald') {
    root.style.setProperty('--accent', '160 84% 39%');
    root.style.setProperty('--accent-glow', 'rgba(16, 185, 129, 0.35)');
  } else if (accent === 'indigo') {
    root.style.setProperty('--accent', '239 84% 67%');
    root.style.setProperty('--accent-glow', 'rgba(99, 102, 241, 0.35)');
  } else if (accent === 'amber') {
    root.style.setProperty('--accent', '38 92% 50%');
    root.style.setProperty('--accent-glow', 'rgba(245, 158, 11, 0.35)');
  } else if (accent === 'rose') {
    root.style.setProperty('--accent', '343 87% 62%');
    root.style.setProperty('--accent-glow', 'rgba(244, 63, 94, 0.35)');
  } else if (accent === 'violet') {
    root.style.setProperty('--accent', '263 70% 60%');
    root.style.setProperty('--accent-glow', 'rgba(139, 92, 246, 0.35)');
  } else {
    // Default sleek neutral monochrome accent (ChatGPT theme)
    root.style.setProperty('--accent', '0 0% 90%');
    root.style.setProperty('--accent-glow', 'rgba(255, 255, 255, 0.2)');
  }
}

function applyFontSize(size: FontSizeType) {
  const root = document.documentElement;
  root.classList.remove('font-sm', 'font-lg');
  if (size === 'sm') root.classList.add('font-sm');
  if (size === 'lg') root.classList.add('font-lg');
}

function applyContrastMode(contrast: ContrastType) {
  const root = document.documentElement;
  if (contrast === 'high') {
    root.classList.add('high-contrast');
  } else {
    root.classList.remove('high-contrast');
  }
}

// ── Derive effective theme (dark/light) from saved preference ─────────────
function getEffectiveTheme(theme: ThemeType): 'dark' | 'light' {
  if (theme === 'system') {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  return theme;
}

function applyTheme(theme: ThemeType) {
  const root = document.documentElement;
  root.classList.remove('dark', 'light');
  const effective = getEffectiveTheme(theme);
  if (effective === 'light') {
    root.classList.add('light');
  } else {
    root.classList.add('dark');
  }
}

function applyCompactMode(enabled: boolean) {
  const root = document.documentElement;
  if (enabled) {
    root.classList.add('compact');
  } else {
    root.classList.remove('compact');
  }
}

// ── OS theme change listener ─────────────────────────────────────────────
let _osThemeCleanup: (() => void) | null = null;

function attachOsThemeListener() {
  if (_osThemeCleanup) _osThemeCleanup();
  const mq = window.matchMedia('(prefers-color-scheme: dark)');
  const handler = () => {
    const saved = (localStorage.getItem('theme') as ThemeType) || 'dark';
    if (saved === 'system') applyTheme('system');
  };
  mq.addEventListener('change', handler);
  _osThemeCleanup = () => mq.removeEventListener('change', handler);
}

// ── Initial load saved settings ──────────────────────────────────────────
const _savedTheme = (localStorage.getItem('theme') as ThemeType) || 'dark';
const _savedContrast = (localStorage.getItem('contrast_mode') as ContrastType) || 'default';
const _savedAccent = (localStorage.getItem('accent_color') as AccentColorType) || 'default';
const _savedFontSize = (localStorage.getItem('font_size') as FontSizeType) || 'base';
const _savedLanguage = localStorage.getItem('language') || 'Auto-detect';
const _savedIntelligence = localStorage.getItem('higher_intelligence') !== 'false';
const _savedDictation = localStorage.getItem('enable_dictation') !== 'false';
const _savedMfa = localStorage.getItem('mfa_enabled') === 'true';
const _savedCompact = localStorage.getItem('compact_mode') === 'true';

applyTheme(_savedTheme);
applyContrastMode(_savedContrast);
applyAccentColor(_savedAccent);
applyFontSize(_savedFontSize);
applyCompactMode(_savedCompact);
attachOsThemeListener();

export const useUIStore = create<UIState>((set) => ({
  theme: _savedTheme,
  contrastMode: _savedContrast,
  accentColor: _savedAccent,
  fontSize: _savedFontSize,
  language: _savedLanguage,
  higherIntelligence: _savedIntelligence,
  enableDictation: _savedDictation,
  mfaEnabled: _savedMfa,
  compactMode: _savedCompact,
  developerMode: localStorage.getItem('developer_mode') === 'true',
  sidebarOpen: localStorage.getItem('sidebar_open') !== 'false',
  activeView: 'chat',

  toggleTheme: () => set((state) => {
    const next: ThemeType = state.theme === 'dark' ? 'light' : 'dark';
    localStorage.setItem('theme', next);
    applyTheme(next);
    return { theme: next };
  }),

  setTheme: (theme) => {
    localStorage.setItem('theme', theme);
    applyTheme(theme);
    if (theme === 'system') {
      attachOsThemeListener();
    }
    set({ theme });
  },

  setContrastMode: (contrast) => {
    localStorage.setItem('contrast_mode', contrast);
    applyContrastMode(contrast);
    set({ contrastMode: contrast });
  },

  setAccentColor: (accent) => {
    localStorage.setItem('accent_color', accent);
    applyAccentColor(accent);
    set({ accentColor: accent });
  },

  setFontSize: (size) => {
    localStorage.setItem('font_size', size);
    applyFontSize(size);
    set({ fontSize: size });
  },

  setLanguage: (language) => {
    localStorage.setItem('language', language);
    set({ language });
  },

  setHigherIntelligence: (enabled) => {
    localStorage.setItem('higher_intelligence', String(enabled));
    set({ higherIntelligence: enabled });
  },

  setEnableDictation: (enabled) => {
    localStorage.setItem('enable_dictation', String(enabled));
    set({ enableDictation: enabled });
  },

  setMfaEnabled: (enabled) => {
    localStorage.setItem('mfa_enabled', String(enabled));
    set({ mfaEnabled: enabled });
  },

  toggleCompactMode: () => set((state) => {
    const next = !state.compactMode;
    localStorage.setItem('compact_mode', String(next));
    applyCompactMode(next);
    return { compactMode: next };
  }),

  setCompactMode: (enabled) => {
    localStorage.setItem('compact_mode', String(enabled));
    applyCompactMode(enabled);
    set({ compactMode: enabled });
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
