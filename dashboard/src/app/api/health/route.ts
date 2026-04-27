import { getHealth } from '@/lib/orchestrator';

export async function GET() {
  return Response.json(getHealth());
}
