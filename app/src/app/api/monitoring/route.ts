import { getMonitoring } from '@/lib/orchestrator';

export async function GET() {
  return Response.json(getMonitoring());
}
