"""Claude Code hook integration endpoints."""
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter

from .. import database
from ..models import HookEvent
from ..services.fitness import calculate_fitness
from ..services.task_sync import sync_tasks
from ..services.mutation_engine import apply_synaptic_reinforcement, reset_session_counter

router = APIRouter(prefix="/hooks")
logger = logging.getLogger(__name__)


@router.post("/session-start")
async def session_start(event: HookEvent):
    reset_session_counter()  # Reset mutation limit for new session
    async with database.pool.connection() as conn:
        await conn.execute("""
            INSERT INTO orch.audit_log (event_code, severity, session_id, details)
            VALUES ('DARIO_SESSION_START', 'info', %s, '{}')
        """, (event.session_id,))
        await conn.commit()
    # Sync tasks on session start
    count = await sync_tasks()
    return {"ok": True, "tasks_synced": count}


@router.post("/session-end")
async def session_end(event: HookEvent):
    # Calculate fitness at session end
    fitness = await calculate_fitness()
    async with database.pool.connection() as conn:
        await conn.execute("""
            INSERT INTO orch.audit_log (event_code, severity, session_id, details)
            VALUES ('DARIO_SESSION_END', 'info', %s, %s)
        """, (event.session_id, f'{{"fitness": {fitness}}}'))
        await conn.commit()
    return {"ok": True, "fitness": fitness}


@router.post("/task-complete")
async def task_complete(event: HookEvent):
    """Record task completion — the micro-evolution trigger."""
    if not event.skill:
        return {"ok": False, "error": "skill required"}

    # Record quality score if provided
    if event.quality_score is not None:
        weights = {"S": 0.25, "A": 0.20, "C": 0.20, "Ac": 0.25, "T": 0.10}
        async with database.pool.connection() as conn:
            await conn.execute("""
                INSERT INTO orch.quality_scores (task_id, skill, composite_score, weights_used, confidence_mode)
                VALUES (%s, %s, %s, %s, %s)
            """, (event.task_id, event.skill, event.quality_score, json.dumps(weights), event.session_id))

            # Update task quality_score
            if event.task_id:
                await conn.execute(
                    "UPDATE orch.tasks SET quality_score = %s, completed_at = NOW() WHERE id = %s",
                    (event.quality_score, event.task_id)
                )

            # Increment total completed
            await conn.execute("UPDATE orch.operational_state SET total_tasks_completed = total_tasks_completed + 1 WHERE id = 1")

            # Record tokens if provided
            if event.tokens_used:
                month = datetime.now(timezone.utc).strftime("%Y-%m")
                await conn.execute("""
                    INSERT INTO orch.budget_monthly (month, total_tokens, token_limit)
                    VALUES (%s, %s, 50000000)
                    ON CONFLICT (month) DO UPDATE SET
                        total_tokens = orch.budget_monthly.total_tokens + EXCLUDED.total_tokens,
                        percentage = (orch.budget_monthly.total_tokens + EXCLUDED.total_tokens)::float / orch.budget_monthly.token_limit * 100,
                        updated_at = NOW()
                """, (month, event.tokens_used))

            await conn.execute("""
                INSERT INTO orch.audit_log (event_code, severity, entity_type, entity_id, details)
                VALUES ('DARIO_TASK_COMPLETE', 'info', 'task', %s, %s)
            """, (event.task_id, f'{{"skill": "{event.skill}", "score": {event.quality_score or 0}}}'))
            await conn.commit()

    return {"ok": True, "task_id": event.task_id, "score": event.quality_score}
