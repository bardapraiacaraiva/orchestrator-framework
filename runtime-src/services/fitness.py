"""Calculate and record the system fitness metric."""
import logging
from datetime import datetime, timezone

from .. import database

logger = logging.getLogger(__name__)


async def calculate_fitness() -> float:
    """fitness = avg_quality_norm * (1 - budget_ratio) * task_velocity"""
    async with database.pool.connection() as conn:
        # Avg quality of last 10 scores (0-100 → 0-1)
        row = await conn.execute(
            "SELECT AVG(composite_score) FROM (SELECT composite_score FROM orch.quality_scores ORDER BY scored_at DESC LIMIT 10) sub"
        )
        result = await row.fetchone()
        avg_quality = (result[0] or 70.0) / 100.0

        # Budget ratio (0-1, lower is better)
        row = await conn.execute(
            "SELECT percentage FROM orch.budget_monthly WHERE month = TO_CHAR(NOW(), 'YYYY-MM')"
        )
        result = await row.fetchone()
        budget_ratio = (result[0] or 0.0) / 100.0

        # Task velocity (completed this month / 30 as baseline target)
        row = await conn.execute(
            "SELECT COUNT(*) FROM orch.tasks WHERE status = 'done' AND completed_at >= DATE_TRUNC('month', NOW())"
        )
        result = await row.fetchone()
        tasks_done = result[0] or 0
        velocity = min(tasks_done / 30.0, 1.0)  # cap at 1.0

    fitness = avg_quality * (1.0 - budget_ratio) * max(velocity, 0.1)  # floor velocity at 0.1
    fitness = round(fitness, 4)

    # Record to history
    async with database.pool.connection() as conn:
        row = await conn.execute("SELECT generation FROM orch.operational_state WHERE id = 1")
        gen_row = await row.fetchone()
        generation = gen_row[0] if gen_row else 1

        await conn.execute("""
            INSERT INTO orch.fitness_history (fitness_score, avg_quality, budget_ratio, task_velocity, generation)
            VALUES (%s, %s, %s, %s, %s)
        """, (fitness, avg_quality, budget_ratio, velocity, generation))

        # Update operational state
        await conn.execute("""
            UPDATE orch.operational_state SET fitness_score = %s, updated_at = NOW() WHERE id = 1
        """, (fitness,))
        await conn.commit()

    logger.info("Fitness calculated: %.4f (quality=%.2f, budget=%.2f, velocity=%.2f)", fitness, avg_quality, budget_ratio, velocity)
    return fitness


async def get_fitness_trend(limit: int = 20) -> list[dict]:
    async with database.pool.connection() as conn:
        rows = await conn.execute(
            "SELECT fitness_score, avg_quality, budget_ratio, task_velocity, generation, measured_at FROM orch.fitness_history ORDER BY measured_at DESC LIMIT %s",
            (limit,)
        )
        results = await rows.fetchall()
    return [
        {"fitness": r[0], "avg_quality": r[1], "budget_ratio": r[2], "velocity": r[3], "generation": r[4], "measured_at": r[5].isoformat()}
        for r in reversed(results)
    ]
