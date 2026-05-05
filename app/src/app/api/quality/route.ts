import { getQuality } from '@/lib/orchestrator';

export async function GET() {
  return Response.json(getQuality());
}
