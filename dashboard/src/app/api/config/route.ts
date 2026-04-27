import { getConfig } from '@/lib/orchestrator';

export async function GET() {
  return Response.json(getConfig());
}
