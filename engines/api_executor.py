#!/usr/bin/env python3
"""
DARIO API Executor — Direct Claude API execution (THE GAME CHANGER).
=====================================================================
Invokes Claude API directly via Anthropic SDK. No Claude session needed.
Runtime can execute tasks 24/7 autonomously.

Model routing:
    - Haiku:  simple tasks, quality scoring (cheap, fast)
    - Sonnet: standard tasks (best cost/quality ratio)
    - Opus:   critical tasks, complex chains (max quality)

Features:
    - Prompt caching (system prompt reused across tasks of same skill)
    - Real token metering (from API response, not estimates)
    - Streaming support (partial output in real-time)
    - Cost tracking (per-model pricing)
    - Retry with exponential backoff

Usage:
    python api_executor.py --task MNB-002                    # Execute task (auto model)
    python api_executor.py --task MNB-002 --model sonnet     # Force model
    python api_executor.py --task MNB-002 --dry-run          # Show prompt without calling API
    python api_executor.py --score MNB-002 --output "..."    # Score output via Haiku
    python api_executor.py --pulse                           # Full autonomous pulse
    python api_executor.py --json

Exit codes:
    0 = success
    1 = error
    2 = blocked by guardrails
    3 = failed, replanned
"""

import argparse
import json
import logging
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ORCH_DIR = Path.home() / ".claude" / "orchestrator"
sys.path.insert(0, str(ORCH_DIR))

from db import DB
from filter_pipeline import FilterPipeline, LoggingFilter, BudgetFilter, QualityGateFilter, TokenBudgetFilter
from output_guardrails import OutputGuardrailFilter
from model_router import ModelRouterFilter, route_model
from artifact_schemas import SchemaValidationFilter

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("api_exec")

PYTHON = sys.executable

# Safety pipeline — same filters as executor.py (was: BYPASSED entirely)
API_PIPELINE = FilterPipeline([
    LoggingFilter(),
    ModelRouterFilter(),
    BudgetFilter(warn_pct=80, block_pct=95),
    SchemaValidationFilter(),
    OutputGuardrailFilter(),
    QualityGateFilter(min_score=60),
    TokenBudgetFilter(),
])

# Model config (pricing per million tokens as of 2026)
MODELS = {
    "haiku": {
        "id": "claude-haiku-4-5-20251001",
        "input_cost": 0.80,   # $/M input tokens
        "output_cost": 4.00,  # $/M output tokens
        "max_tokens": 8192,
        "use_for": ["scoring", "simple", "classification"],
    },
    "sonnet": {
        "id": "claude-sonnet-4-6",
        "input_cost": 3.00,
        "output_cost": 15.00,
        "max_tokens": 16384,
        "use_for": ["standard", "default", "analysis", "content"],
    },
    "opus": {
        "id": "claude-opus-4-6",
        "input_cost": 15.00,
        "output_cost": 75.00,
        "max_tokens": 32768,
        "use_for": ["critical", "complex", "strategy", "financial"],
    },
}

# System prompts per skill category (cached across tasks)
SYSTEM_PROMPTS = {
    "dario": "You are a senior digital marketing strategist for a Portuguese agency. Deliver specific, actionable outputs. Always reference the client by name. Portuguese market context. Write in Portuguese (European) unless explicitly asked for English.",
    "seo": "You are an expert SEO consultant. Provide technically precise, data-backed recommendations. Include implementation-ready code (schema, config) where applicable. Portuguese market awareness.",
    "diva": "You are a senior architect and interior designer specializing in Portuguese construction. Reference RJUE/RGEU regulations. Use ProNIC pricing. Metric system.",
    "default": "You are a skilled professional executing a specific task. Be precise, specific to the project, and actionable.",
}

