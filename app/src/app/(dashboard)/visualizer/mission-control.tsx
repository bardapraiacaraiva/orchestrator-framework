'use client';

import { useEffect, useRef, useState, useCallback } from 'react';

type Props = {
  agents: any;
  tasks: any;
  budget: any;
  quality: any;
};

type MapNode = {
  id: string;
  x: number;
  y: number;
  type: 'ceo' | 'vp' | 'dir';
  name: string;
  label: string;
  status: 'active' | 'idle' | 'off';
  parent: string | null;
  workers?: number;
  title?: string;
  capabilities?: string[];
  heartbeat?: any;
  adapter?: string;
};

const feedEvents = [
  { type: 'system', msg: 'Heartbeat pulse initiated — scanning taskboard' },
  { type: 'dispatch', msg: 'CEO dispatched task → worker-brand' },
  { type: 'execute', msg: 'worker-brand executing (dario-brand)' },
  { type: 'complete', msg: 'Task completed — score: 92/100 ✓' },
  { type: 'quality', msg: 'Quality: success_pattern extracted for brand_positioning' },
  { type: 'budget', msg: 'Budget: +12,400 tokens (0.05% total)' },
  { type: 'system', msg: 'Dependencies resolved — 2 tasks unblocked' },
  { type: 'dispatch', msg: 'Dispatch: MNB-002 → worker-naming' },
  { type: 'dispatch', msg: 'Dispatch: MNB-003 → worker-seo-local' },
  { type: 'execute', msg: 'worker-naming executing (dario-naming)' },
  { type: 'execute', msg: 'worker-seo-local executing (seo-local)' },
  { type: 'complete', msg: 'worker-naming completed — score: 88/100 ✓' },
  { type: 'quality', msg: '5-dim rubric: Specificity:18 Action:17 Complete:18 Acc:18 Tone:17' },
  { type: 'complete', msg: 'worker-seo-local completed — score: 85/100 ✓' },
  { type: 'budget', msg: 'Budget: +18,200 tokens (0.09% total)' },
  { type: 'dispatch', msg: 'Dispatch: MNB-004 → worker-story-circle' },
  { type: 'complete', msg: 'worker-story-circle completed — score: 90/100 ✓' },
  { type: 'quality', msg: 'Quality avg updated: 88.3 across 5 tasks' },
  { type: 'system', msg: 'Heartbeat complete — next pulse in 30 min' },
  { type: 'system', msg: 'RAG health: OK — sources active, reranking enabled' },
  { type: 'system', msg: 'LUCAS monitoring: 0 stale tasks, 0 alerts pending' },
  { type: 'quality', msg: 'Skill metrics: dario-brand → Tier S (avg 92.0)' },
  { type: 'budget', msg: 'Model routing: Opus for critical, Sonnet for standard' },
  { type: 'system', msg: 'Agent memory synced: project files + entities updated' },
];

const feedColors: Record<string, string> = {
  system: 'text-gray-400',
  dispatch: 'text-cyan-400',
  execute: 'text-amber-400',
  complete: 'text-green-400',
  quality: 'text-purple-400',
  budget: 'text-amber-400',
};

const feedIcons: Record<string, string> = {
  system: '⚙',
  dispatch: '→',
  execute: '▶',
  complete: '✓',
  quality: '★',
  budget: '$',
};

