import { Navigate, createBrowserRouter } from 'react-router-dom';
import AppLayout from '../layouts/AppLayout';
import AuthLayout from '../layouts/AuthLayout';
import LoginPage from '../pages/LoginPage';
import ChatPage from '../pages/ChatPage';
import WorkspacePage from '../pages/WorkspacePage';
import SettingsPage from '../pages/SettingsPage';
import OAuthCallbackPage from '../pages/OAuthCallbackPage';
import SharedChatPage from '../pages/SharedChatPage';
import { useAuthStore } from '../store/authStore';

// Protected Route Helper
const ProtectedRoute = ({ children }: { children: React.ReactNode }) => {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />;
};

// Public Only Route Helper (e.g. for login page)
const PublicRoute = ({ children }: { children: React.ReactNode }) => {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  return !isAuthenticated ? <>{children}</> : <Navigate to="/" replace />;
};

export const router = createBrowserRouter([
  {
    path: '/login',
    element: (
      <PublicRoute>
        <AuthLayout />
      </PublicRoute>
    ),
    children: [
      {
        path: '',
        element: <LoginPage />,
      },
    ],
  },
  {
    path: '/auth/google/callback',
    element: <OAuthCallbackPage provider="google" />,
  },
  {
    path: '/auth/github/callback',
    element: <OAuthCallbackPage provider="github" />,
  },
  {
    path: '/',
    element: (
      <ProtectedRoute>
        <AppLayout />
      </ProtectedRoute>
    ),
    children: [
      {
        path: '',
        element: <ChatPage />,
      },
      {
        path: 'c/:chatId',
        element: <ChatPage />,
      },
      {
        path: 'workspace',
        element: <WorkspacePage />,
      },
      {
        path: 'settings',
        element: <SettingsPage />,
      },
    ],
  },
  {
    path: '/share/:chatId',
    element: <SharedChatPage />,
  },
  {
    path: '*',
    element: <Navigate to="/" replace />,
  },
]);