# Skill-specific system prompt overrides (richer prompts for complex skills)
SKILL_PROMPTS = {
    "dario-story-circle": (
        "You are a master brand storyteller specializing in the Story Circle framework (Dan Harmon). "
        "You create compelling origin stories that connect emotionally with target audiences. "
        "Your deliverables always include: 1) Full 8-beat Story Circle mapping, 2) About page copy (~350 words), "
        "3) Google Business Profile description (under 750 chars), 4) Social media versions (3 variations). "
        "Write in Portuguese (European). Use a sophisticated but accessible tone. "
        "When you lack specific facts about the business (founder name, year, exact address), INVENT plausible "
        "details clearly marked as [EXEMPLO] rather than leaving blanks — this gives the client a ready-to-edit "
        "draft instead of a template. Always ground the narrative in the local market and cultural context."
    ),
    "dario-offer": (
        "You are an expert in crafting irresistible offers using Alex Hormozi's Grand Slam Offer framework. "
        "Structure every offer with: Dream Outcome, Perceived Likelihood, Time to Achievement, Effort & Sacrifice. "
        "Calculate the Value Equation explicitly. Include pricing psychology, bonuses, guarantees, and urgency. "
        "Write in Portuguese (European). Be specific to the client's market and audience."
    ),
    "dario-diagnose": (
        "You are a senior business diagnostician. Analyze the company holistically across: operations, marketing, "
        "digital presence, customer journey, revenue model, team efficiency, and technology stack. "
        "Provide a scored diagnostic (0-100 per area) with specific improvement opportunities and estimated ROI. "
        "Write in Portuguese (European). Be data-driven and specific, not generic."
    ),
    "dario-brand": (
        "You are a brand strategist expert in Kapferer's Identity Prism and archetype theory. "
        "Deliver: brand positioning statement, identity prism (6 facets), primary+secondary archetypes, "
        "tone of voice guide, visual direction brief. Write in Portuguese (European). "
        "Tie everything to the client's specific market positioning and competitive landscape."
    ),
    "dario-wp-audit": (
        "You are a WordPress expert. Audit: performance (Core Web Vitals, TTFB, LCP), security (headers, "
        "updates, vulnerabilities), SEO (meta, schema, sitemap), UX (mobile, accessibility), plugin health, "
        "hosting quality. Score each area 0-100. Provide fix-by-fix action plan with priority and effort. "
        "Write in Portuguese (European)."
    ),
    "dario-sales-letter": (
        "You are an expert direct response copywriter trained in Gary Halbert, Dan Kennedy, and Eugene Schwartz. "
        "Write sales letters that convert using proven structures: AIDA, PAS (Problem-Agitate-Solve), or Star-Story-Solution. "
        "Include: magnetic headline, opening hook, problem identification, agitation, solution reveal, social proof, "
        "irresistible offer, risk reversal (guarantee), urgency/scarcity, strong CTA, and P.S. "
        "Write in Portuguese (European). Match the client's brand tone. Every sentence earns the next."
    ),
    "dario-email-seq": (
        "You are a master email marketer specializing in SOAP Opera Sequences (Russell Brunson) and nurture flows. "
        "Each email must have: compelling subject line (<50 chars), preview text, narrative hook, emotional bridge, "
        "value delivery, and clear CTA. Build tension across the sequence — each email creates desire for the next. "
        "Write in Portuguese (European). Include send timing recommendations."
    ),
    "dario-naming": (
        "You are a naming expert and brand linguist. Generate creative, memorable brand names considering: "
        "phonetics, cultural connotations (PT+EN), domain availability (.pt, .com), trademark risk, "
        "social media handle availability. Score each option 1-10 across memorability, relevance, availability, "
        "and international appeal. Write in Portuguese (European) with EN translations where relevant."
    ),
    "dario-pitch": (
        "You are an expert pitch consultant who has trained founders for TED, Shark Tank, and investor meetings. "
        "Create elevator pitches at multiple lengths (30s, 60s, 2min) with: hook, problem, solution, traction, "
        "ask. Include the one-liner formula: [Company] helps [audience] [achieve outcome] by [unique method]. "
        "Write in Portuguese (European). Be confident, data-backed, and memorable."
    ),
    "seo-schema": (
        "You are a Schema.org markup expert. Generate valid JSON-LD structured data following Google's "
        "documentation and rich results requirements. Test mental model: will this pass Google's Rich Results Test? "
        "Include all required AND recommended properties. Provide code ready to paste into <head>. "
        "Cover: LocalBusiness, Organization, WebPage, BreadcrumbList, FAQPage, Service, Review as applicable."
    ),
    "dario-funnel": (
        "You are a conversion funnel architect with expertise in AARRR metrics, customer journey mapping, "
        "and marketing automation. Design complete funnels with: channel strategy per stage, content types, "
        "conversion metrics and benchmarks, tool recommendations, automation workflows (Make/Zapier). "
        "Write in Portuguese (European). Include visual funnel diagram in ASCII/markdown."
    ),
    "dario-financial-model": (
        "You are a financial modelling expert for SMBs and service businesses. Build 12-month projections with: "
        "revenue model (units x price), fixed and variable costs, break-even analysis, cash flow, P&L summary. "
        "Use realistic benchmarks for the industry. Present in clear tables with monthly breakdown. "
        "Write in Portuguese (European). All values in EUR."
    ),
    "dario-sop": (
        "You are a process engineer and operations consultant. Create Standard Operating Procedures with: "
        "clear step numbering, responsible roles (RACI), time estimates, checklists, templates (ready to use), "
        "decision trees for exceptions. Format for easy adoption by non-technical teams. "
        "Write in Portuguese (European). Focus on practical, day-1-implementable procedures."
    ),
    # --- MARKETING BATCH ---
    "dario-ads-blueprint": (
        "You are a paid media strategist expert in Meta Ads, Google Ads, and LinkedIn Ads. "
        "Create complete ad blueprints with: campaign structure (awareness/consideration/conversion), "
        "audience targeting (demographics, interests, lookalikes, custom), ad formats per platform, "
        "copy variations (3 headlines + 3 descriptions per ad), budget allocation, bidding strategy, "
        "KPIs and benchmarks per industry. Write in Portuguese (European)."
    ),
    "dario-pipeline": (
        "You are a CRM and sales pipeline architect. Design complete sales pipelines with: "
        "stage definitions (with clear entry/exit criteria), automation triggers per stage, "
        "lead scoring model, follow-up cadences, handoff protocols between marketing and sales, "
        "tool recommendations (HubSpot/Pipedrive/Close), and reporting dashboards. "
        "Write in Portuguese (European). Include visual pipeline diagram."
    ),
    "dario-social": (
        "You are a social media strategist for premium brands. Create comprehensive social media strategies with: "
        "platform selection and justification, content pillars (3-5), posting calendar (weekly grid), "
        "content formats per platform (reels, carousels, stories, lives), hashtag strategy, "
        "engagement tactics, UGC strategy, influencer collaboration framework. "
        "Write in Portuguese (European). Include 10 ready-to-post content ideas."
    ),
    "dario-content": (
        "You are a senior content strategist specializing in authority-building content. Create content plans with: "
        "pillar content mapping, topic clusters with keyword targets, content types (blog, video, podcast, lead magnet), "
        "editorial calendar 30/60/90 days, content repurposing workflow, distribution channels, "
        "measurement framework (traffic, engagement, conversion). Write in Portuguese (European)."
    ),
    "dario-proposal": (
        "You are a business development expert who writes winning proposals. Create professional proposals with: "
        "executive summary, problem statement (client-specific), proposed solution, methodology/timeline, "
        "team and credentials, pricing (tiered options), case studies/social proof, terms and next steps. "
        "Write in Portuguese (European). Tone: confident, specific, professional."
    ),
    # --- SEO BATCH ---
    "seo-technical": (
        "You are a technical SEO specialist. Audit and provide fixes for: crawlability (robots.txt, meta robots), "
        "indexability (canonical, hreflang, noindex), site speed (Core Web Vitals, TTFB, LCP, CLS, INP), "
        "mobile optimization, JavaScript rendering, internal linking architecture, URL structure, "
        "HTTP status codes, redirect chains, structured data validation. Provide fix-priority matrix."
    ),
    "seo-content": (
        "You are an SEO content specialist. Evaluate content for: E-E-A-T signals, keyword optimization "
        "(primary, secondary, LSI), content depth and comprehensiveness, readability (Flesch-Kincaid), "
        "internal linking, featured snippet optimization, AI citation readiness, thin content detection. "
        "Provide content briefs with word count targets, heading structure, and competitor gaps."
    ),
    "seo-geo": (
        "You are a GEO (Generative Engine Optimization) and AI search specialist. Analyze and optimize for: "
        "AI crawler accessibility (GPTBot, ClaudeBot, Bingbot), llms.txt compliance, passage-level citability, "
        "brand mention signals, entity recognition, knowledge graph integration. "
        "Platform-specific optimization for Google AI Overviews, ChatGPT, Perplexity, Bing Copilot. "
        "Write in Portuguese (European) with technical terms in English."
    ),
    "seo-sitemap": (
        "You are a sitemap architecture expert. Generate and validate XML sitemaps with: "
        "proper priority and changefreq values, image sitemaps, video sitemaps, news sitemaps (if applicable), "
        "hreflang sitemaps for multilingual sites, sitemap index for large sites (>50K URLs). "
        "Include robots.txt directives and Search Console submission instructions."
    ),
    "seo-images": (
        "You are an image SEO specialist. Audit and optimize: file names (keyword-rich), alt text (descriptive, unique), "
        "image formats (WebP/AVIF conversion), lazy loading, responsive images (srcset), "
        "OG images and social preview cards, image compression ratios, CDN configuration. "
        "Provide optimized alt text for the 20 most important images. Include image sitemap XML."
    ),
    "seo-hreflang": (
        "You are an hreflang implementation expert. Generate hreflang tags for multilingual/multiregional sites: "
        "x-default handling, self-referencing tags, return tag validation, XML sitemap hreflang, "
        "HTTP header hreflang, common error detection (missing return tags, conflicting signals). "
        "Provide code ready to paste. Support PT-pt, PT-br, EN-us, EN-gb, ES patterns."
    ),
    # --- DIVA BATCH ---
    "diva-moodboard": (
        "You are a senior interior designer creating professional moodboards. Produce detailed moodboard briefs with: "
        "color palette (primary, secondary, accent with hex codes), material palette (3-5 materials with textures), "
        "furniture selection (with dimensions and price range), lighting plan (ambient, task, accent), "
        "key inspiration images description, style references, cultural context. "
        "Write in Portuguese (European). Reference Portuguese suppliers and brands where applicable."
    ),
    "diva-materials": (
        "You are a materials science expert for construction and interior design. Provide material specifications with: "
        "technical properties (resistance, durability, maintenance), Portuguese market availability and pricing, "
        "supplier recommendations (ProNIC codes where applicable), sustainability ratings, "
        "installation requirements, compatibility matrix between materials. "
        "Write in Portuguese (European). Reference Portuguese regulations (LNEC certifications)."
    ),
    "diva-floor-plan": (
        "You are an architectural space planner. Analyze and optimize floor plans considering: "
        "circulation flow, functional zoning (social, private, service), minimum dimensions (RGEU), "
        "natural light optimization, ventilation, accessibility (DL 163/2006), furniture layout. "
        "Provide before/after layout descriptions with measurements in meters. "
        "Write in Portuguese (European). Reference RGEU minimum areas."
    ),
    "diva-budget": (
        "You are a construction cost estimator for the Portuguese market. Create detailed budgets with: "
        "itemized costs per division (demolition, structure, MEP, finishes, furniture), "
        "unit prices referenced to ProNIC or CYPE, contingency allowances (10-15%), "
        "payment schedule aligned with construction phases, VAT calculations (23% or 6% reduced). "
        "Write in Portuguese (European). All prices in EUR. Include range (low/medium/high)."
    ),
    "diva-timeline": (
        "You are a construction project manager. Create detailed project timelines with: "
        "Gantt chart description (phases, durations, dependencies), critical path identification, "
        "milestone dates, permit/licensing lead times (Camara Municipal typical timelines), "
        "weather considerations for exterior work, subcontractor coordination windows. "
        "Write in Portuguese (European). Include buffer for typical Portuguese construction delays."
    ),
    "diva-licensing": (
        "You are a Portuguese building regulations expert (RJUE/RGEU/PDM). Provide licensing guidance for: "
        "type of permit required (comunicacao previa, autorizacao, licenciamento), required documents, "
        "Camara Municipal submission process, typical timelines by municipality, "
        "technical team requirements (architect, engineer), fees and taxes (TMU, TRIU). "
        "Write in Portuguese (European). Reference specific articles of RJUE (DL 555/99) and RGEU."
    ),
    # --- OPERATIONS BATCH ---
    "dario-legal": (
        "You are a business legal consultant with expertise in Portuguese commercial law. Draft and review: "
        "service contracts (prestacao de servicos), NDAs (acordos de confidencialidade), "
        "terms of service, privacy policies (RGPD/GDPR), client agreements. "
        "Include standard clauses, risk warnings, and Portuguese legal requirements. "
        "Write in Portuguese (European). Disclaimer: not a substitute for a licensed lawyer (advogado)."
    ),
    "dario-hr": (
        "You are an HR consultant specializing in Portuguese SMBs. Provide HR frameworks for: "
        "job descriptions, hiring processes, onboarding plans, performance review templates, "
        "compensation benchmarking (Portuguese market), remote work policies, team structure recommendations. "
        "Reference Portuguese labour law (Codigo do Trabalho) where applicable. "
        "Write in Portuguese (European)."
    ),
    "dario-client-onboard": (
        "You are a client success specialist. Design onboarding experiences with: "
        "welcome sequence (emails + materials), kickoff meeting agenda, expectation setting document, "
        "access provisioning checklist, 30/60/90 day success milestones, feedback collection points, "
        "escalation procedures, handoff protocols. Write in Portuguese (European). "
        "Focus on reducing time-to-value and preventing early churn."
    ),
    "dario-produto": (
        "You are a product strategist and manager. Create product strategy documents with: "
        "market analysis (TAM/SAM/SOM), competitive landscape, value proposition canvas, "
        "feature prioritization (RICE/MoSCoW), MVP definition, user personas, "
        "go-to-market strategy, pricing strategy, KPIs and success metrics. "
        "Write in Portuguese (European). Focus on Portuguese/European market context."
    ),
}


