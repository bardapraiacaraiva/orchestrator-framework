"""DARIO Orchestrator Runtime — Self-Evolving AI Agent OS."""
import asyncio
import logging
import logging.handlers
import sys
from contextlib import asynccontextmanager

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Fix Windows event loop for psycopg3 async
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from .config import settings
from .database import init_pool, close_pool, run_migrations
from .routers import health, hooks, evolution, dashboard, tasks, budget, weights
from .services.task_sync import sync_tasks
from .services.fitness import calculate_fitness
from .services.state_machine import check_transitions
from .services.autodiag import run_autodiag
from .services.crystallizer import analyze_session_patterns, detect_and_crystallize
from .services.weekly_evolution import run_weekly_evolution

import os
_log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
os.makedirs(_log_dir, exist_ok=True)
_log_file = os.path.join(_log_dir, "dario-orch.log")

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.handlers.RotatingFileHandler(_log_file, maxBytes=5_000_000, backupCount=3, encoding="utf-8"),
    ],
)
logger = logging.getLogger("dario-orch")

scheduler = AsyncIOScheduler()


async def micro_pulse():
    """Every 5 minutes: sync tasks, recalculate health, check transitions, autodiag."""
    try:
        await sync_tasks()
        await check_transitions()
        diag = await run_autodiag()
        if diag["warnings"] or diag["failures"]:
            logger.warning("AutoDiag: %d warnings, %d failures", diag["warnings"], diag["failures"])
    except Exception as e:
        logger.error("Micro pulse failed: %s", e)


async def session_pulse():
    """Every 30 minutes: calculate fitness, analyze patterns, crystallize."""
    try:
        await sync_tasks()
        fitness = await calculate_fitness()
        await check_transitions()
        patterns = await analyze_session_patterns()
        crystal = await detect_and_crystallize()
        logger.info("Session pulse — fitness: %.4f, patterns: %d, crystallized: %d",
                    fitness, patterns, crystal["crystallized"])
    except Exception as e:
        logger.error("Session pulse failed: %s", e)


async def weekly_pulse():
    """Sundays at 03:00: full evolution cycle."""
    try:
        result = await run_weekly_evolution()
        logger.info("Weekly evolution complete — Gen %s", result.get("generation_incremented"))
    except Exception as e:
        logger.error("Weekly pulse failed: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_pool()
    await run_migrations()
    await sync_tasks()
    await calculate_fitness()

    # Schedule pulses
    scheduler.add_job(micro_pulse, "interval", seconds=settings.micro_pulse_seconds, id="micro_pulse")
    scheduler.add_job(session_pulse, "interval", seconds=settings.session_pulse_seconds, id="session_pulse")
    scheduler.add_job(weekly_pulse, "cron", day_of_week="sun", hour=3, minute=0, id="weekly_pulse")
    scheduler.start()
    logger.info("DARIO Orchestrator Runtime started on port %d", settings.orch_port)
    logger.info("Scheduler running: micro=%ds, session=%ds", settings.micro_pulse_seconds, settings.session_pulse_seconds)

    yield

    # Shutdown
    scheduler.shutdown()
    await close_pool()
    logger.info("DARIO Orchestrator Runtime stopped")


app = FastAPI(
    title="DARIO Orchestrator Runtime",
    version="1.0.0",
    description="Self-Evolving AI Agent OS — Real-time metrics, state machine, evolution engine.",
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Register routers
app.include_router(health.router)
app.include_router(tasks.router)
app.include_router(hooks.router)
app.include_router(evolution.router)
app.include_router(budget.router)
app.include_router(weights.router)
app.include_router(dashboard.router)


if __name__ == "__main__":
    uvicorn.run("src.main:app", host=settings.orch_host, port=settings.orch_port, reload=False, loop="asyncio")
