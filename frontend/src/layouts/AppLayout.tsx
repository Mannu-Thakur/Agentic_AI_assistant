import { Outlet } from 'react-router-dom';

export default function AppLayout() {
  return (
    <div className="h-screen w-screen flex flex-col overflow-hidden bg-background text-foreground">
      {/* ─── Main content fills remaining height ─── */}
      <main className="flex-1 min-h-0 flex overflow-hidden" role="main">
        <Outlet />
      </main>
    </div>
  );
}