def select_model(task: dict) -> str:
    """Select optimal model based on task priority and policy."""
    policy = task.get("execution_policy", "default")
    priority = task.get("priority", "medium")

    if policy in ("critical", "financial") or priority == "critical":
        return "opus"
    elif policy == "client_facing" or priority == "high":
        return "sonnet"
    elif priority == "low":
        return "haiku"
    return "sonnet"  # default


def get_system_prompt(skill: str) -> str:
    """Get system prompt — skill-specific override first, then category fallback."""
    # Check skill-specific prompt first (richer, targeted)
    if skill in SKILL_PROMPTS:
        return SKILL_PROMPTS[skill]
    # Category fallback
    if skill.startswith("dario-") or skill.startswith("dario_"):
        return SYSTEM_PROMPTS["dario"]
    elif skill.startswith("seo"):
        return SYSTEM_PROMPTS["seo"]
    elif skill.startswith("diva-"):
        return SYSTEM_PROMPTS["diva"]
    return SYSTEM_PROMPTS["default"]


def calculate_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    """Calculate cost in USD."""
    config = MODELS.get(model, MODELS["sonnet"])
    cost = (input_tokens / 1_000_000 * config["input_cost"] +
            output_tokens / 1_000_000 * config["output_cost"])
    return round(cost, 6)


