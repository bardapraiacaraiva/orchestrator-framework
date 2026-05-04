"""Live dashboard — real data from PostgreSQL."""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from .. import database
from ..services.fitness import get_fitness_trend
from ..services.state_machine import get_state

router = APIRouter()


@router.get("/dashboard/data")
async def dashboard_data():
    """All dashboard metrics in one call."""
    state = await get_state()
    fitness_trend = await get_fitness_trend(20)

    async with database.pool.connection() as conn:
        # Task stats
        row = await conn.execute("SELECT status, COUNT(*) FROM orch.tasks GROUP BY status")
        task_counts = dict(await row.fetchall())

        # Quality trend (last 20)
        row = await conn.execute("SELECT composite_score, skill, scored_at FROM orch.quality_scores ORDER BY scored_at DESC LIMIT 20")
        quality_entries = [{"score": r[0], "skill": r[1], "at": r[2].isoformat()} for r in await row.fetchall()]

        # Budget
        row = await conn.execute("SELECT month, total_tokens, percentage FROM orch.budget_monthly ORDER BY month DESC LIMIT 1")
        budget = await row.fetchone()

        # Recent audit
        row = await conn.execute("SELECT event_code, severity, recorded_at FROM orch.audit_log ORDER BY recorded_at DESC LIMIT 10")
        audit = [{"event": r[0], "severity": r[1], "at": r[2].isoformat()} for r in await row.fetchall()]

        # Mutations
        row = await conn.execute("SELECT file_mutated, field_changed, status, applied_at FROM orch.mutations ORDER BY applied_at DESC LIMIT 10")
        mutations = [{"file": r[0], "field": r[1], "status": r[2], "at": r[3].isoformat()} for r in await row.fetchall()]

        # Patterns
        row = await conn.execute("SELECT pattern_type, description, occurrences, crystallized FROM orch.patterns ORDER BY occurrences DESC LIMIT 10")
        patterns = [{"type": r[0], "desc": r[1], "count": r[2], "crystallized": r[3]} for r in await row.fetchall()]

        # Synaptic weights
        row = await conn.execute("SELECT skill_a, skill_b, weight, co_activations FROM orch.synaptic_weights ORDER BY weight DESC LIMIT 10")
        weights = [{"pair": f"{r[0]} + {r[1]}", "weight": round(r[2], 3), "co_act": r[3]} for r in await row.fetchall()]

    return {
        "state": state,
        "tasks": task_counts,
        "fitness_trend": fitness_trend,
        "quality_recent": quality_entries,
        "budget": {"month": budget[0], "tokens": budget[1], "pct": budget[2]} if budget else None,
        "audit_recent": audit,
        "mutations": mutations,
        "patterns": patterns,
        "weights": weights,
    }


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Serve live HTML dashboard."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>DARIO Orchestrator — Live Dashboard</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:system-ui,-apple-system,sans-serif;background:#0a0a0f;color:#e0e0e0;padding:20px}
h1{font-size:1.5rem;color:#00d4ff;margin-bottom:20px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;margin-bottom:20px}
.card{background:#1a1a2e;border:1px solid #2a2a4e;border-radius:12px;padding:16px}
.card h3{font-size:.85rem;color:#888;text-transform:uppercase;margin-bottom:8px}
.card .value{font-size:1.8rem;font-weight:700;color:#00d4ff}
.card .sub{font-size:.8rem;color:#666;margin-top:4px}
.state-ACTIVE{color:#00ff88}.state-REFLECTIVE_PAUSE{color:#ffaa00}.state-GUARDIAN{color:#ff4444}.state-EXPANSION{color:#aa66ff}
.badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:.75rem;font-weight:600}
.badge-info{background:#1a3a5c;color:#4da6ff}.badge-warning{background:#5c4a1a;color:#ffaa00}.badge-critical{background:#5c1a1a;color:#ff4444}
table{width:100%;border-collapse:collapse;font-size:.85rem}
th,td{padding:6px 10px;text-align:left;border-bottom:1px solid #2a2a4e}
th{color:#888;font-weight:500}
.sparkline{display:flex;align-items:end;gap:2px;height:40px}
.sparkline .bar{background:#00d4ff;border-radius:2px;min-width:8px;transition:height .3s}
#refresh{position:fixed;top:10px;right:10px;background:#1a1a2e;border:1px solid #2a2a4e;color:#888;padding:6px 12px;border-radius:6px;cursor:pointer}
</style>
</head>
<body>
<h1>DARIO Orchestrator v2.1-ALIVE</h1>
<button id="refresh" onclick="load()">Refresh</button>
<div class="grid" id="cards"></div>
<div class="grid">
<div class="card"><h3>Fitness Trend</h3><div class="sparkline" id="sparkline"></div></div>
<div class="card"><h3>Synaptic Weights</h3><table id="weights"><tr><th>Pair</th><th>Weight</th></tr></table></div>
</div>
<div class="grid">
<div class="card"><h3>Mutations</h3><table id="mutations"><tr><th>Field</th><th>Status</th></tr></table></div>
<div class="card"><h3>Patterns</h3><table id="patterns"><tr><th>Type</th><th>Count</th><th>Crystallized</th></tr></table></div>
<div class="card"><h3>Recent Audit</h3><table id="audit"><tr><th>Event</th><th>Time</th></tr></table></div>
</div>
<script>
async function load(){
 const r=await fetch('/dashboard/data');const d=await r.json();
 const s=d.state;
 document.getElementById('cards').innerHTML=`
  <div class="card"><h3>State</h3><div class="value state-${s.state}">${s.state}</div><div class="sub">Autonomy: ${s.autonomy_level} | Gen ${s.generation}</div></div>
  <div class="card"><h3>System Health</h3><div class="value">${(s.system_health*100).toFixed(1)}%</div><div class="sub">Fitness: ${(s.fitness_score*100).toFixed(1)}%</div></div>
  <div class="card"><h3>Tasks</h3><div class="value">${Object.values(d.tasks).reduce((a,b)=>a+b,0)}</div><div class="sub">Done: ${d.tasks.done||0} | Active: ${d.tasks.in_progress||0} | Blocked: ${d.tasks.blocked||0}</div></div>
  <div class="card"><h3>Budget</h3><div class="value">${d.budget?d.budget.pct.toFixed(1)+'%':'0%'}</div><div class="sub">${d.budget?d.budget.tokens.toLocaleString()+' tokens':'-'}</div></div>
  <div class="card"><h3>Quality (last 20)</h3><div class="value">${d.quality_recent.length?((d.quality_recent.reduce((a,b)=>a+b.score,0)/d.quality_recent.length).toFixed(1)):'—'}</div><div class="sub">${d.quality_recent.length} scores recorded</div></div>
  <div class="card"><h3>Total Completed</h3><div class="value">${s.total_tasks_completed}</div><div class="sub">Since ${new Date(s.started_at).toLocaleDateString()}</div></div>
 `;
 // Sparkline
 const sp=document.getElementById('sparkline');
 if(d.fitness_trend.length){
  const max=Math.max(...d.fitness_trend.map(e=>e.fitness),0.01);
  sp.innerHTML=d.fitness_trend.map(e=>`<div class="bar" style="height:${(e.fitness/max)*40}px" title="${(e.fitness*100).toFixed(1)}%"></div>`).join('');
 }
 // Weights
 const wt=document.getElementById('weights');
 wt.innerHTML='<tr><th>Pair</th><th>Weight</th></tr>'+(d.weights||[]).map(w=>`<tr><td>${w.pair}</td><td><strong>${w.weight}</strong> (${w.co_act}x)</td></tr>`).join('');
 // Mutations
 const mt=document.getElementById('mutations');
 mt.innerHTML='<tr><th>Field</th><th>Status</th></tr>'+(d.mutations||[]).map(m=>`<tr><td style="font-size:.75rem">${m.field.split('.').pop()}</td><td><span class="badge badge-info">${m.status}</span></td></tr>`).join('');
 // Patterns
 const pt=document.getElementById('patterns');
 pt.innerHTML='<tr><th>Type</th><th>Count</th><th>Crystal</th></tr>'+(d.patterns||[]).map(p=>`<tr><td>${p.type}</td><td>${p.count}/5</td><td>${p.crystallized?'Yes':'No'}</td></tr>`).join('');
 // Audit
 const at=document.getElementById('audit');
 at.innerHTML='<tr><th>Event</th><th>Time</th></tr>'+d.audit_recent.map(e=>`<tr><td><span class="badge badge-${e.severity}">${e.event}</span></td><td>${new Date(e.at).toLocaleTimeString()}</td></tr>`).join('');
}
load();setInterval(load,30000);
</script>
</body>
</html>"""