export function MissionControl({ agents, tasks, budget, quality }: Props) {
  const mapRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const [feed, setFeed] = useState<{ time: string; type: string; msg: string }[]>([]);
  const [hoverNode, setHoverNode] = useState<MapNode | null>(null);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });
  const [nodes, setNodes] = useState<MapNode[]>([]);
  const [taskDots, setTaskDots] = useState<{ id: number; fromX: number; fromY: number; toX: number; toY: number; progress: number; color: string }[]>([]);
  const [activeNodes, setActiveNodes] = useState<Set<string>>(new Set(['ceo']));
  const [flashNodes, setFlashNodes] = useState<Set<string>>(new Set());
  const feedIdx = useRef(0);
  const dotId = useRef(0);

  // Build node layout
  useEffect(() => {
    if (!mapRef.current) return;
    const w = mapRef.current.clientWidth;
    const h = mapRef.current.clientHeight;
    const cx = w / 2;
    const cy = h / 2;
    const baseR = Math.min(w * 0.44, h * 0.44, 380);

    const nodeData: MapNode[] = [];

    // CEO center
    const ceoAgent = agents.agents.find((a: any) => a.type === 'orchestrator' && !a.reports_to);
    nodeData.push({
      id: 'ceo', x: cx, y: cy, type: 'ceo',
      name: ceoAgent?.name || 'D.A.R.I.O.',
      label: 'CEO',
      status: 'active',
      parent: null,
      title: ceoAgent?.title || 'Chief Executive Officer',
      capabilities: ceoAgent?.capabilities?.slice(0, 8) || [],
      heartbeat: ceoAgent?.heartbeat,
      adapter: ceoAgent?.adapter,
    });

    // VPs
    const orchestrators = agents.agents.filter((a: any) => a.type === 'orchestrator' && a.reports_to);
    const vpR = baseR * 0.42;
    orchestrators.forEach((vp: any, i: number) => {
      const angle = -Math.PI / 2 + (i * 2 * Math.PI / Math.max(orchestrators.length, 1));
      nodeData.push({
        id: vp.id, x: cx + vpR * Math.cos(angle), y: cy + vpR * Math.sin(angle),
        type: 'vp', name: vp.name || vp.id,
        label: (vp.name || vp.id).substring(0, 5),
        status: 'idle', parent: 'ceo',
        title: vp.title,
        capabilities: vp.capabilities?.slice(0, 6) || [],
        heartbeat: vp.heartbeat,
        adapter: vp.adapter,
      });
    });

    // Directors
    const directors = agents.agents.filter((a: any) => a.type !== 'orchestrator' && a.type !== 'shared');
    const dirR = baseR * 0.92;
    directors.forEach((d: any, i: number) => {
      const angle = -Math.PI / 2 + (i * 2 * Math.PI / Math.max(directors.length, 1));
      const h = agents.hierarchy as Record<string, any[]>;
      const workerCount = h[d.id]?.length || 0;
      nodeData.push({
        id: d.id, x: cx + dirR * Math.cos(angle), y: cy + dirR * Math.sin(angle),
        type: 'dir', name: d.name || d.id,
        label: (d.name || d.id).substring(0, 3).toUpperCase(),
        status: workerCount > 3 ? 'active' : workerCount > 0 ? 'idle' : 'off',
        parent: d.reports_to || 'ceo',
        workers: workerCount,
        title: d.title,
        capabilities: d.capabilities?.slice(0, 4) || [],
      });
    });

    setNodes(nodeData);
  }, [agents]);

  // Draw SVG connections with animated dashes
  useEffect(() => {
    if (!svgRef.current || nodes.length === 0) return;
    const svg = svgRef.current;
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    const ns = 'http://www.w3.org/2000/svg';

    // Add defs for gradient and animation
    const defs = document.createElementNS(ns, 'defs');

    // Glow filter
    const filter = document.createElementNS(ns, 'filter');
    filter.setAttribute('id', 'glow');
    const blur = document.createElementNS(ns, 'feGaussianBlur');
    blur.setAttribute('stdDeviation', '2');
    blur.setAttribute('result', 'coloredBlur');
    filter.appendChild(blur);
    const merge = document.createElementNS(ns, 'feMerge');
    const mn1 = document.createElementNS(ns, 'feMergeNode');
    mn1.setAttribute('in', 'coloredBlur');
    merge.appendChild(mn1);
    const mn2 = document.createElementNS(ns, 'feMergeNode');
    mn2.setAttribute('in', 'SourceGraphic');
    merge.appendChild(mn2);
    filter.appendChild(merge);
    defs.appendChild(filter);
    svg.appendChild(defs);

    for (const n of nodes) {
      if (!n.parent) continue;
      const parent = nodes.find(p => p.id === n.parent);
      if (!parent) continue;

      const isHighlighted = selectedNode === n.id || selectedNode === n.parent;
      const isVpLine = n.type === 'vp';

      const line = document.createElementNS(ns, 'line');
      line.setAttribute('x1', String(parent.x));
      line.setAttribute('y1', String(parent.y));
      line.setAttribute('x2', String(n.x));
      line.setAttribute('y2', String(n.y));
      line.setAttribute('stroke', isHighlighted ? '#00e5ff' : isVpLine ? '#b388ff' : '#2a3a5a');
      line.setAttribute('stroke-width', isHighlighted ? '2' : isVpLine ? '1.5' : '0.8');
      line.setAttribute('stroke-dasharray', '6 4');
      line.setAttribute('opacity', isHighlighted ? '0.9' : isVpLine ? '0.5' : '0.3');

      if (isHighlighted || isVpLine) {
        line.setAttribute('filter', 'url(#glow)');
        // Animate dash flow
        const animate = document.createElementNS(ns, 'animate');
        animate.setAttribute('attributeName', 'stroke-dashoffset');
        animate.setAttribute('from', '0');
        animate.setAttribute('to', '-20');
        animate.setAttribute('dur', '1.5s');
        animate.setAttribute('repeatCount', 'indefinite');
        line.appendChild(animate);
      }

      svg.appendChild(line);
    }
  }, [nodes, selectedNode]);

  // Orchestration simulation — activates nodes, sends task dots, feeds events
  useEffect(() => {
    if (nodes.length <= 1) return;

    const ceo = nodes.find(n => n.id === 'ceo');
    const vps = nodes.filter(n => n.type === 'vp');
    const dirs = nodes.filter(n => n.type === 'dir');
    if (!ceo) return;

    // Simulation cycle: dispatch → execute → complete
    const interval = setInterval(() => {
      const event = feedEvents[feedIdx.current % feedEvents.length];
      const now = new Date();
      const time = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}`;
      setFeed(prev => [{ time, ...event }, ...prev].slice(0, 40));

      // Pick random target node for orchestration
      const allTargets = [...vps, ...dirs.filter(d => d.workers && d.workers > 0)];
      const target = allTargets[Math.floor(Math.random() * allTargets.length)];

      if (event.type === 'dispatch' && target) {
        // CEO sends task → flash target, activate it, send cyan dot
        setActiveNodes(prev => new Set([...prev, target.id]));
        setFlashNodes(prev => new Set([...prev, target.id]));
        setTimeout(() => setFlashNodes(prev => { const n = new Set(prev); n.delete(target.id); return n; }), 800);

        // Send dot from CEO to target (via VP if target is a dir)
        const vp = vps.find(v => nodes.some(d => d.parent === v.id && d.id === target.id));
        if (vp && target.type === 'dir') {
          // Two-hop: CEO → VP → Dir
          setTaskDots(prev => [...prev,
            { id: dotId.current++, fromX: ceo.x, fromY: ceo.y, toX: vp.x, toY: vp.y, progress: 0, color: '#00e5ff' },
          ]);
          setTimeout(() => {
            setTaskDots(prev => [...prev,
              { id: dotId.current++, fromX: vp.x, fromY: vp.y, toX: target.x, toY: target.y, progress: 0, color: '#00e5ff' },
            ]);
            setFlashNodes(prev => new Set([...prev, vp.id]));
            setTimeout(() => setFlashNodes(prev => { const n = new Set(prev); n.delete(vp.id); return n; }), 600);
          }, 600);
        } else {
          setTaskDots(prev => [...prev,
            { id: dotId.current++, fromX: ceo.x, fromY: ceo.y, toX: target.x, toY: target.y, progress: 0, color: '#00e5ff' },
          ]);
        }
      } else if (event.type === 'complete' && target) {
        // Target sends result back to CEO — green dot
        setTaskDots(prev => [...prev,
          { id: dotId.current++, fromX: target.x, fromY: target.y, toX: ceo.x, toY: ceo.y, progress: 0, color: '#00e676' },
        ]);
        setFlashNodes(prev => new Set([...prev, 'ceo']));
        setTimeout(() => {
          setFlashNodes(prev => { const n = new Set(prev); n.delete('ceo'); return n; });
          setActiveNodes(prev => { const n = new Set(prev); n.delete(target.id); return n; });
        }, 1000);
      } else if (event.type === 'execute' && target) {
        // Activate the node while executing
        setActiveNodes(prev => new Set([...prev, target.id]));
        setFlashNodes(prev => new Set([...prev, target.id]));
        setTimeout(() => setFlashNodes(prev => { const n = new Set(prev); n.delete(target.id); return n; }), 500);
      } else if (event.type === 'quality') {
        // Quality check — purple dot from target to CEO
        if (target) {
          setTaskDots(prev => [...prev,
            { id: dotId.current++, fromX: target.x, fromY: target.y, toX: ceo.x, toY: ceo.y, progress: 0, color: '#b388ff' },
          ]);
        }
      }

      feedIdx.current++;
    }, 2200);

    // Periodic random activation/deactivation to make it feel alive
    const lifeInterval = setInterval(() => {
      const randomDir = dirs[Math.floor(Math.random() * dirs.length)];
      if (randomDir) {
        setActiveNodes(prev => {
          const n = new Set(prev);
          if (n.has(randomDir.id)) n.delete(randomDir.id);
          else n.add(randomDir.id);
          return n;
        });
      }
    }, 3500);

    return () => { clearInterval(interval); clearInterval(lifeInterval); };
  }, [nodes]);

  // Animate task dots
  useEffect(() => {
    if (taskDots.length === 0) return;
    const anim = setInterval(() => {
      setTaskDots(prev =>
        prev
          .map(d => ({ ...d, progress: d.progress + 0.04 }))
          .filter(d => d.progress <= 1)
      );
    }, 30);
    return () => clearInterval(anim);
  }, [taskDots.length > 0]);

  const handleNodeClick = useCallback((id: string) => {
    setSelectedNode(prev => prev === id ? null : id);
  }, []);

  return (
    <div className="flex flex-col h-[calc(100vh-48px)] -m-6 relative">
      {/* Scanline effect */}
      <div className="fixed top-0 left-0 w-full h-[2px] bg-gradient-to-r from-transparent via-cyan-400/15 to-transparent z-50 pointer-events-none animate-[scanline_8s_linear_infinite]" />

      {/* Header bar */}
      <div className="flex items-center justify-between px-5 py-2.5 border-b border-[#2a3a5a] bg-gradient-to-b from-[#111827]/95 to-[#0a0e1a]/98 backdrop-blur-sm shrink-0 z-10">
        <div className="text-lg font-extrabold tracking-tight">
          <span className="text-white">DARIO</span>{' '}
          <span className="text-cyan-400 drop-shadow-[0_0_12px_rgba(0,229,255,0.6)]">Orchestrator</span>
          <span className="text-gray-600 text-sm ml-2 font-normal">— Agent Command Center</span>
        </div>
        <div className="flex gap-3 items-center text-xs">
          <Badge color="cyan" pulse>Pulse: active</Badge>
          <Badge color="purple">Agents: {agents.total}</Badge>
          <Badge color="amber">Tasks: {tasks.total}</Badge>
          <Badge color="green">Budget: {budget.percentage}%</Badge>
        </div>
      </div>

      {/* 3-panel layout */}
      <div className="flex-1 grid grid-cols-[200px_1fr_340px] min-h-0">
        {/* LEFT: Agent Tree */}
        <div className="border-r border-[#2a3a5a] overflow-y-auto p-3 bg-[#111827]/40 text-xs scrollbar-thin">
          <div className="text-[10px] uppercase tracking-[0.15em] text-gray-600 font-bold mb-3">Agent Hierarchy</div>
          <TreeNode
            name={agents.agents.find((a: any) => !a.reports_to)?.name || 'D.A.R.I.O.'}
            type="ceo"
            status="active"
            selected={selectedNode}
            onSelect={handleNodeClick}
            id="ceo"
            children={[
              ...agents.agents.filter((a: any) => a.type === 'orchestrator' && a.reports_to).map((vp: any) => ({
                id: vp.id,
                name: vp.name || vp.id,
                type: 'vp' as const,
                status: 'idle' as const,
                children: agents.agents
                  .filter((d: any) => d.reports_to === vp.id && d.type !== 'orchestrator')
                  .map((d: any) => {
                    const h = agents.hierarchy as Record<string, any[]>;
                    return { id: d.id, name: d.name || d.id, type: 'dir' as const, status: 'idle' as const, workers: h[d.id]?.length || 0 };
                  }),
              })),
              ...agents.agents
                .filter((a: any) => a.reports_to === (agents.agents.find((x: any) => !x.reports_to)?.id || 'dario-ceo') && a.type !== 'orchestrator' && a.type !== 'shared')
                .map((d: any) => {
                  const h = agents.hierarchy as Record<string, any[]>;
                  return { id: d.id, name: d.name || d.id, type: 'dir' as const, status: 'idle' as const, workers: h[d.id]?.length || 0 };
                }),
            ]}
          />
        </div>

        {/* CENTER: Orbital Map */}
        <div
          ref={mapRef}
          className="relative overflow-hidden cursor-crosshair"
          style={{
            background: `
              radial-gradient(ellipse at center, rgba(0,229,255,0.04) 0%, rgba(0,229,255,0.01) 35%, transparent 70%),
              radial-gradient(circle at center,
                transparent 18%, rgba(42,58,90,0.14) 19%, transparent 20%,
                transparent 36%, rgba(42,58,90,0.10) 37%, transparent 38%,
                transparent 54%, rgba(42,58,90,0.07) 55%, transparent 56%,
                transparent 72%, rgba(42,58,90,0.05) 73%, transparent 74%,
                transparent 90%, rgba(42,58,90,0.03) 91%, transparent 92%
              )
            `,
          }}
          onClick={() => setSelectedNode(null)}
        >
          <svg ref={svgRef} className="absolute inset-0 w-full h-full pointer-events-none" />

          {/* Animated task dots traveling along connections */}
          {taskDots.map(d => {
            const x = d.fromX + (d.toX - d.fromX) * d.progress;
            const y = d.fromY + (d.toY - d.fromY) * d.progress;
            const opacity = d.progress < 0.1 ? d.progress * 10 : d.progress > 0.9 ? (1 - d.progress) * 10 : 1;
            return (
              <div
                key={d.id}
                className="absolute w-[6px] h-[6px] rounded-full pointer-events-none z-[5]"
                style={{
                  left: x - 3, top: y - 3,
                  background: d.color,
                  boxShadow: `0 0 10px ${d.color}, 0 0 20px ${d.color}40`,
                  opacity,
                }}
              />
            );
          })}

          {/* Heartbeat waves */}
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 pointer-events-none">
            <div className="absolute -inset-0 rounded-full border border-cyan-400/10 animate-[hbWave_4s_ease-out_infinite]" />
            <div className="absolute -inset-0 rounded-full border border-cyan-400/10 animate-[hbWave_4s_ease-out_infinite_2s]" />
          </div>

          {/* Nodes */}
          {nodes.map(n => (
            <OrbitalNode
              key={n.id}
              node={n}
              isSelected={selectedNode === n.id}
              isActive={activeNodes.has(n.id)}
              isFlashing={flashNodes.has(n.id)}
              onHover={(node, e) => { setHoverNode(node); setTooltipPos({ x: e.clientX, y: e.clientY }); }}
              onHoverEnd={() => setHoverNode(null)}
              onClick={handleNodeClick}
            />
          ))}

          {/* Tooltip */}
          {hoverNode && (
            <div
              className="fixed z-50 bg-[#111827]/95 border border-[#2a3a5a] rounded-xl px-5 py-4 shadow-2xl pointer-events-none max-w-[260px] backdrop-blur-sm"
              style={{ left: tooltipPos.x + 16, top: tooltipPos.y - 16 }}
            >
              <div className="text-sm font-bold text-cyan-400 mb-1">{hoverNode.name}</div>
              <div className="text-xs text-gray-400 mb-2">{hoverNode.title || hoverNode.type.toUpperCase()}</div>

              <div className="space-y-1.5 text-[11px]">
                <div className="flex justify-between">
                  <span className="text-gray-500">Status</span>
                  <span className={hoverNode.status === 'active' ? 'text-green-400 font-semibold' : 'text-gray-500'}>
                    {hoverNode.status === 'active' ? '● ACTIVE' : hoverNode.status === 'idle' ? '○ IDLE' : '○ OFFLINE'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Type</span>
                  <span className="text-gray-300">{hoverNode.type.toUpperCase()}</span>
                </div>
                {hoverNode.workers != null && hoverNode.workers > 0 && (
                  <div className="flex justify-between">
                    <span className="text-gray-500">Workers</span>
                    <span className="text-amber-400 font-semibold">{hoverNode.workers}</span>
                  </div>
                )}
                {hoverNode.adapter && (
                  <div className="flex justify-between">
                    <span className="text-gray-500">Adapter</span>
                    <span className="text-purple-400 text-[10px]">{hoverNode.adapter}</span>
                  </div>
                )}
                {hoverNode.heartbeat && (
                  <div className="flex justify-between">
                    <span className="text-gray-500">Heartbeat</span>
                    <span className="text-cyan-400">every {hoverNode.heartbeat.interval_minutes}min</span>
                  </div>
                )}
              </div>

              {hoverNode.capabilities && hoverNode.capabilities.length > 0 && (
                <div className="mt-2.5 pt-2.5 border-t border-[#2a3a5a]">
                  <div className="text-[9px] text-gray-600 uppercase tracking-wider mb-1.5">Capabilities</div>
                  <div className="flex flex-wrap gap-1">
                    {hoverNode.capabilities.map((c: string) => (
                      <span key={c} className="px-1.5 py-0.5 bg-cyan-400/10 border border-cyan-400/15 rounded text-[9px] text-cyan-400/70">
                        {c.replace(/_/g, ' ')}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* RIGHT: Activity Feed */}
        <div className="border-l border-[#2a3a5a] flex flex-col bg-[#111827]/40 overflow-hidden">
          <div className="px-4 py-3 border-b border-[#2a3a5a] shrink-0 flex items-center justify-between">
            <div className="text-[10px] uppercase tracking-[0.15em] text-gray-600 font-bold">Live Activity Feed</div>
            <div className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
              <span className="text-[9px] text-gray-500">streaming</span>
            </div>
          </div>
          <div className="flex-1 overflow-y-auto px-3 py-2 scrollbar-thin">
            {feed.map((f, i) => (
              <div
                key={`${f.time}-${i}`}
                className={`flex gap-2 py-1.5 px-2 rounded text-[11px] hover:bg-white/[.03] transition-all ${i === 0 ? 'animate-[slideIn_0.3s_ease-out]' : ''}`}
              >
                <span className="text-gray-700 font-mono text-[9px] shrink-0 pt-0.5 w-[52px]">{f.time}</span>
                <span className={`shrink-0 w-3 text-center ${feedColors[f.type]}`}>{feedIcons[f.type]}</span>
                <span className={`${feedColors[f.type]} leading-relaxed`}>{f.msg}</span>
              </div>
            ))}
            {feed.length === 0 && (
              <div className="text-gray-700 text-xs text-center py-12">
                <div className="text-2xl mb-2">⚙</div>
                Waiting for orchestrator events...
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Footer: Pipeline */}
      <div className="flex items-center justify-center gap-1.5 px-4 py-2 border-t border-[#2a3a5a] bg-[#111827]/70 shrink-0 text-xs backdrop-blur-sm">
        <PipeStage label="backlog" count={tasks.byStatus.backlog} color="gray" />
        <Arrow />
        <PipeStage label="todo" count={tasks.byStatus.todo} color="cyan" />
        <Arrow />
        <PipeStage label="in_progress" count={tasks.byStatus.in_progress} color="amber" />
        <Arrow />
        <PipeStage label="in_review" count={tasks.byStatus.in_review} color="purple" />
        <Arrow />
        <PipeStage label="done" count={tasks.byStatus.done} color="green" />
        <div className="w-px h-5 bg-[#2a3a5a] mx-3" />
        <span className="text-gray-500">Quality: <b className="text-green-400">{quality.global_avg.toFixed(1)}</b></span>
        <div className="w-px h-5 bg-[#2a3a5a] mx-1" />
        <span className="text-gray-500">Budget: <b className={budget.percentage > 80 ? 'text-amber-400' : 'text-green-400'}>{budget.percentage}%</b></span>
        <div className="w-px h-5 bg-[#2a3a5a] mx-1" />
        <span className="text-gray-500">Agents: <b className="text-purple-400">{agents.total}</b></span>
      </div>

      {/* CSS Animations */}
      <style jsx global>{`
        @keyframes scanline {
          0% { transform: translateY(-2px); }
          100% { transform: translateY(100vh); }
        }
        @keyframes hbWave {
          0% { width: 0; height: 0; opacity: 0.4; border-width: 2px; }
          100% { width: 600px; height: 600px; opacity: 0; border-width: 0.5px; margin: -300px; }
        }
        @keyframes slideIn {
          from { opacity: 0; transform: translateY(-8px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes breathe {
          0%, 100% { box-shadow: 0 0 20px rgba(0,229,255,0.2), inset 0 0 15px rgba(0,229,255,0.05); }
          50% { box-shadow: 0 0 40px rgba(0,229,255,0.4), inset 0 0 25px rgba(0,229,255,0.1); }
        }
        @keyframes dirPulse {
          0%, 100% { box-shadow: 0 0 6px rgba(0,230,118,0.15); }
          50% { box-shadow: 0 0 14px rgba(0,230,118,0.35); }
        }
        @keyframes nodeFlash {
          0% { transform: scale(1); box-shadow: 0 0 0 rgba(0,230,118,0); }
          30% { transform: scale(1.3); box-shadow: 0 0 30px rgba(0,230,118,0.6), 0 0 60px rgba(0,230,118,0.2); }
          100% { transform: scale(1); box-shadow: 0 0 12px rgba(0,230,118,0.3); }
        }
        .scrollbar-thin::-webkit-scrollbar { width: 4px; }
        .scrollbar-thin::-webkit-scrollbar-thumb { background: #2a3a5a; border-radius: 2px; }
        .scrollbar-thin::-webkit-scrollbar-track { background: transparent; }
      `}</style>
    </div>
  );
}

// === SUB-COMPONENTS ===

function OrbitalNode({ node, isSelected, isActive, isFlashing, onHover, onHoverEnd, onClick }: {
  node: MapNode;
  isSelected: boolean;
  isActive: boolean;
  isFlashing: boolean;
  onHover: (n: MapNode, e: React.MouseEvent) => void;
  onHoverEnd: () => void;
  onClick: (id: string) => void;
}) {
  const sizeMap = { ceo: 64, vp: 48, dir: 36 };
  const size = sizeMap[node.type];

  const borderColor =
    isFlashing ? 'border-green-400 shadow-[0_0_24px_rgba(0,230,118,0.6)]' :
    isSelected ? 'border-cyan-400 shadow-[0_0_20px_rgba(0,229,255,0.4)]' :
    isActive && node.type === 'dir' ? 'border-green-400/60 shadow-[0_0_12px_rgba(0,230,118,0.3)]' :
    node.type === 'ceo' ? 'border-cyan-400' :
    node.type === 'vp' ? 'border-purple-400' :
    'border-[#2a3a5a]';

  const bgGradient =
    isFlashing ? 'bg-gradient-to-br from-green-900/40 to-[#1a2235]' :
    isActive && node.type === 'dir' ? 'bg-gradient-to-br from-green-900/20 to-[#1a2235]' :
    node.type === 'ceo' ? 'bg-gradient-to-br from-[#0a0e1a] to-[#1a2235]' :
    node.type === 'vp' ? 'bg-gradient-to-br from-[#1a1040] to-[#1a2235]' :
    'bg-[#1a2235]';

  const textColor =
    isFlashing ? 'text-green-400' :
    isActive && node.type === 'dir' ? 'text-green-400' :
    node.type === 'ceo' ? 'text-cyan-400' :
    node.type === 'vp' ? 'text-purple-400' :
    'text-gray-300';

  const animClass =
    isFlashing ? 'animate-[nodeFlash_0.6s_ease-out]' :
    node.type === 'ceo' ? 'animate-[breathe_3s_ease-in-out_infinite]' :
    isActive ? 'animate-[dirPulse_2.5s_ease-in-out_infinite]' : '';

  const glowShadow =
    node.type === 'ceo' ? 'shadow-[0_0_30px_rgba(0,229,255,0.25)]' :
    node.type === 'vp' ? 'shadow-[0_0_16px_rgba(179,136,255,0.2)]' : '';

  return (
    <div
      className="absolute -translate-x-1/2 -translate-y-1/2 text-center cursor-pointer z-[2] transition-all duration-300 hover:scale-110 hover:z-10"
      style={{ left: node.x, top: node.y }}
      onMouseEnter={(e) => onHover(node, e)}
      onMouseMove={(e) => onHover(node, e)}
      onMouseLeave={onHoverEnd}
      onClick={(e) => { e.stopPropagation(); onClick(node.id); }}
    >
      <div
        className={`rounded-full flex items-center justify-center font-extrabold mx-auto border-2 ${borderColor} ${bgGradient} ${textColor} ${animClass} ${glowShadow} transition-all`}
        style={{ width: size, height: size, fontSize: node.type === 'ceo' ? 14 : node.type === 'vp' ? 11 : 9 }}
      >
        {node.label}
      </div>
      {/* Active indicator ring */}
      {isActive && node.type !== 'ceo' && (
        <div
          className="absolute rounded-full border border-green-400/30 animate-ping pointer-events-none"
          style={{ width: size + 16, height: size + 16, left: '50%', top: size / 2, transform: 'translate(-50%, -50%)' }}
        />
      )}
      <div className="text-[9px] text-gray-500 mt-1 whitespace-nowrap max-w-[80px] truncate mx-auto">
        {node.name}
      </div>
      {node.workers != null && node.workers > 0 && (
        <div className={`text-[8px] ${isActive ? 'text-green-400 font-bold' : 'text-amber-400'}`}>
          {isActive ? '● active' : `${node.workers}w`}
        </div>
      )}
    </div>
  );
}

function Badge({ color, pulse, children }: { color: string; pulse?: boolean; children: React.ReactNode }) {
  const colors: Record<string, string> = {
    cyan: 'bg-cyan-400/10 border-cyan-400/30 text-cyan-400',
    purple: 'bg-purple-400/10 border-purple-400/30 text-purple-400',
    amber: 'bg-amber-400/10 border-amber-400/30 text-amber-400',
    green: 'bg-green-400/10 border-green-400/30 text-green-400',
  };
  return (
    <span className={`px-3 py-1 rounded-xl border font-semibold flex items-center gap-2 ${colors[color]}`}>
      {pulse && <span className="w-2 h-2 rounded-full bg-green-400 shadow-[0_0_6px_rgba(0,230,118,0.6)] animate-pulse" />}
      {children}
    </span>
  );
}

function PipeStage({ label, count, color }: { label: string; count: number; color: string }) {
  const colors: Record<string, string> = {
    gray: 'text-gray-400 border-gray-600',
    cyan: 'text-cyan-400 border-cyan-400/40 bg-cyan-400/5',
    amber: 'text-amber-400 border-amber-400/40 bg-amber-400/5',
    purple: 'text-purple-400 border-purple-400/40 bg-purple-400/5',
    green: 'text-green-400 border-green-400/40 bg-green-400/5',
  };
  return (
    <span className={`px-3 py-1 rounded-lg border font-semibold text-[11px] ${colors[color]}`}>
      {label}: <b>{count}</b>
    </span>
  );
}

function Arrow() {
  return <span className="text-gray-600 animate-pulse text-sm">→</span>;
}

function TreeNode({ name, type, status, children, workers, selected, onSelect, id }: {
  name: string;
  type: 'ceo' | 'vp' | 'dir';
  status: 'active' | 'idle' | 'off';
  children?: any[];
  workers?: number;
  selected?: string | null;
  onSelect?: (id: string) => void;
  id?: string;
}) {
  const [open, setOpen] = useState(type === 'ceo' || type === 'vp');
  const isSelected = selected === id;

  const dotClass =
    status === 'active' ? 'bg-green-400 shadow-[0_0_6px_rgba(0,230,118,0.5)] animate-pulse' :
    status === 'idle' ? 'bg-cyan-400 shadow-[0_0_3px_rgba(0,229,255,0.3)]' :
    'bg-gray-600';

  const nameColor =
    isSelected ? 'text-cyan-400 font-bold' :
    type === 'ceo' ? 'text-cyan-400 font-bold' :
    type === 'vp' ? 'text-purple-400 font-semibold' :
    'text-gray-300';

  return (
    <div className="ml-1">
      <div
        className={`flex items-center gap-1.5 py-[3px] cursor-pointer hover:text-cyan-400 transition-colors rounded px-1 ${isSelected ? 'bg-cyan-400/10' : ''}`}
        onClick={() => {
          if (children && children.length > 0) setOpen(!open);
          if (onSelect && id) onSelect(id);
        }}
      >
        {children && children.length > 0 ? (
          <span className={`text-[8px] text-gray-600 transition-transform duration-200 ${open ? 'rotate-0' : '-rotate-90'}`}>▼</span>
        ) : (
          <span className="w-2" />
        )}
        <span className={`w-2 h-2 rounded-full shrink-0 ${dotClass}`} />
        <span className={`text-[11px] ${nameColor} truncate`}>{name}</span>
        {workers != null && workers > 0 && (
          <span className="text-[9px] text-gray-600 bg-white/5 px-1.5 rounded ml-auto shrink-0">{workers}w</span>
        )}
      </div>
      {open && children && children.length > 0 && (
        <div className="ml-3 border-l border-[#2a3a5a]/40 pl-2">
          {children.map((c: any, i: number) => (
            <TreeNode key={c.id || i} {...c} selected={selected} onSelect={onSelect} />
          ))}
        </div>
      )}
    </div>
  );
}
