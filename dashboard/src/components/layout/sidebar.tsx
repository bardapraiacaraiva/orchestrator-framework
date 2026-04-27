'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { logout } from '@/lib/auth';
import {
  LayoutDashboard,
  CheckSquare,
  Wallet,
  Star,
  Puzzle,
  FileText,
  Settings,
  Bell,
  Users,
  FolderKanban,
  BarChart3,
  Network,
  LogOut,
} from 'lucide-react';

const navItems = [
  { label: 'Command Center', href: '/command-center', icon: LayoutDashboard },
  { label: 'Tasks', href: '/tasks', icon: CheckSquare },
  { label: 'Budget', href: '/budget', icon: Wallet },
  { label: 'Quality', href: '/quality', icon: Star },
  { label: 'Agents', href: '/agents', icon: Users },
  { label: 'Visualizer', href: '/visualizer', icon: Network },
  { label: 'Projects', href: '/projects', icon: FolderKanban },
  { label: 'Notifications', href: '/notifications', icon: Bell },
  { label: 'Skills', href: '/skills', icon: Puzzle },
  { label: 'Reports', href: '/reports', icon: BarChart3 },
  { label: 'Logs', href: '/logs', icon: FileText },
  { label: 'Settings', href: '/settings', icon: Settings },
];

export function Sidebar({ healthStatus, userName }: { healthStatus: string; userName?: string }) {
  const pathname = usePathname();

  return (
    <aside className="flex w-60 flex-col justify-between bg-[#111827] px-3 py-6">
      {/* Logo */}
      <div>
        <Link href="/command-center" className="mb-8 flex items-center gap-2 px-3">
          <span className="text-xl font-bold tracking-tight text-white">
            D<span className="text-[#00e5ff]">.</span>A
            <span className="text-[#00e5ff]">.</span>R
            <span className="text-[#00e5ff]">.</span>I
            <span className="text-[#00e5ff]">.</span>O
          </span>
        </Link>

        {/* Navigation */}
        <nav className="mt-6 flex flex-col gap-1">
          {navItems.map(({ label, href, icon: Icon }) => {
            const isActive = pathname === href;
            return (
              <Link
                key={href}
                href={href}
                className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-[#00e5ff]/15 text-[#00e5ff]'
                    : 'text-gray-400 hover:bg-white/5 hover:text-white'
                }`}
              >
                <Icon className="h-4 w-4 shrink-0" />
                {label}
              </Link>
            );
          })}
        </nav>
      </div>

      {/* Footer: User + Health */}
      <div className="space-y-3">
        {userName && (
          <div className="flex items-center justify-between px-3">
            <div className="flex items-center gap-2">
              <div className="h-6 w-6 rounded-full bg-[#00e5ff]/20 flex items-center justify-center text-[10px] font-bold text-[#00e5ff]">
                {userName.charAt(0).toUpperCase()}
              </div>
              <span className="text-xs text-gray-400 truncate max-w-[120px]">{userName}</span>
            </div>
            <form action={logout}>
              <button type="submit" className="text-gray-500 hover:text-red-400 transition-colors" title="Sign out">
                <LogOut className="h-3.5 w-3.5" />
              </button>
            </form>
          </div>
        )}
        <div className="flex items-center gap-2 px-3 text-xs text-gray-500">
          <span
            className={`h-2 w-2 rounded-full ${
              healthStatus === 'healthy'
                ? 'bg-emerald-400'
                : healthStatus === 'degraded'
                  ? 'bg-amber-400'
                  : 'bg-red-400'
            }`}
          />
          System: {healthStatus === 'healthy' ? 'Healthy' : healthStatus === 'degraded' ? 'Degraded' : 'Unhealthy'}
        </div>
      </div>
    </aside>
  );
}
