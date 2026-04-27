import { getProjects } from '@/lib/orchestrator';

export async function GET() {
  return Response.json(getProjects());
}