def run_engine(script: str, args: list) -> dict:
    """Run orchestrator engine."""
    path = ORCH_DIR / script
    if not path.exists():
        return {"error": f"{script} not found"}
    try:
        r = subprocess.run([PYTHON, str(path)] + args,
                           capture_output=True, text=True, timeout=30, cwd=str(ORCH_DIR))
        if r.stdout.strip():
            try:
                return json.loads(r.stdout.strip())
            except json.JSONDecodeError:
                return {"raw": r.stdout.strip()[:300]}
        return {"exit_code": r.returncode}
    except Exception as e:
        return {"error": str(e)[:200]}


# =============================================================================
# CORE: Execute task via Claude API
# =============================================================================

def execute_task(task_id: str, model_override: str = None, dry_run: bool = False) -> dict:
    """Full lifecycle: guardrails → context → prompt → API call → score → advance."""
    db = DB()
    result = {"task_id": task_id, "steps": [], "status": "pending"}

    # Load task from DB
    task = db.get_task(task_id)
    if not task:
        result["status"] = "error"
        result["error"] = "Task not found"
        return result

    skill = task.get("skill", "")
    project = task.get("project", "")

    # 0. TASK-FORMAT-SPEC-V1: Enrich + Pre-conditions
    spec_enrich = run_engine("task_spec.py", ["--enrich", task_id, "--json"])
    result["steps"].append({"step": "spec_enrich", "fields": spec_enrich.get("enriched_fields", [])})

    spec_pre = run_engine("task_spec.py", ["--check-pre", task_id, "--json"])
    if not spec_pre.get("pass", True) and spec_pre.get("blockers"):
        result["status"] = "blocked"
        result["error"] = f"Pre-conditions: {spec_pre['blockers']}"
        return result
    result["steps"].append({"step": "pre_conditions", "pass": spec_pre.get("pass", True)})

    # Reload task after enrichment (may have new fields)
    task = db.get_task(task_id)

    # 0.5. FILTER PIPELINE — BEFORE (budget, model routing, logging)
    filter_ctx = API_PIPELINE.before(task)
    result["steps"].append({
        "step": "filter_pipeline_before",
        "blocked": filter_ctx.get("blocked", False),
        "model": filter_ctx.get("recommended_model", "sonnet"),
    })
    if filter_ctx.get("blocked"):
        result["status"] = "blocked"
        result["error"] = f"Pipeline: {filter_ctx.get('block_reason', '?')}"
        return result

    # Use model router's recommendation instead of hardcoded select_model
    if not model_override:
        model_override = filter_ctx.get("recommended_model", "sonnet")

    # 1. Guardrails
    guard = run_engine("guardrails.py", ["--task", task_id, "--json"])
    verdict = guard.get("verdict", "FAIL")
    result["steps"].append({"step": "guardrails", "verdict": verdict})

    if verdict == "FAIL":
        result["status"] = "blocked"
        result["error"] = f"Guardrails: {guard.get('errors', [])}"
        return result

    # 2. Context injection
    context = run_engine("context_injector.py", ["--task", task_id, "--json"])
    context_block = context.get("context_block", "")
    result["steps"].append({"step": "context", "sources": context.get("sources_used", 0)})

    # 3. Adaptive rubric
    rubric = run_engine("adaptive_rubric.py", ["--task", task_id, "--json"])
    result["steps"].append({"step": "rubric", "dimensions": rubric.get("dimensions_count", 5)})

    # 4. Build prompt
    from executor import build_execution_prompt
    prompt = build_execution_prompt(task, context_block, rubric)

    # 5. Select model
    model = model_override or select_model(task)
    model_config = MODELS.get(model, MODELS["sonnet"])
    result["model"] = model
    result["model_id"] = model_config["id"]
    result["steps"].append({"step": "model_selected", "model": model})

    # 6. Trace start
    run_engine("tracer.py", ["--start", "--task", task_id, "--skill", skill,
                              "--worker", task.get("assignee", ""), "--project", project])

    if dry_run:
        result["status"] = "dry_run"
        result["prompt_preview"] = prompt[:500]
        result["prompt_tokens_est"] = len(prompt) // 4
        return result

    # 7. Atomic checkout
    if not db.checkout_task(task_id):
        result["status"] = "already_running"
        return result

    # 8. CALL CLAUDE API
    result["steps"].append({"step": "api_call_start"})
    api_result = call_claude_api(prompt, skill, model)
    result["steps"].append({"step": "api_call_end", "success": api_result.get("success", False)})

    if api_result.get("success"):
        output = api_result["output"]
        input_tokens = api_result["input_tokens"]
        output_tokens = api_result["output_tokens"]
        total_tokens = input_tokens + output_tokens
        cost = api_result["cost"]

        # 8.5. FILTER PIPELINE — AFTER (schema, guardrails, quality gate)
        after_ctx = {"actual_tokens": total_tokens, "quality_score": 0}
        after_result = API_PIPELINE.after(task, output, after_ctx)
        result["steps"].append({
            "step": "filter_pipeline_after",
            "tripwire": after_result.get("tripwire", False),
        })
        if after_result.get("tripwire"):
            log.warning(f"[TRIPWIRE] {task_id}: {after_result.get('tripwire_reason', '?')}")
            db.block_task(task_id, f"Tripwire: {after_result.get('tripwire_reason', '')[:200]}")
            result["status"] = "tripwire"
            result["tripwire_reason"] = after_result.get("tripwire_reason", "")
            db.log_event("api-executor", "task_tripwire", task_id=task_id,
                        details=after_result.get("tripwire_reason", "")[:200])
            return result

        # 9. Auto-score via Haiku
        score_result = auto_score_output(output, rubric, task)
        score = score_result.get("score", 0)

        result["steps"].append({"step": "scored", "score": score, "cost": cost})

        # 10. Record in quality scorer
        run_engine("quality_scorer.py", [
            "--task", task_id, "--score", str(score),
            "--skill", skill, "--project", project, "--json"
        ])

        # 11. Trace end
        run_engine("tracer.py", ["--end", "--task", task_id, "--status", "success",
                                  "--tokens", str(total_tokens), "--score", str(score),
                                  "--output", output[:200]])

        # 12. Complete task in DB
        final_status = "done" if score >= 60 else "in_review"
        db.complete_task(task_id, score=score, tokens=total_tokens,
                         output=output, status=final_status)

        # 12.5 TASK-FORMAT-SPEC-V1: Post-conditions check
        spec_post = run_engine("task_spec.py", ["--check-post", task_id, "--json"])
        result["steps"].append({"step": "post_conditions", "pass": spec_post.get("pass", True),
                                "issues": spec_post.get("issues", [])})

        # 13. Audit
        db.log_event("api-executor", "task_completed", task_id=task_id,
                     details=f"model={model} score={score} tokens={total_tokens} cost=${cost:.4f}")

        result["status"] = final_status
        result["output_preview"] = output[:300]
        result["tokens"] = {"input": input_tokens, "output": output_tokens, "total": total_tokens}
        result["cost"] = cost
        result["score"] = score

    else:
        error = api_result.get("error", "Unknown API error")

        # Trace end (failed)
        run_engine("tracer.py", ["--end", "--task", task_id, "--status", "failed",
                                  "--error", error[:200]])

        # Replan
        replan = run_engine("replanner.py", [
            "--task", task_id, "--failure", "agent_timeout", "--error", error[:200], "--json"
        ])

        result["status"] = "failed"
        result["error"] = error
        result["replan"] = replan.get("action", "escalate")

        db.log_event("api-executor", "task_failed", task_id=task_id,
                     details=f"error={error[:100]} replan={replan.get('action','?')}")

    return result


