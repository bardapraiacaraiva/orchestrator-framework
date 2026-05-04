"""Evolution engine endpoints."""
from fastapi import APIRouter

from .. import database
from ..services.fitness import calculate_fitness, get_fitness_trend
from ..services.state_machine import get_state

router = APIRouter(prefix="/evolution")


@router.get("")
async def evolution_status():
    state = await get_state()
    async with database.pool.connection() as conn:
        row = await conn.execute("SELECT COUNT(*) FROM orch.mutations WHERE status = 'applied'")
        r = await row.fetchone()
        mutations_applied = r[0]

        row = await conn.execute("SELECT COUNT(*) FROM orch.mutations WHERE status = 'reverted'")
        r = await row.fetchone()
        mutations_reverted = r[0]

        row = await conn.execute("SELECT COUNT(*) FROM orch.patterns WHERE crystallized = TRUE")
        r = await row.fetchone()
        patterns_crystallized = r[0]

        row = await conn.execute("SELECT COUNT(*) FROM orch.quality_scores")
        r = await row.fetchone()
        total_scores = r[0]

    trend = await get_fitness_trend(10)

    return {
        "generation": state["generation"],
        "fitness_score": state["fitness_score"],
        "mutations_applied": mutations_applied,
        "mutations_reverted": mutations_reverted,
        "patterns_crystallized": patterns_crystallized,
        "total_quality_scores": total_scores,
        "fitness_trend": trend,
        "state": state["state"],
        "autonomy": state["autonomy_level"],
    }


@router.get("/fitness")
async def fitness_history():
    trend = await get_fitness_trend(50)
    return {"entries": trend, "count": len(trend)}


@router.get("/journal")
async def journal(limit: int = 20):
    async with database.pool.connection() as conn:
        rows = await conn.execute(
            "SELECT id, session_id, pulse_type, tasks_completed, avg_quality, evolutionary_delta, generation, recorded_at FROM orch.evolution_journal ORDER BY recorded_at DESC LIMIT %s",
            (limit,)
        )
        results = await rows.fetchall()
    return [
        {"id": r[0], "session_id": r[1], "pulse_type": r[2], "tasks_completed": r[3],
         "avg_quality": r[4], "delta": r[5], "generation": r[6], "recorded_at": r[7].isoformat()}
        for r in results
    ]


@router.post("/pulse/{pulse_type}")
async def trigger_pulse(pulse_type: str):
    """Manually trigger an evolution pulse."""
    if pulse_type not in ("micro", "session", "weekly"):
        return {"error": "Invalid pulse type. Use: micro, session, weekly"}

    from ..services.task_sync import sync_tasks
    from ..services.state_machine import check_transitions
    from ..services.crystallizer import analyze_session_patterns, detect_and_crystallize
    from ..services.weekly_evolution import run_weekly_evolution

    if pulse_type == "weekly":
        result = await run_weekly_evolution()
        return {"ok": True, "pulse_type": "weekly", "result": result}

    count = await sync_tasks()
    fitness = await calculate_fitness()
    await check_transitions()

    crystal_result = None
    if pulse_type == "session":
        patterns = await analyze_session_patterns()
        crystal_result = await detect_and_crystallize()

    # Record journal entry
    state = await get_state()
    async with database.pool.connection() as conn:
        await conn.execute("""
            INSERT INTO orch.evolution_journal (pulse_type, tasks_completed, avg_quality, generation)
            VALUES (%s, 0, %s, %s)
        """, (pulse_type, fitness * 100, state["generation"]))

        await conn.execute(
            "UPDATE orch.operational_state SET last_pulse = NOW() WHERE id = 1"
        )
        await conn.commit()

    return {
        "ok": True, "pulse_type": pulse_type, "fitness": fitness,
        "tasks_synced": count, "state": state["state"],
        "crystallized": crystal_result["crystallized"] if crystal_result else 0,
    }


@router.get("/patterns")
async def list_patterns():
    async with database.pool.connection() as conn:
        rows = await conn.execute(
            "SELECT id, pattern_type, description, occurrences, threshold, crystallized, rule_applied, first_seen, last_seen FROM orch.patterns ORDER BY occurrences DESC LIMIT 50"
        )
        results = await rows.fetchall()
    return [
        {"id": r[0], "type": r[1], "description": r[2], "occurrences": r[3],
         "threshold": r[4], "crystallized": r[5], "rule": r[6],
         "first_seen": r[7].isoformat(), "last_seen": r[8].isoformat()}
        for r in results
    ]


@router.get("/mutations")
async def list_mutations(limit: int = 20):
    async with database.pool.connection() as conn:
        rows = await conn.execute(
            "SELECT id, generation, file_mutated, field_changed, old_value, new_value, reason, status, fitness_before, fitness_after, applied_at FROM orch.mutations ORDER BY applied_at DESC LIMIT %s",
            (limit,)
        )
        results = await rows.fetchall()
    return [
        {"id": r[0], "generation": r[1], "file": r[2], "field": r[3],
         "old": r[4], "new": r[5], "reason": r[6], "status": r[7],
         "fitness_before": r[8], "fitness_after": r[9],
         "applied_at": r[10].isoformat()}
        for r in results
    ]
