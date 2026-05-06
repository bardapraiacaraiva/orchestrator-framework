#!/usr/bin/env python3
"""
DARIO Dispatch Engine — Real-Time Task Routing
===============================================
The "brain" that automatically routes tasks to optimal workers.
Reads company.yaml hierarchy, matches capabilities, checks workload,
assigns atomically, and logs everything.

Usage:
    python dispatch_engine.py                    # Dispatch all unassigned tasks
    python dispatch_engine.py --task MNB-002     # Dispatch specific task
    python dispatch_engine.py --dry-run          # Show routing without assigning
    python dispatch_engine.py --status           # Show worker availability
    python dispatch_engine.py --explain MNB-002  # Explain WHY a routing decision was made

Exit codes:
    0 = success (at least 1 task dispatched or nothing to dispatch)
    1 = error (parse failure, missing files)
    2 = all workers busy (tasks queued)
"""

import argparse
import logging
import os
import sys
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# --- YAML handling (try ruamel for round-trip, fallback to PyYAML) ---
try:
    from ruamel.yaml import YAML
    yaml_engine = YAML()
    yaml_engine.preserve_quotes = True
    yaml_engine.width = 200

    def load_yaml(path):
        with open(path, 'r', encoding='utf-8') as f:
            return yaml_engine.load(f)

    def dump_yaml(data, path):
        with open(path, 'w', encoding='utf-8') as f:
            yaml_engine.dump(data, f)

except ImportError:
    import yaml

    def load_yaml(path):
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def dump_yaml(data, path):
        with open(path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


# --- Configuration ---
ORCH_DIR = Path.home() / ".claude" / "orchestrator"
TASKS_DIR = ORCH_DIR / "tasks" / "active"
COMPANY_FILE = ORCH_DIR / "company.yaml"
AUDIT_DIR = ORCH_DIR / "audit"
DISPATCH_LOG = ORCH_DIR / "dispatch_log.yaml"

# Workload limits
MAX_WORKER_IN_PROGRESS = 1
MAX_DIRECTOR_IN_PROGRESS = 2

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s"
)
log = logging.getLogger("dispatch")


# =============================================================================
# CORE: Load Company Hierarchy
# =============================================================================

class CompanyHierarchy:
    """Parsed company.yaml with fast lookups."""

    def __init__(self, company_data: dict):
        self.raw = company_data
        self.agents = company_data.get("agents", {})
        self.workers = company_data.get("workers", {})
        self._build_indexes()

    def _build_indexes(self):
        """Build fast-lookup indexes."""
        # Worker by skill name
        self.worker_by_skill = {}
        # Worker by ID
        self.worker_by_id = {}
        # Director manages list
        self.director_workers = {}
        # All capabilities per worker
        self.worker_capabilities = {}

        for wid, wdata in self.workers.items():
            if not isinstance(wdata, dict):
                continue
            self.worker_by_id[wid] = wdata
            skill = wdata.get("skill", "")
            if skill:
                self.worker_by_skill[skill] = wid
            caps = wdata.get("capabilities", [])
            self.worker_capabilities[wid] = set(caps) if isinstance(caps, list) else set()
            # Index by director
            reports_to = wdata.get("reports_to", "")
            if reports_to:
                self.director_workers.setdefault(reports_to, []).append(wid)

        # Agent (director/VP) by ID
        self.agent_by_id = {}
        for akey, adata in self.agents.items():
            if isinstance(adata, dict) and "id" in adata:
                self.agent_by_id[adata["id"]] = adata

    def get_worker(self, worker_id: str) -> Optional[dict]:
        return self.worker_by_id.get(worker_id)

    def get_worker_for_skill(self, skill: str) -> Optional[str]:
        return self.worker_by_skill.get(skill)

    def get_siblings(self, worker_id: str) -> list:
        """Get other workers under the same director."""
        worker = self.worker_by_id.get(worker_id)
        if not worker:
            return []
        director = worker.get("reports_to", "")
        siblings = self.director_workers.get(director, [])
        return [s for s in siblings if s != worker_id]

    def get_director(self, worker_id: str) -> Optional[dict]:
        """Get the director that manages this worker."""
        worker = self.worker_by_id.get(worker_id)
        if not worker:
            return None
        director_id = worker.get("reports_to", "")
        return self.agent_by_id.get(director_id)

    def get_director_capabilities(self, director_id: str) -> set:
        """Get capabilities of a director."""
        agent = self.agent_by_id.get(director_id)
        if agent:
            caps = agent.get("capabilities", [])
            return set(caps) if isinstance(caps, list) else set()
        return set()


