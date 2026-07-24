import { Outlet } from 'react-router-dom';

export default function AppLayout() {
  return (
    <div className="h-screen w-screen flex overflow-hidden bg-background text-foreground">
      {/* ─── Main content ─── */}
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden" role="main">
        <Outlet />
      </main>
    </div>
  );
}
