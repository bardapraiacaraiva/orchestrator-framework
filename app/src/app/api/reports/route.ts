import { getTasks, getBudget, getQuality, getSkills, getAgents, getLogs } from '@/lib/orchestrator';

export async function GET() {
  return Response.json({
    tasks: getTasks(),
    budget: getBudget(),
    quality: getQuality(),
    skills: getSkills(),
    agents: getAgents(),
    logs: getLogs(7),
  });
}
