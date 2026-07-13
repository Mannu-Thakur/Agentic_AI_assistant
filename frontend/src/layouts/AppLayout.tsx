import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { useState } from 'react';
import { useUIStore } from '../store/uiStore';
import { useAuthStore } from '../store/authStore';
import Logo from '../components/ui/Logo';
import {
  MessageSquare,
  Brain,
  FolderClosed,
  Settings,
  LogOut,
  ChevronLeft,
  ChevronRight,
  Terminal,
} from 'lucide-react';

export default function AppLayout() {
  const { sidebarOpen, toggleSidebar, setActiveView, activeView, developerMode, toggleDeveloperMode } = useUIStore();
  const { user, logout } = useAuthStore();
  const navigate = useNavigate();
  const location = useLocation();

  const [showUserMenu, setShowUserMenu] = useState(false);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const navItems = [
    { id: 'chat',      label: 'Chat',            icon: MessageSquare, path: '/' },
    { id: 'memories',  label: 'Semantic Memory',  icon: Brain,        path: '/workspace' },
    { id: 'documents', label: 'Documents',        icon: FolderClosed, path: '/workspace' },
    { id: 'settings',  label: 'Settings',         icon: Settings,     path: '/settings' },
  ];

  const isItemActive = (id: string) => {
    if (id === 'chat')     return location.pathname === '/';
    if (id === 'settings') return location.pathname === '/settings';
    // On /workspace, use activeView to pick exactly one
    if (id === 'memories')  return location.pathname.startsWith('/workspace') && activeView === 'memories';
    if (id === 'documents') return location.pathname.startsWith('/workspace') && activeView === 'documents';
    return false;
  };

  const userInitial = user?.full_name
    ? user.full_name.charAt(0).toUpperCase()
    : user?.email.charAt(0).toUpperCase() ?? 'U';

  return (
    <div className="h-screen w-screen flex overflow-hidden bg-background text-foreground">

      {/* ─── Left Sidebar ─── */}
      <aside
        className="relative flex flex-col border-r border-border bg-surface sidebar-transition flex-shrink-0 z-30"
        style={{ width: sidebarOpen ? 'var(--sidebar-width)' : 'var(--sidebar-collapsed)' }}
        aria-label="Main navigation"
      >
        {/* Header */}
        <div
          className="flex items-center border-b border-border flex-shrink-0 overflow-hidden bg-transparent light-dark"
          style={{ height: 'var(--header-height)', padding: sidebarOpen ? '0 14px' : '0 12px' }}
        >
          <Logo collapsed={!sidebarOpen} size={26} />
        </div>

        {/* Nav */}
        <nav className="flex-1 overflow-y-auto overflow-x-hidden py-3 px-2 space-y-0.5" aria-label="Primary navigation">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = isItemActive(item.id);

            return (
              <button
                key={item.id}
              onClick={() => {
                  if (item.id === 'memories')  { setActiveView('memories');  }
                  if (item.id === 'documents') { setActiveView('documents'); }
                  if (item.id === 'chat')      { setActiveView('chat');      }
                  navigate(item.path);
                }}
                data-tooltip={!sidebarOpen ? item.label : undefined}
                aria-label={item.label}
                className={`w-full flex items-center gap-3 rounded-lg text-sm font-medium transition-all duration-150
                  ${sidebarOpen ? 'px-3 py-2' : 'px-0 py-2 justify-center'}
                  ${active
                    ? 'bg-accent/10 text-accent active-glow'
                    : 'text-foreground-2 hover:text-foreground hover:bg-surface-2'
                  }`}
              >
                <Icon className="w-4 h-4 flex-shrink-0" />
                {sidebarOpen && (
                  <span className="truncate leading-none">{item.label}</span>
                )}
              </button>
            );
          })}

          {/* Developer Mode toggle */}
          <button
            onClick={toggleDeveloperMode}
            data-tooltip={!sidebarOpen ? 'Dev Mode' : undefined}
            aria-label="Toggle Developer Mode"
            className={`w-full flex items-center gap-3 rounded-lg text-sm font-medium transition-all duration-150
              ${sidebarOpen ? 'px-3 py-2' : 'px-0 py-2 justify-center'}
              ${developerMode
                ? 'bg-surface-3 text-foreground border border-border-2'
                : 'text-foreground-2 hover:text-foreground hover:bg-surface-2 border border-transparent'
              }`}
          >
            <Terminal className="w-4 h-4 flex-shrink-0" />
            {sidebarOpen && <span className="truncate leading-none">Dev HUD</span>}
            {sidebarOpen && developerMode && (
              <span className="ml-auto text-[9px] px-1.5 py-0.5 rounded-full bg-accent/20 text-foreground font-semibold">ON</span>
            )}
          </button>
        </nav>

        {/* Footer – user profile */}
        <div className="border-t border-border p-2 space-y-1 flex-shrink-0">
          {/* User row */}
          <div className="relative">
            <button
              onClick={() => setShowUserMenu(!showUserMenu)}
              data-tooltip={!sidebarOpen ? (user?.full_name || user?.email || 'Account') : undefined}
              aria-label="User menu"
              className={`w-full flex items-center gap-2.5 rounded-lg transition-all hover:bg-surface-2
                ${sidebarOpen ? 'px-2.5 py-2' : 'px-0 py-2 justify-center'}`}
            >
              <div className="w-7 h-7 rounded-full bg-accent/20 border border-accent/30 flex items-center justify-center text-accent font-bold text-xs flex-shrink-0">
                {userInitial}
              </div>
              {sidebarOpen && (
                <div className="min-w-0 flex-1 text-left">
                  <p className="text-xs font-semibold truncate leading-tight">{user?.full_name || 'User'}</p>
                  <p className="text-[10px] text-foreground-3 truncate">{user?.email}</p>
                </div>
              )}
            </button>

            {/* Dropdown */}
            {showUserMenu && (
              <>
                <div className="fixed inset-0 z-40" onClick={() => setShowUserMenu(false)} />
                <div className={`absolute ${sidebarOpen ? 'left-0' : 'left-full ml-2'} bottom-full mb-1 w-44 glass-heavy rounded-xl shadow-2xl p-1 z-50 animate-scale-in`}>
                  <button
                    onClick={() => { navigate('/settings'); setShowUserMenu(false); }}
                    className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-medium text-foreground-2 hover:text-foreground hover:bg-surface-2 transition-all"
                  >
                    <Settings className="w-3.5 h-3.5" />
                    Settings
                  </button>
                  <button
                    onClick={handleLogout}
                    className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-medium text-red-400 hover:text-red-300 hover:bg-red-500/10 transition-all"
                  >
                    <LogOut className="w-3.5 h-3.5" />
                    Logout
                  </button>
                </div>
              </>
            )}
          </div>
        </div>

        {/* Collapse toggle button */}
        <button
          onClick={toggleSidebar}
          aria-label={sidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'}
          className="absolute -right-3 top-[calc(var(--header-height)_+_16px)] z-50
                     w-6 h-6 rounded-full border border-border bg-surface-2 shadow-md
                     flex items-center justify-center text-foreground-2
                     hover:text-foreground hover:bg-surface-3 transition-all"
        >
          {sidebarOpen ? <ChevronLeft className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        </button>
      </aside>

      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/60 z-20 md:hidden"
          onClick={toggleSidebar}
        />
      )}

      {/* ─── Main content ─── */}
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <Outlet />
      </main>
    </div>
  );
}
