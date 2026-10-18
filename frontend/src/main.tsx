import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider } from 'react-router-dom';
import { router } from './router/index.tsx';
import { TooltipProvider } from './components/ui/Tooltip.tsx';
import './index.css';

class AppErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean; error?: Error }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }
  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: '2rem', textAlign: 'center', fontFamily: 'sans-serif' }}>
          <h2>Something went wrong</h2>
          <p style={{ color: '#666' }}>{this.state.error?.message}</p>
          <button onClick={() => window.location.reload()} style={{ padding: '8px 16px', cursor: 'pointer' }}>
            Reload Page
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

const subscribeToRouter = (onStoreChange: () => void) => router.subscribe(onStoreChange);
const getRouterInitialized = () => router.state.initialized;

function RouterStartupGate() {
  const isInitialized = React.useSyncExternalStore(
    subscribeToRouter,
    getRouterInitialized,
    getRouterInitialized,
  );

  if (!isInitialized) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background text-muted-foreground" role="status">
        Loading workspace…
      </div>
    );
  }

  return <RouterProvider router={router} />;
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <AppErrorBoundary>
          <RouterStartupGate />
        </AppErrorBoundary>
      </TooltipProvider>
    </QueryClientProvider>
  </React.StrictMode>
);

