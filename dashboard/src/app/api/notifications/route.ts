import { getNotifications } from '@/lib/orchestrator';

export async function GET() {
  return Response.json(getNotifications());
}
