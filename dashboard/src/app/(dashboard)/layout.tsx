import { getHealth } from '@/lib/orchestrator';
import { getSession } from '@/lib/session';
import { Sidebar } from '@/components/layout/sidebar';

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const health = getHealth();
  const session = await getSession();

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar healthStatus={health.overall} userName={session?.name} />
      <main className="flex-1 overflow-y-auto bg-[#0a0e1a] p-6">{children}</main>
    </div>
  );
}
