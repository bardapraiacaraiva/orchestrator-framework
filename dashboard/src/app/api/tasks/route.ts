import { getTasks } from '@/lib/orchestrator';

export async function GET() {
  return Response.json(getTasks());
}
