import { Outlet, Link, useNavigate, useLocation } from 'react-router-dom';
import { useUIStore } from '../store/uiStore';
import { useAuthStore } from '../store/authStore';
import { 
  MessageSquare, 
  Brain, 
  FolderClosed, 
  Settings, 
  LogOut, 
  Menu, 
  X,
  Cpu
} from 'lucide-react';

export default function AppLayout() {
  const { sidebarOpen, toggleSidebar, setActiveView } = useUIStore();
  const { user, logout } = useAuthStore();
  const navigate = useNavigate();
  const location = useLocation();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const navItems = [
    { id: 'chat', label: 'Chat Workspace', icon: MessageSquare, path: '/' },
    { id: 'memories', label: 'Semantic Memory', icon: Brain, path: '/workspace' },
    { id: 'documents', label: 'Document Files', icon: FolderClosed, path: '/workspace' },
  ];

  return (
    <div className="h-screen w-screen flex overflow-hidden bg-background text-foreground">
      
      {/* Sidebar Component */}
      <aside 
        className={`fixed inset-y-0 left-0 z-40 w-64 border-r border-border bg-card/50 backdrop-blur-xl flex flex-col justify-between transition-transform duration-300 md:translate-x-0 md:relative ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="flex flex-col flex-1 min-h-0">
          
          {/* Sidebar Header branding */}
          <div className="h-16 px-6 flex items-center justify-between border-b border-border">
            <div className="flex items-center space-x-3">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-violet-600 to-indigo-600 flex items-center justify-center">
                <Cpu className="w-4.5 h-4.5 text-white" />
              </div>
              <span className="font-semibold text-sm tracking-tight">Omni</span>
            </div>
            <button onClick={toggleSidebar} className="md:hidden text-muted-foreground hover:text-foreground">
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Navigation Links */}
          <nav className="flex-1 px-4 py-6 space-y-1.5 overflow-y-auto">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = (item.id === 'chat' && location.pathname === '/') || 
                               (item.id !== 'chat' && location.pathname.startsWith('/workspace'));
              
              const clickHandler = () => {
                if (item.id === 'memories') setActiveView('memories');
                if (item.id === 'documents') setActiveView('documents');
                navigate(item.path);
              };

              return (
                <button
                  key={item.id}
                  onClick={clickHandler}
                  className={`w-full flex items-center space-x-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all ${
                    isActive 
                      ? 'bg-primary text-primary-foreground shadow-lg shadow-primary/20' 
                      : 'text-muted-foreground hover:text-foreground hover:bg-secondary/50'
                  }`}
                >
                  <Icon className="w-4.5 h-4.5" />
                  <span>{item.label}</span>
                </button>
              );
            })}
          </nav>
        </div>

        {/* Sidebar Footer - User profile settings */}
        <div className="p-4 border-t border-border bg-card/80">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center space-x-3 min-w-0">
              <div className="w-9 h-9 rounded-full bg-gradient-to-tr from-violet-600 to-indigo-600 flex items-center justify-center font-bold text-white uppercase shadow-md shadow-violet-900/20">
                {user?.full_name ? user.full_name.charAt(0) : user?.email.charAt(0)}
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-xs font-semibold truncate">{user?.full_name || 'Active User'}</p>
                <p className="text-[10px] text-muted-foreground truncate">{user?.email}</p>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <Link
              to="/settings"
              className="flex items-center justify-center space-x-1.5 py-1.5 px-2 rounded-lg border border-border bg-secondary/50 hover:bg-muted text-xs font-medium transition-all"
            >
              <Settings className="w-3.5 h-3.5" />
              <span>Settings</span>
            </Link>
            <button
              onClick={handleLogout}
              className="flex items-center justify-center space-x-1.5 py-1.5 px-2 rounded-lg border border-red-500/20 bg-red-500/5 hover:bg-red-500/10 text-red-400 text-xs font-medium transition-all"
            >
              <LogOut className="w-3.5 h-3.5" />
              <span>Logout</span>
            </button>
          </div>
        </div>
      </aside>

      {/* Main Content Pane */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden relative">
        
        {/* Toggle navigation bar header for mobile screens */}
        <header className="h-16 border-b border-border flex items-center justify-between px-6 md:hidden glass sticky top-0 z-30">
          <button 
            onClick={toggleSidebar}
            className="p-2 rounded-lg border border-border bg-card text-foreground hover:bg-muted"
          >
            <Menu className="w-5 h-5" />
          </button>
          <div className="flex items-center space-x-2">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-tr from-violet-600 to-indigo-600 flex items-center justify-center">
              <Cpu className="w-4 h-4 text-white" />
            </div>
            <span className="font-semibold text-xs tracking-tight">Omni</span>
          </div>
          <div className="w-9" /> {/* Spacer */}
        </header>

        {/* Children content page injection */}
        <main className="flex-1 overflow-y-auto relative bg-background/95">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