# =============================================================================
# CORE: Task Loading
# =============================================================================

def load_tasks() -> list:
    """Load all active tasks (DB-first, YAML fallback)."""
    try:
        from task_store import TaskStore
        return TaskStore().get_all()
    except Exception:
        # Fallback to YAML
        tasks = []
        if not TASKS_DIR.exists():
            return tasks
        for f in TASKS_DIR.glob("*.yaml"):
            try:
                data = load_yaml(str(f))
                if data:
                    data["_file"] = str(f)
                    tasks.append(data)
            except Exception as e:
                log.warning(f"Failed to parse {f.name}: {e}")
        return tasks


def get_unassigned_tasks(tasks: list) -> list:
    """Get tasks that need dispatch (status=todo, no assignee)."""
    return [
        t for t in tasks
        if t.get("status") == "todo"
        and not t.get("assignee")
    ]


def get_worker_workload(tasks: list) -> dict:
    """Calculate current workload per worker (fixed: was calling wrong signature)."""
    try:
        from db import DB
        db = DB()
        active = db.get_tasks(status="in_progress") + db.get_tasks(status="todo") + db.get_tasks(status="in_review")
        workload = {}
        for t in active:
            assignee = t.get("assignee")
            if assignee:
                workload[assignee] = workload.get(assignee, 0) + 1
        return workload
    except Exception:
        workload = {}
        for t in tasks:
            assignee = t.get("assignee")
            if not assignee:
                continue
            status = t.get("status", "")
            if status in ("todo", "in_progress", "in_review"):
                workload[assignee] = workload.get(assignee, 0) + 1
        return workload


def is_worker_available(worker_id: str, workload: dict) -> bool:
    """Check if worker can accept new work."""
    current = workload.get(worker_id, 0)
    return current < MAX_WORKER_IN_PROGRESS


def is_director_available(director_id: str, workload: dict) -> bool:
    """Check if director can accept execution work."""
    current = workload.get(director_id, 0)
    return current < MAX_DIRECTOR_IN_PROGRESS


# =============================================================================
# CORE: Routing Algorithm
# =============================================================================

