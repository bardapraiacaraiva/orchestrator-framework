import { getDailyDigest } from '@/lib/orchestrator';

export async function GET() {
  return Response.json(getDailyDigest());
}