def call_claude_api(prompt: str, skill: str, model: str, retries: int = 2) -> dict:
    """Call Claude API with retry and cost tracking."""
    try:
        import anthropic
    except ImportError:
        return {"success": False, "error": "anthropic SDK not installed"}

    client = anthropic.Anthropic()
    model_config = MODELS.get(model, MODELS["sonnet"])
    system_prompt = get_system_prompt(skill)

    for attempt in range(retries + 1):
        try:
            response = client.messages.create(
                model=model_config["id"],
                max_tokens=model_config["max_tokens"],
                system=[{
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},  # Prompt caching
                }],
                messages=[{"role": "user", "content": prompt}],
            )

            output = response.content[0].text
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            cost = calculate_cost(input_tokens, output_tokens, model)

            # Check for cache hits
            cache_read = getattr(response.usage, 'cache_read_input_tokens', 0)
            cache_creation = getattr(response.usage, 'cache_creation_input_tokens', 0)

            return {
                "success": True,
                "output": output,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost": cost,
                "model": model,
                "cache_read": cache_read,
                "cache_creation": cache_creation,
            }

        except anthropic.RateLimitError:
            if attempt < retries:
                wait = 2 ** (attempt + 1)
                log.warning(f"Rate limited, retry in {wait}s (attempt {attempt+1}/{retries})")
                time.sleep(wait)
                continue
            return {"success": False, "error": "Rate limited after retries"}

        except anthropic.APIError as e:
            if attempt < retries and e.status_code >= 500:
                time.sleep(2 ** attempt)
                continue
            return {"success": False, "error": f"API error: {e.message}"}

        except Exception as e:
            return {"success": False, "error": str(e)[:300]}

    return {"success": False, "error": "Max retries exceeded"}