# Keyword → Skill routing table (from dispatch SKILL.md)
KEYWORD_SKILL_MAP = {
    # Marketing
    "brand": "dario-brand", "positioning": "dario-brand", "archetype": "dario-brand", "marca": "dario-brand",
    "offer": "dario-offer", "oferta": "dario-offer", "pricing": "dario-offer", "hormozi": "dario-offer",
    "sales letter": "dario-sales-letter", "copy": "dario-sales-letter", "vsl": "dario-sales-letter",
    "ads": "dario-ads-blueprint", "traffic": "dario-ads-blueprint", "facebook ads": "dario-ads-blueprint",
    "funnel": "dario-funnel", "funil": "dario-funnel", "value ladder": "dario-funnel", "tripwire": "dario-funnel",
    "pipeline": "dario-pipeline", "outbound": "dario-pipeline", "prospecting": "dario-pipeline",
    "email": "dario-email-seq", "sequence": "dario-email-seq", "nurture": "dario-email-seq",
    "naming": "dario-naming", "brand name": "dario-naming", "domain": "dario-naming",
    "story": "dario-story-circle", "narrative": "dario-story-circle", "narrativa": "dario-story-circle", "about page": "dario-story-circle", "historia": "dario-story-circle",
    "pitch": "dario-pitch", "investor": "dario-pitch", "deck": "dario-pitch",
    "proposal": "dario-proposal", "quotation": "dario-proposal",
    "negotiation": "dario-negotiation", "objections": "dario-negotiation",
    # Technical
    "wordpress": "dario-wp-audit", "wp": "dario-wp-audit",
    "woocommerce": "dario-woo-audit", "checkout": "dario-woo-audit", "mbway": "dario-woo-audit",
    "core web vitals": "dario-cwv-fix", "lcp": "dario-cwv-fix", "inp": "dario-cwv-fix",
    "pentest": "dario-pentest-checklist", "security": "dario-pentest-checklist", "owasp": "dario-pentest-checklist",
    "make": "dario-make-blueprint", "automation": "dario-make-blueprint", "zapier": "dario-make-blueprint",
    "ios": "dario-ios-hig", "hig": "dario-ios-hig", "swift": "dario-ios-hig",
    "sop": "dario-sop", "procedure": "dario-sop", "checklist": "dario-sop",
    # SEO
    "seo audit": "seo-audit", "site health": "seo-audit",
    "crawl": "seo-technical", "robots": "seo-technical", "indexation": "seo-technical",
    "content quality": "seo-content", "eeat": "seo-content", "readability": "seo-content",
    "schema": "seo-schema", "json-ld": "seo-schema", "structured data": "seo-schema",
    "local seo": "seo-local", "seo local": "seo-local", "gbp": "seo-local", "nap": "seo-local", "citations": "seo-local", "google maps": "seo-local",
    "ai overviews": "seo-geo", "geo": "seo-geo", "perplexity": "seo-geo",
    "seo strategy": "seo-plan", "estrategia seo": "seo-plan", "content plan": "seo-plan", "site architecture": "seo-plan",
    "single page": "seo-page", "on-page": "seo-page",
    "sitemap": "seo-sitemap", "xml sitemap": "seo-sitemap",
    "image seo": "seo-images", "alt text": "seo-images",
    "hreflang": "seo-hreflang", "international": "seo-hreflang",
    "programmatic seo": "seo-programmatic", "scaled pages": "seo-programmatic",
    "competitor": "seo-competitor-pages", "alternatives": "seo-competitor-pages",
    "keyword data": "seo-dataforseo", "serp": "seo-dataforseo", "backlinks": "seo-dataforseo",
    "og image": "seo-image-gen", "social preview": "seo-image-gen",
    "keyword cluster": "dario-kw-cluster", "topic map": "dario-kw-cluster",
    # Finance
    "p&l": "dario-financial-model", "cash flow": "dario-financial-model", "forecast": "dario-financial-model",
    "pricing calculator": "dario-pricing-calculator", "cost/hour": "dario-pricing-calculator",
    "mrr": "dario-saas-metrics", "churn": "dario-saas-metrics", "ltv": "dario-saas-metrics",
    # Client Success
    "onboard": "dario-client-onboard", "kickoff": "dario-client-onboard", "novo cliente": "dario-client-onboard",
    "diagnose": "dario-diagnose", "diagnostico": "dario-diagnose", "diagnóstico": "dario-diagnose",
    "project": "dario-projeto", "context": "dario-projeto",
    # DIVA
    "moodboard": "diva-moodboard", "materials": "diva-materials",
    "floor plan": "diva-floor-plan", "planta": "diva-floor-plan",
    "render": "diva-render", "3d": "diva-render",
    "budget estimation": "diva-budget", "orcamento obra": "diva-budget", "orcamento": "diva-budget", "orçamento": "diva-budget", "custo obra": "diva-budget", "remodelação": "diva-budget", "remodelacao": "diva-budget",
    "timeline": "diva-timeline", "cronograma": "diva-timeline",
    "inspection": "diva-inspection", "vistoria": "diva-inspection",
    "contract": "diva-contract", "empreitada": "diva-contract",
    "licensing": "diva-licensing", "camara": "diva-licensing", "alvara": "diva-licensing", "licenciamento": "diva-licensing", "licença": "diva-licensing",
    "energy": "diva-energy", "sce": "diva-energy",
    "smart home": "diva-smart-home", "domotica": "diva-smart-home",
    # DIVA (extended)
    "briefing": "diva-briefing", "questionario": "diva-briefing",
    "bim": "diva-bim", "revit": "diva-bim", "archicad": "diva-bim",
    "landscape": "diva-landscape", "paisagismo": "diva-landscape", "jardim": "diva-landscape",
    "mep": "diva-mep", "avac": "diva-mep", "canalizacao": "diva-mep",
    "acoustics": "diva-acoustics", "acustica": "diva-acoustics", "isolamento sonoro": "diva-acoustics",
    "accessibility": "diva-accessibility", "mobilidade reduzida": "diva-accessibility",
    "ffe": "diva-ffe", "mobiliario projecto": "diva-ffe",
    "pss": "diva-inspection", "seguranca obra": "diva-inspection",
    "roadmap projecto": "diva-roadmap",
    "portfolio caso": "diva-portfolio",
    "comparar propostas": "diva-comparador", "comparador": "diva-comparador",
    "planradar": "diva-planradar",
    "render brief": "diva-render-brief",
    "vision foto": "diva-vision", "analisar foto": "diva-vision",
    # Marketing (extended)
    "content": "dario-content", "editorial": "dario-content", "blog post": "dario-content", "artigo": "dario-content",
    "social media": "dario-social", "instagram": "dario-social", "linkedin": "dario-social", "tiktok": "dario-social", "reels": "dario-social",
    "press release": "dario-pr", "comunicado": "dario-pr", "media": "dario-pr",
    "cro": "dario-cro", "conversion": "dario-cro", "ab test": "dario-cro",
    "data analytics": "dario-data", "google analytics": "dario-data",
    "movement": "dario-movement", "tribal": "dario-movement", "comunidade": "dario-movement",
    "product": "dario-product", "prd": "dario-product", "user stories": "dario-product", "sprint": "dario-product",
    "layout": "dario-layout-visual", "typography": "dario-layout-visual", "grid": "dario-layout-visual",
    # HR / Legal / Support
    "hiring": "dario-hr", "recruitment": "dario-hr", "recrutamento": "dario-hr", "job description": "dario-hr",
    "legal": "dario-legal", "nda": "dario-legal", "termos servico": "dario-legal", "rgpd": "dario-legal",
    "support ticket": "dario-support", "faq": "dario-support", "helpdesk": "dario-support",
    # C-Level
    "c-level": "dario-c-level", "okr": "dario-c-level", "strategic vision": "dario-c-level", "visao estrategica": "dario-c-level",
    # A360 Skills
    "nicho": "a360-nicho", "tam sam": "a360-nicho", "market validation": "a360-nicho",
    "avatar": "a360-avatar", "buyer persona": "a360-avatar", "cliente ideal": "a360-avatar",
    "case study": "a360-case-study", "caso sucesso": "a360-case-study",
    "funil aquisicao": "a360-funil", "lead magnet": "a360-funil",
    "growth engine": "a360-growth", "viral loop": "a360-growth", "referral": "a360-growth",
    "lancamento": "a360-lancamento", "launch": "a360-lancamento", "pre-launch": "a360-lancamento",
    "metricas negocio": "a360-metricas", "burn rate": "a360-metricas", "runway": "a360-metricas",
    "business model": "a360-modelo", "unit economics": "a360-modelo", "revenue stream": "a360-modelo",
    "grand slam": "a360-oferta", "irresistible offer": "a360-oferta",
    "investor pitch": "a360-pitch", "fundraising": "a360-pitch",
    "scaling": "a360-scale", "escalar": "a360-scale", "milestone": "a360-scale",
    "validacao": "a360-validacao", "smoke test": "a360-validacao", "mvp": "a360-validacao",
    # ATLAS Events
    "evento": "atlas-briefing", "event planning": "atlas-briefing",
    "venue": "atlas-venue", "espaco evento": "atlas-venue",
    "catering": "atlas-catering", "menu evento": "atlas-catering",
    "av setup": "atlas-av", "som evento": "atlas-av", "iluminacao evento": "atlas-av",
    "event budget": "atlas-budget", "orcamento evento": "atlas-budget",
    "rsvp": "atlas-guest", "convidados": "atlas-guest",
    "event marketing": "atlas-marketing", "promover evento": "atlas-marketing",
    "staffing evento": "atlas-staff", "equipa evento": "atlas-staff",
    "event timeline": "atlas-timeline", "run of show": "atlas-timeline",
    "sponsor": "atlas-sponsor", "patrocinio": "atlas-sponsor",
    "hybrid event": "atlas-hybrid", "evento virtual": "atlas-hybrid",
    # LUCAS internal
    "budget tracking": "lucas-budget-tracking", "token usage": "lucas-budget-tracking",
    "cost alert": "lucas-cost-alerting",
    "stale task": "lucas-stale-detection",
    "system health": "lucas-health-monitoring",
    "feedback loop": "lucas-feedback-loop",
    "skill evaluation": "lucas-skill-evaluation",
    "revenue tracking": "lucas-revenue-tracking",
    # Contabilidade
    "facturacao": "conta-facturacao", "e-fatura": "conta-facturacao", "saft": "conta-facturacao",
    "iva": "conta-iva", "declaracao iva": "conta-iva",
    "irc": "conta-irc", "modelo 22": "conta-irc",
    "payroll": "conta-payroll", "salarios": "conta-payroll", "dmr": "conta-payroll",
    "balancete": "conta-relatorios", "demonstracao resultados": "conta-relatorios",
    # Restaurante
    "restaurante": "skill-restaurante-pt", "menu": "skill-restaurante-pt", "gastronomico": "skill-restaurante-pt",
    # Standalone + Portuguese terms (fixed: common PT terms were missing)
    "seo": "seo-audit",
    "website": "dario-wp-audit",
    "auditoria": "dario-diagnose",
    "analise": "dario-diagnose",
    "relatorio": "dario-diagnose",
    "otimizacao": "dario-cwv-fix",
    "optimizacao": "dario-cwv-fix",
    "campanha": "dario-ads-blueprint",
    "proposta": "dario-proposal",
    "apresentacao": "dario-pitch",
    "reuniao": "dario-sop",
    "pagina": "dario-funnel",
    "landing page": "dario-funnel",
}


