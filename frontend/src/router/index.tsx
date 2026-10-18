import { Navigate, createBrowserRouter } from 'react-router-dom';
import AppLayout from '../layouts/AppLayout';
import AuthLayout from '../layouts/AuthLayout';
import OAuthCallbackPage from '../pages/OAuthCallbackPage';
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
        lazy: async () => {
          const { default: LoginPage } = await import('../pages/LoginPage');
          return { Component: LoginPage };
        },
      },
    ],
  },
  {
    path: '/forgot-password',
    element: (
      <PublicRoute>
        <AuthLayout />
      </PublicRoute>
    ),
    children: [
      {
        path: '',
        lazy: async () => {
          const { default: ForgotPasswordPage } = await import('../pages/ForgotPasswordPage');
          return { Component: ForgotPasswordPage };
        },
      },
    ],
  },
  {
    path: '/reset-password',
    element: <AuthLayout />,
    children: [
      {
        path: '',
        lazy: async () => {
          const { default: ResetPasswordPage } = await import('../pages/ResetPasswordPage');
          return { Component: ResetPasswordPage };
        },
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
        lazy: async () => {
          const { default: ChatPage } = await import('../pages/ChatPage');
          return { Component: ChatPage };
        },
      },
      {
        path: 'c/:chatId',
        lazy: async () => {
          const { default: ChatPage } = await import('../pages/ChatPage');
          return { Component: ChatPage };
        },
      },
      {
        path: 'workspace',
        lazy: async () => {
          const { default: WorkspacePage } = await import('../pages/WorkspacePage');
          return { Component: WorkspacePage };
        },
      },
      {
        path: 'settings',
        lazy: async () => {
          const { default: SettingsPage } = await import('../pages/SettingsPage');
          return { Component: SettingsPage };
        },
      },
      {
        path: 'resume',
        lazy: async () => {
          const { default: ResumePage } = await import('../pages/ResumePage');
          return { Component: ResumePage };
        },
      },
      {
        path: 'analytics',
        lazy: async () => {
          const { default: AnalyticsPage } = await import('../pages/AnalyticsPage');
          return { Component: AnalyticsPage };
        },
      },
    ],
  },
  {
    path: '/share/:chatId',
    lazy: async () => {
      const { default: SharedChatPage } = await import('../pages/SharedChatPage');
      return { Component: SharedChatPage };
    },
  },
  {
    path: '*',
    element: <Navigate to="/" replace />,
  },
]);