# =============================================================================
# AUTO-SCORING via Haiku (LLM-as-Judge)
# =============================================================================

def auto_score_output(output: str, rubric: dict, task: dict) -> dict:
    """Score task output using Haiku as judge. Cheap, fast, consistent."""
    try:
        import anthropic
    except ImportError:
        return {"score": 0, "error": "SDK not installed"}

    dimensions_text = ""
    for d in rubric.get("dimensions", []):
        dimensions_text += f"- {d.get('name')} ({d.get('weight',0):.0%}): {d.get('description','')}\n"

    threshold = rubric.get("pass_threshold", 60)

    desc = task.get('description', '')[:300]

    scoring_prompt = f"""Score this task output on a 0-100 scale.

TASK: {task.get('title', '')}
SKILL: {task.get('skill', '')}
PROJECT: {task.get('project', '')}
DESCRIPTION: {desc}

RUBRIC DIMENSIONS:
{dimensions_text}
Pass threshold: {threshold}/100

SCORING GUIDELINES — READ CAREFULLY:
1. Score RELATIVE TO THE CONTEXT PROVIDED in the task description.
   If the description only says "studio design interiores Lisboa" with no metrics, URLs, or data,
   then the output CANNOT be expected to contain site-specific audit findings.
   Score what is achievable with the context given.

2. A score of 85+ means: excellent structure, actionable, well-adapted to the client/market described.
   A score of 90+ means: could be sent to a client as-is with minimal editing.
   A score of 70 means: generic template that could apply to any business.

3. [CONFIRMAR] or [EXEMPLO] tags = PROFESSIONAL (score normally, do not penalize)
4. Invented but plausible examples adapted to the specific market = GOOD (reward specificity)
5. Generic advice that could apply to any business = BAD (penalize)

6. Weight the dimensions:
   - Structure & Format (25%): professional, tables, headings, ready to present
   - Market Specificity (25%): adapted to PT market, Lisboa, the specific sector
   - Actionability (25%): concrete next steps, not vague recommendations
   - Completeness (25%): all aspects from the description covered

OUTPUT TO SCORE:
{output[:6000]}

Respond with ONLY a JSON object:
{{"score": <0-100>, "feedback": "<one sentence>", "dimensions": {{"structure": <0-25>, "specificity": <0-25>, "actionability": <0-25>, "completeness": <0-25>}}}}"""

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=MODELS["haiku"]["id"],
            max_tokens=256,
            messages=[{"role": "user", "content": scoring_prompt}],
        )

        text = response.content[0].text.strip()
        # Extract JSON from response
        if "{" in text:
            json_str = text[text.index("{"):text.rindex("}") + 1]
            return json.loads(json_str)
        return {"score": 0, "error": "No JSON in response"}

    except Exception as e:
        log.warning(f"Auto-score failed: {e}")
        return {"score": 0, "error": str(e)[:200]}