def infer_skill_from_task(task: dict) -> Optional[str]:
    """Infer the best skill for a task using multiple signals."""
    # Signal 1: Explicit skill field (strongest)
    if task.get("skill"):
        return task["skill"]

    # Signal 2: Keyword matching from title + description
    text = f"{task.get('title', '')} {task.get('description', '')}".lower()

    # Try multi-word matches first (more specific)
    scores = {}
    for keyword, skill in sorted(KEYWORD_SKILL_MAP.items(), key=lambda x: -len(x[0])):
        if keyword in text:
            scores[skill] = scores.get(skill, 0) + len(keyword)

    if scores:
        # Tie-breaking: prefer skill matching MORE keywords, then title-match bonus (fixed: was non-deterministic)
        title = task.get("title", "").lower()
        keyword_counts = {}
        for keyword, skill in KEYWORD_SKILL_MAP.items():
            if keyword in text and skill in scores:
                keyword_counts[skill] = keyword_counts.get(skill, 0) + 1
                if keyword in title:
                    scores[skill] = scores.get(skill, 0) + 10  # Title match bonus
        return max(scores, key=scores.get)

    return None


def load_synaptic_weights() -> dict:
    """Load synaptic weights for dispatch boosting."""
    weights_file = ORCH_DIR / "synaptic_weights.yaml"
    if not weights_file.exists():
        return {}
    try:
        data = load_yaml(str(weights_file))
        return data.get("affinity_graph", {}) if data else {}
    except Exception:
        return {}


