import { getSkills } from '@/lib/orchestrator';

export async function GET() {
  return Response.json(getSkills());
}
