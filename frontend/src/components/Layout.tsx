import { Outlet, Link, useLocation } from 'react-router-dom';
import { Shield, LayoutDashboard, PlusCircle, Settings, LogOut } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAuth } from '@/hooks/useAuth';

const NAV_ITEMS = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/tasks/new', icon: PlusCircle, label: 'New Task' },
];

export default function Layout() {
  const { pathname } = useLocation();
  const { logout } = useAuth();

  return (
    <div className="min-h-screen flex">
      <aside className="w-56 border-r border-border bg-card flex flex-col">
        <Link to="/" className="h-14 flex items-center gap-2 px-4 border-b border-border">
          <Shield className="w-5 h-5 text-primary" />
          <span className="font-semibold text-sm">SecureClawAgent</span>
        </Link>
        <nav className="flex-1 p-3 space-y-1">
          {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
            <Link
              key={to}
              to={to}
              className={cn(
                'flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors',
                pathname === to
                  ? 'bg-secondary text-secondary-foreground'
                  : 'text-muted-foreground hover:bg-secondary hover:text-secondary-foreground',
              )}
            >
              <Icon className="w-4 h-4" />
              {label}
            </Link>
          ))}
        </nav>
        <div className="p-3 border-t border-border space-y-1">
          <button
            onClick={logout}
            className="flex items-center gap-3 px-3 py-2 rounded-md text-sm text-muted-foreground hover:bg-secondary hover:text-secondary-foreground w-full"
          >
            <LogOut className="w-4 h-4" />
            Logout
          </button>
        </div>
      </aside>
      <main className="flex-1 p-6 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