def get_weight_boost(skill: str, weights: dict) -> float:
    """
    Get dispatch boost from synaptic weights.
    If this skill has high affinity with recently successful skills, boost it.
    Returns: multiplier (1.0 = no boost, up to 1.3 = strong boost)
    """
    if not weights:
        return 1.0

    boosts = []
    for pair_key, pair_data in weights.items():
        if not isinstance(pair_data, dict):
            continue
        # Parse pair key correctly: "skill-a + skill-b"
        parts = [p.strip() for p in pair_key.split(" + ")]
        if skill not in parts:
            continue
        weight = float(pair_data.get("weight", 0.5))
        co_activations = int(pair_data.get("co_activations", 0))
        if weight > 0.5 and co_activations > 0:
            # Boost proportional to weight above baseline
            boosts.append(weight - 0.5)

    if boosts:
        avg_boost = sum(boosts) / len(boosts)
        return round(1.0 + min(avg_boost * 0.6, 0.3), 3)  # Cap at 1.3x

    return 1.0


def find_best_worker(task: dict, hierarchy: CompanyHierarchy, workload: dict, explain: bool = False) -> tuple:
    """
    Core routing algorithm. Returns (worker_id, reason) or (None, reason).

    Algorithm:
    1. Direct skill match → worker for that skill
    2. Synaptic weight boost (evolution learning feedback)
    3. If busy → fallback to sibling workers with capability overlap
    4. If all siblings busy → escalate to director
    5. If director busy → queue (return None)
    """
    reasons = []
    skill = infer_skill_from_task(task)

    # Load evolution weights for dispatch boosting
    weights = load_synaptic_weights()
    boost = get_weight_boost(skill, weights) if skill else 1.0
    if boost > 1.0:
        reasons.append(f"WEIGHT_BOOST: {boost:.3f}x (evolution affinity)")


    if not skill:
        reasons.append("NO_SKILL_MATCH: Could not infer skill from task title/description")
        return None, reasons

    reasons.append(f"SKILL_INFERRED: {skill}")

    # Step 1: Direct skill → worker
    worker_id = hierarchy.get_worker_for_skill(skill)
    if not worker_id:
        reasons.append(f"NO_WORKER: No worker registered for skill '{skill}'")
        return None, reasons

    reasons.append(f"PRIMARY_WORKER: {worker_id}")

    # Step 2: Check availability
    if is_worker_available(worker_id, workload):
        reasons.append(f"AVAILABLE: {worker_id} has no in_progress tasks")
        return worker_id, reasons

    # Worker busy — find fallback
    reasons.append(f"BUSY: {worker_id} has {workload.get(worker_id, 0)} active tasks")

    # Step 3: Try sibling workers with capability overlap
    task_caps = set()
    worker_data = hierarchy.get_worker(worker_id)
    if worker_data:
        task_caps = hierarchy.worker_capabilities.get(worker_id, set())

    siblings = hierarchy.get_siblings(worker_id)
    for sibling_id in siblings:
        sibling_caps = hierarchy.worker_capabilities.get(sibling_id, set())
        overlap = task_caps & sibling_caps
        if overlap and is_worker_available(sibling_id, workload):
            reasons.append(f"FALLBACK_SIBLING: {sibling_id} (overlap: {overlap})")
            return sibling_id, reasons

    reasons.append("NO_SIBLING_AVAILABLE: All siblings busy or no capability overlap")

    # Step 4: Escalate to director
    director = hierarchy.get_director(worker_id)
    if director:
        director_id = director.get("id", "")
        if is_director_available(director_id, workload):
            reasons.append(f"ESCALATE_DIRECTOR: {director_id}")
            return director_id, reasons
        reasons.append(f"DIRECTOR_BUSY: {director_id}")

    # Step 5: Queue — no one available
    reasons.append("QUEUED: No executor available, task stays in todo")
    return None, reasons


