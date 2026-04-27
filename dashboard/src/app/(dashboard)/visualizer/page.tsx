import { getAgents, getTasks, getBudget, getQuality } from '@/lib/orchestrator';
import { MissionControl } from './mission-control';

export default function VisualizerPage() {
  const agents = getAgents();
  const tasks = getTasks();
  const budget = getBudget();
  const quality = getQuality();

  return (
    <MissionControl
      agents={agents}
      tasks={tasks}
      budget={budget}
      quality={quality}
    />
  );
}
