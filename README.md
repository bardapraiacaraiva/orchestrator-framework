# Orchestrator AI Framework v9.0

**The only durable execution engine for Claude Code.** 26 Python engines. 45 API endpoints. SQLite persistence. Self-evolving.

```bash
npx orchestrator-ai-framework init
```

---

## What changed in v9.0

| v2.x (YAML-based) | v9.0 (Execution Engine) |
|---|---|
| YAML files as state | SQLite DB with ACID transactions |
| Manual task assignment | Automatic dispatch with workload awareness |
| No execution without user | FastAPI runtime executes 24/7 |
| Fixed 5-dimension scoring | Adaptive rubrics (16 profiles) |
| No learning | Evolution engine with synaptic weights |
| No crash recovery | WAL + checkpoints + replanner |
| 8 core skills | 26 Python engines + 8 skills |
| 0 API endpoints | 45 REST endpoints |
| 0 tests | 48 pytest tests |

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Runtime Engine (FastAPI)  — localhost:8422               │
│  ┌──────────┐  ┌──────────┐  ┌─────────┐  ┌──────────┐ │
│  │Scheduler │  │ 45 REST  │  │ SQLite  │  │ Auth     │ │
│  │ (30min)  │  │endpoints │  │ACID/WAL │  │ RBAC     │ │
│  └────┬─────┘  └────┬─────┘  └────┬────┘  └──────────┘ │
│       └──────────────┴─────────────┘                     │
│  ┌───────────────────────────────────────────────────┐   │
│  │              26 Python Engines                     │   │
│  │  Dispatch · State · Executor · Chain DAG ·         │   │
│  │  Quality · Evolution · AutoDiag · Guardrails ·     │   │
│  │  Tracer · Replanner · Context · Rubrics ·          │   │
│  │  LLM-Judge · Predictor · Token Meter ·             │   │
│  │  Templates · Plugins · Federation · Compliance     │   │
│  └───────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘
```

## 26 Python Engines

### Core Execution
| Engine | What it does |
|---|---|
| `executor.py` | Full pipeline: guardrails → context → rubric → trace → execute → score |
| `api_executor.py` | Direct Claude API execution with model routing (Haiku/Sonnet/Opus) |
| `dispatch_engine.py` | Keyword → skill → worker routing with workload awareness |
| `chain_executor.py` | DAG skill chains with per-step checkpoints and artifact validation |
| `session_boot.py` | Auto-dispatch + state check on session start |

### State & Persistence
| Engine | What it does |
|---|---|
| `db.py` | SQLite with WAL mode, ACID transactions, CAS checkout |
| `state_machine.py` | 4 operational states, autonomy ladder (P-A1 → P-A4) |
| `filelock.py` | OS-level file locking + write-ahead log crash recovery |
| `task_store.py` | DB-first task access with YAML fallback |

### Quality & Learning
| Engine | What it does |
|---|---|
| `quality_scorer.py` | Record scores, calculate tiers, determine actions |
| `llm_judge.py` | Auto-scoring via Haiku (LLM-as-Judge, $0.001/score) |
| `adaptive_rubric.py` | 16 skill profiles with context-adaptive dimensions |
| `evolution_runner.py` | Learning journals, synaptic weight mutations, pattern crystallization |
| `predictor.py` | Pre-execution quality/cost/risk estimates |

### Safety & Recovery
| Engine | What it does |
|---|---|
| `guardrails.py` | 7 pre-execution checks (blocks if FAIL) |
| `replanner.py` | retry → sibling → fallback → escalate cascade |
| `autodiag_runner.py` | 7 health checks with auto-fix |

### Observability
| Engine | What it does |
|---|---|
| `tracer.py` | Per-task execution traces with multi-attempt tracking |
| `audit_logger.py` | Unified append-only event trail |
| `token_meter.py` | Real token usage tracking by model/skill/project |

### Infrastructure
| Engine | What it does |
|---|---|
| `runtime.py` | FastAPI server with scheduler, SSE, dashboard |
| `auth.py` | API key authentication + RBAC (admin/operator/viewer) |
| `context_injector.py` | 6-source context assembly (memory, RAG, artifacts, hints) |
| `task_templates.py` | 5 parametric templates with ${variables} |
| `install_service.py` | Auto-start on Windows login |
| `tier3.py` | 10 differentiation features (tenancy, plugins, federation, compliance, NL, etc.) |

## 45 API Endpoints

### Tasks & Execution
```
GET  /tasks                    POST /tasks
POST /tasks/{id}/assign        POST /tasks/{id}/checkout
POST /tasks/{id}/complete      GET  /dispatch
POST /dispatch                 POST /pulse
```

### State & Monitoring
```
GET  /health                   GET  /state
POST /state/transition         GET  /audit
GET  /budget                   GET  /scores
GET  /events (SSE)             GET  /dashboard (HTML)
GET  /dashboard/data           GET  /metrics (Prometheus)
GET  /traces
```

### Chains & Templates
```
POST /chains/compose           POST /chains/{name}/start
GET  /chains                   GET  /context/{id}
GET  /rubric/{id}              GET  /templates
POST /templates/{name}/instantiate
```

### TIER 3 Features
```
GET  /agents                   POST /agents/{id}/create
POST /tenants/{id}             GET  /tenants/{id}/tasks
GET  /plugins                  POST /plugins/{name}/install
POST /workflows/create         POST /federation/peers
GET  /compliance/rgpd          GET  /compliance/soc2
GET  /ask?q=...                GET  /optimize/cost
```

## Quick Start

### Install
```bash
npx orchestrator-ai-framework init --company "Your Company" --preset agency
```

### Start Runtime
```bash
python ~/.claude/orchestrator/runtime.py --port 8422
```

### Create API Key
```bash
python ~/.claude/orchestrator/auth.py --create "admin" --role admin
```

### Run Tests
```bash
cd ~/.claude/orchestrator && python -m pytest tests/ -v
```

### Check System Health
```bash
curl http://localhost:8422/health
```

## Presets

| Preset | Workers | Skills | Best for |
|---|---|---|---|
| `agency` | 50+ | Marketing, SEO, Tech, Finance | Digital agencies |
| `saas` | 30+ | Product, Engineering, Metrics | SaaS companies |
| `studio` | 40+ | Design, Architecture, Construction | Design studios |
| `freelancer` | 10 | Core skills only | Solo professionals |

## Key Capabilities

### Self-Executing
Runtime scheduler fires heartbeat every 30 min. Tasks dispatch, execute, score, and advance automatically.

### Self-Correcting
When tasks fail: replanner auto-retries, tries sibling workers, falls back to alternative skills, or escalates to human.

### Self-Evolving
Evolution engine captures learning journals, mutates synaptic weights, and crystallizes patterns into permanent rules. Dispatch uses evolved weights for smarter routing.

### Durable
SQLite with WAL mode for ACID transactions. Per-step checkpoints in skill chains. Write-ahead log for crash recovery. Resume from any point.

### Observable
Execution traces per task. Prometheus metrics. Unified audit trail. Interactive dashboard. Natural language queries.

### Multi-Tenant
Isolated tasks, budget, and audit per tenant. RBAC with API keys. Federation for multi-instance delegation.

## Requirements

- Claude Code CLI
- Python 3.10+
- Node.js 18+ (for installer)
- FastAPI + uvicorn (`pip install fastapi uvicorn`)
- Anthropic SDK (`pip install anthropic`) — for API execution

## License

MIT

## Built by

[BARDA Digital Agency](https://github.com/bardapraiacaraiva) — 2026