# =============================================================================
# AUTONOMOUS PULSE — Full cycle via API
# =============================================================================

def autonomous_pulse(dry_run: bool = False, max_tasks: int = 3) -> dict:
    """Complete autonomous pulse: state → dispatch → execute wave via API."""
    db = DB()
    pulse = {"timestamp": datetime.now(timezone.utc).isoformat(), "steps": {}, "tasks_executed": []}

    # State check
    state = run_engine("state_machine.py", ["--evaluate", "--json"])
    pulse["steps"]["state"] = {"state": state.get("state"), "health": state.get("system_health")}
    if state.get("state") == "GUARDIAN":
        pulse["status"] = "guardian_stop"
        return pulse

    # Dispatch
    dispatch = run_engine("dispatch_engine.py", ["--json"])
    pulse["steps"]["dispatch"] = {"dispatched": dispatch.get("dispatched", 0)}

    # AutoDiag
    diag = run_engine("autodiag_runner.py", ["--fix", "--json"])
    pulse["steps"]["autodiag"] = {"passed": diag.get("passed", 0), "total": diag.get("total", 0)}

    # Get ready tasks
    ready = [t for t in db.get_tasks(status="todo") if t.get("assignee")]
    max_parallel = state.get("max_parallel", 3)
    wave = ready[:min(max_parallel, max_tasks)]

    pulse["steps"]["wave_size"] = len(wave)

    # Execute each task via API
    for task in wave:
        task_result = execute_task(task["id"], dry_run=dry_run)
        pulse["tasks_executed"].append({
            "task_id": task["id"],
            "status": task_result.get("status"),
            "score": task_result.get("score"),
            "tokens": task_result.get("tokens", {}).get("total"),
            "cost": task_result.get("cost"),
            "model": task_result.get("model"),
        })

    # Budget summary
    pulse["steps"]["budget"] = db.get_budget()

    # Total cost
    total_cost = sum(t.get("cost", 0) or 0 for t in pulse["tasks_executed"])
    total_tokens = sum((t.get("tokens") or 0) for t in pulse["tasks_executed"])
    pulse["totals"] = {"tasks": len(wave), "tokens": total_tokens, "cost": round(total_cost, 4)}

    pulse["status"] = "ok"

    db.log_event("api-executor", "autonomous_pulse",
                 details=f"tasks={len(wave)} tokens={total_tokens} cost=${total_cost:.4f}")

    return pulse


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="DARIO API Executor — Direct Claude API execution")
    parser.add_argument("--task", "-t", help="Execute single task via API")
    parser.add_argument("--model", "-m", choices=["haiku", "sonnet", "opus"], help="Force model")
    parser.add_argument("--pulse", action="store_true", help="Autonomous pulse (dispatch + execute wave)")
    parser.add_argument("--max-tasks", type=int, default=3, help="Max tasks per pulse")
    parser.add_argument("--dry-run", "-n", action="store_true", help="Show without calling API")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")

    args = parser.parse_args()
    if args.json:
        logging.getLogger().setLevel(logging.ERROR)

    if args.task:
        result = execute_task(args.task, model_override=args.model, dry_run=args.dry_run)
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print(f"=== EXECUTE: {args.task} → {result['status']} ===\n")
            for s in result.get("steps", []):
                print(f"  [{s.get('step')}] {s}")
            if result.get("score"):
                print(f"\n  Score: {result['score']}/100 | Cost: ${result.get('cost',0):.4f} | Model: {result.get('model')}")
            if result.get("prompt_preview"):
                print(f"\n  Prompt: {result['prompt_preview'][:200]}...")
        return 0 if result["status"] in ("done", "dry_run") else 2 if result["status"] == "blocked" else 3

    elif args.pulse:
        result = autonomous_pulse(dry_run=args.dry_run, max_tasks=args.max_tasks)
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print(f"=== AUTONOMOUS PULSE ({result.get('status')}) ===\n")
            for name, data in result.get("steps", {}).items():
                print(f"  {name}: {data}")
            print(f"\n  Tasks executed: {len(result.get('tasks_executed', []))}")
            for t in result.get("tasks_executed", []):
                print(f"    [{t.get('status')}] {t['task_id']} — score={t.get('score')} model={t.get('model')} cost=${t.get('cost',0)}")
            totals = result.get("totals", {})
            print(f"\n  Totals: {totals.get('tasks',0)} tasks, {totals.get('tokens',0)} tokens, ${totals.get('cost',0):.4f}")
        return 0

    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
