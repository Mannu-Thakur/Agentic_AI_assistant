import { create } from 'zustand';

interface User {
  id: string;
  email: string;
  full_name: string | null;
  avatar_url: string | null;
  is_active: boolean;
  created_at: string;
}

interface AuthState {
  token: string | null;
  user: User | null;
  isAuthenticated: boolean;
  login: (token: string, user: User, rememberMe?: boolean) => void;
  logout: () => void;
  updateUser: (user: User) => void;
}

const getStorageItem = (key: string): string | null => {
  return localStorage.getItem(key) || sessionStorage.getItem(key);
};

export const useAuthStore = create<AuthState>((set) => ({
  token: getStorageItem('access_token'),
  user: getStorageItem('user_info') ? JSON.parse(getStorageItem('user_info')!) : null,
  isAuthenticated: !!getStorageItem('access_token'),
  
  login: (token, user, rememberMe = true) => {
    const storage = rememberMe ? localStorage : sessionStorage;
    storage.setItem('access_token', token);
    storage.setItem('user_info', JSON.stringify(user));
    
    // Clear other storage type
    const otherStorage = rememberMe ? sessionStorage : localStorage;
    otherStorage.removeItem('access_token');
    otherStorage.removeItem('user_info');
    
    set({ token, user, isAuthenticated: true });
  },
  
  logout: () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('user_info');
    sessionStorage.removeItem('access_token');
    sessionStorage.removeItem('user_info');
    set({ token: null, user: null, isAuthenticated: false });
  },

  updateUser: (user) => {
    if (localStorage.getItem('access_token')) {
      localStorage.setItem('user_info', JSON.stringify(user));
    } else {
      sessionStorage.setItem('user_info', JSON.stringify(user));
    }
    set({ user });
  }
}));