# =============================================================================
# CORE: Assignment (Atomic Write)
# =============================================================================

def assign_task(task: dict, worker_id: str, reasons: list) -> bool:
    """Atomically assign a task to a worker with file locking."""
    task_file = task.get("_file")
    if not task_file or not os.path.exists(task_file):
        log.error(f"Task file not found: {task_file}")
        return False

    try:
        from filelock import YAMLLock
        with YAMLLock(task_file, timeout=5) as lock:
            data = lock.read()
            if not data:
                return False

            # Atomic: check status hasn't changed since we read it
            if data.get("status") != "todo":
                log.warning(f"Task {data.get('id')} status changed (race condition avoided)")
                return False
            if data.get("assignee"):
                log.warning(f"Task {data.get('id')} already assigned (race condition avoided)")
                return False

            # Assign
            now = datetime.now(timezone.utc).isoformat()
            data["assignee"] = worker_id
            data["assigned_at"] = now
            data["dispatch_reason"] = reasons[-1] if reasons else "direct_match"

            lock.write(data)
        log.info(f"DISPATCHED: {data.get('id')} → {worker_id}")
        return True

    except TimeoutError:
        log.warning(f"Lock timeout on {task_file} — skipping (another process holds lock)")
        return False
    except ImportError:
        # Fallback: no locking (backwards compat)
        data = load_yaml(task_file)
        if not data or data.get("status") != "todo" or data.get("assignee"):
            return False
        data["assignee"] = worker_id
        data["assigned_at"] = datetime.now(timezone.utc).isoformat()
        data["dispatch_reason"] = reasons[-1] if reasons else "direct_match"
        dump_yaml(data, task_file)
        log.info(f"DISPATCHED (no lock): {data.get('id')} → {worker_id}")
        return True
    except Exception as e:
        log.error(f"Failed to assign task: {e}")
        return False


