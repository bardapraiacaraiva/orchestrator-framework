import { getAgents } from '@/lib/orchestrator';

export async function GET() {
  return Response.json(getAgents());
}
