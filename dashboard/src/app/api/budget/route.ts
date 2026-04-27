import { getBudget } from '@/lib/orchestrator';

export async function GET() {
  return Response.json(getBudget());
}