# =============================================================================
# CORE: Audit Logging
# =============================================================================

def log_dispatch(task_id: str, worker_id: Optional[str], reasons: list, dry_run: bool = False):
    """Append dispatch decision to audit log."""
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_file = AUDIT_DIR / f"dispatch_{today}.log"

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "task_id": task_id,
        "assigned_to": worker_id or "QUEUED",
        "dry_run": dry_run,
        "reasons": reasons,
    }

    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(f"[{entry['timestamp']}] {task_id} → {entry['assigned_to']}")
        if dry_run:
            f.write(" (DRY RUN)")
        f.write(f" | {' > '.join(reasons)}\n")


# =============================================================================
# COMMANDS
# =============================================================================

def cmd_dispatch(args):
    """Main dispatch command — route unassigned tasks."""
    if not COMPANY_FILE.exists():
        log.error(f"company.yaml not found at {COMPANY_FILE}")
        return 1

    company_data = load_yaml(str(COMPANY_FILE))
    hierarchy = CompanyHierarchy(company_data)
    tasks = load_tasks()
    workload = get_worker_workload(tasks)

    # Filter to target tasks
    if args.task:
        targets = [t for t in tasks if t.get("id") == args.task]
        if not targets:
            log.error(f"Task {args.task} not found in active tasks")
            return 1
    else:
        targets = get_unassigned_tasks(tasks)

    if not targets:
        if args.json:
            import json
            print(json.dumps({"dispatched": 0, "queued": 0, "total_analyzed": 0, "assignments": []}))
        else:
            log.info("No unassigned tasks to dispatch.")
        return 0

    dispatched = 0
    queued = 0
    assignments_log = []

    for task in targets:
        task_id = task.get("id", "UNKNOWN")
        worker_id, reasons = find_best_worker(task, hierarchy, workload, explain=args.dry_run)

        assignments_log.append({
            "task_id": task_id,
            "assigned_to": worker_id,
            "skill": infer_skill_from_task(task),
            "reason": reasons[-1] if reasons else "unknown",
        })

        if args.dry_run:
            status = f"→ {worker_id}" if worker_id else "→ QUEUED"
            print(f"  {task_id}: {status}")
            for r in reasons:
                print(f"    {r}")
            print()
        else:
            if worker_id:
                success = assign_task(task, worker_id, reasons)
                if success:
                    dispatched += 1
                    # Update workload for next iteration
                    workload[worker_id] = workload.get(worker_id, 0) + 1
            else:
                queued += 1

        log_dispatch(task_id, worker_id, reasons, dry_run=args.dry_run)

    # Summary
    if args.json:
        import json
        result = {
            "dispatched": dispatched,
            "queued": queued,
            "total_analyzed": len(targets),
            "assignments": assignments_log,
        }
        print(json.dumps(result, indent=2))
    elif args.dry_run:
        print(f"--- DRY RUN: {len(targets)} tasks analyzed ---")
    else:
        log.info(f"Dispatch complete: {dispatched} assigned, {queued} queued")

    return 0 if dispatched > 0 or queued == 0 else 2


def cmd_status(args):
    """Show worker availability status."""
    if not COMPANY_FILE.exists():
        log.error(f"company.yaml not found")
        return 1

    company_data = load_yaml(str(COMPANY_FILE))
    hierarchy = CompanyHierarchy(company_data)
    tasks = load_tasks()
    workload = get_worker_workload(tasks)

    print("=== WORKER AVAILABILITY ===\n")

    # Group by director
    for director_id, worker_ids in sorted(hierarchy.director_workers.items()):
        director = hierarchy.agent_by_id.get(director_id, {})
        dir_name = director.get("title", director_id)
        dir_load = workload.get(director_id, 0)
        print(f"[{director_id}] {dir_name} (load: {dir_load}/{MAX_DIRECTOR_IN_PROGRESS})")

        for wid in worker_ids:
            wdata = hierarchy.worker_by_id.get(wid, {})
            skill = wdata.get("skill", "?")
            load = workload.get(wid, 0)
            avail = "✓" if load < MAX_WORKER_IN_PROGRESS else "✗ BUSY"
            print(f"  {avail} {wid} ({skill}) — load: {load}/{MAX_WORKER_IN_PROGRESS}")

        print()

    # Unassigned tasks
    unassigned = get_unassigned_tasks(tasks)
    if unassigned:
        print(f"=== PENDING DISPATCH: {len(unassigned)} tasks ===")
        for t in unassigned:
            print(f"  [{t.get('id')}] {t.get('title', '?')}")
    else:
        print("=== All tasks assigned ===")

    return 0


def cmd_explain(args):
    """Explain routing decision for a specific task."""
    if not COMPANY_FILE.exists():
        log.error(f"company.yaml not found")
        return 1

    company_data = load_yaml(str(COMPANY_FILE))
    hierarchy = CompanyHierarchy(company_data)
    tasks = load_tasks()
    workload = get_worker_workload(tasks)

    target = [t for t in tasks if t.get("id") == args.explain]
    if not target:
        log.error(f"Task {args.explain} not found")
        return 1

    task = target[0]
    print(f"=== DISPATCH EXPLANATION: {args.explain} ===\n")
    print(f"Title: {task.get('title', '?')}")
    print(f"Description: {task.get('description', '?')}")
    print(f"Skill (explicit): {task.get('skill', 'none')}")
    print(f"Status: {task.get('status')}")
    print(f"Current assignee: {task.get('assignee', 'none')}")
    print()

    # Run routing
    inferred_skill = infer_skill_from_task(task)
    print(f"Inferred skill: {inferred_skill}")

    worker_id, reasons = find_best_worker(task, hierarchy, workload, explain=True)

    print(f"\nRouting decision: {'→ ' + worker_id if worker_id else 'QUEUED (no available worker)'}")
    print(f"\nReasoning chain:")
    for i, r in enumerate(reasons, 1):
        print(f"  {i}. {r}")

    return 0


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="DARIO Dispatch Engine — Automatic task routing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument("--task", "-t", help="Dispatch specific task by ID")
    parser.add_argument("--dry-run", "-n", action="store_true", help="Show routing without assigning")
    parser.add_argument("--status", "-s", action="store_true", help="Show worker availability")
    parser.add_argument("--explain", "-e", help="Explain routing for a task ID")
    parser.add_argument("--json", "-j", action="store_true", help="Output results as JSON (for autopilot integration)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    elif args.json:
        logging.getLogger().setLevel(logging.ERROR)  # Suppress INFO in JSON mode

    if args.status:
        return cmd_status(args)
    elif args.explain:
        return cmd_explain(args)
    else:
        return cmd_dispatch(args)


if __name__ == "__main__":
    sys.exit(main())
