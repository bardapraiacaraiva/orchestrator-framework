"""Operational state machine with automatic transitions."""
import logging

from .. import database

logger = logging.getLogger(__name__)

VALID_STATES = {"ACTIVE", "REFLECTIVE_PAUSE", "GUARDIAN", "EXPANSION"}
VALID_AUTONOMY = {"P-A1", "P-A2", "P-A3", "P-A4"}


async def get_state() -> dict:
    async with database.pool.connection() as conn:
        row = await conn.execute("SELECT state, autonomy_level, system_health, fitness_score, max_parallel, generation, total_tasks_completed, last_pulse, started_at FROM orch.operational_state WHERE id = 1")
        r = await row.fetchone()
    if not r:
        return {"state": "ACTIVE", "autonomy_level": "P-A1", "system_health": 0.85}
    return {
        "state": r[0], "autonomy_level": r[1], "system_health": r[2],
        "fitness_score": r[3], "max_parallel": r[4], "generation": r[5],
        "total_tasks_completed": r[6], "last_pulse": r[7], "started_at": r[8],
    }


async def check_transitions():
    """Evaluate state transitions and autonomy level based on current metrics."""
    state_data = await get_state()
    current = state_data["state"]
    health = state_data["system_health"]

    # Get recent quality avg
    async with database.pool.connection() as conn:
        row = await conn.execute("SELECT AVG(composite_score) FROM (SELECT composite_score FROM orch.quality_scores ORDER BY scored_at DESC LIMIT 3) sub")
        r = await row.fetchone()
        avg_quality_last_3 = r[0] or 70.0

        row = await conn.execute("SELECT AVG(composite_score) FROM (SELECT composite_score FROM orch.quality_scores ORDER BY scored_at DESC LIMIT 10) sub")
        r = await row.fetchone()
        avg_quality_last_10 = r[0] or 70.0

        row = await conn.execute("SELECT AVG(composite_score) FROM (SELECT composite_score FROM orch.quality_scores ORDER BY scored_at DESC LIMIT 20) sub")
        r = await row.fetchone()
        avg_quality_last_20 = r[0] or 70.0

        row = await conn.execute("SELECT COUNT(*) FROM orch.quality_scores")
        r = await row.fetchone()
        total_scores = r[0] or 0

        row = await conn.execute("SELECT percentage FROM orch.budget_monthly WHERE month = TO_CHAR(NOW(), 'YYYY-MM')")
        r = await row.fetchone()
        budget_pct = r[0] or 0.0

        # Evolutionary delta
        row = await conn.execute("SELECT AVG(composite_score) FROM (SELECT composite_score FROM orch.quality_scores ORDER BY scored_at DESC LIMIT 10 OFFSET 10) sub")
        r = await row.fetchone()
        prev_10 = r[0] or avg_quality_last_10
        evo_delta = avg_quality_last_10 - prev_10

        # Guardian triggers in last 30 days
        row = await conn.execute("SELECT COUNT(*) FROM orch.audit_log WHERE event_code LIKE '%GUARDIAN%' AND recorded_at > NOW() - INTERVAL '30 days'")
        r = await row.fetchone()
        guardian_triggers_30d = r[0] or 0

    # --- State transitions ---
    new_state = current

    if current == "ACTIVE":
        if avg_quality_last_3 < 60:
            new_state = "REFLECTIVE_PAUSE"
            logger.warning("Quality regression detected (avg=%.1f) → REFLECTIVE_PAUSE", avg_quality_last_3)
        elif health < 0.50:
            new_state = "GUARDIAN"
            logger.critical("System health critical (%.2f) → GUARDIAN", health)
        elif budget_pct >= 95:
            new_state = "GUARDIAN"
            logger.critical("Budget critical (%.1f%%) → GUARDIAN", budget_pct)

    elif current == "REFLECTIVE_PAUSE":
        if health >= 0.85 and avg_quality_last_3 >= 70:
            new_state = "ACTIVE"
            logger.info("Recovery confirmed → ACTIVE")
        elif health < 0.50:
            new_state = "GUARDIAN"

    if new_state != current:
        await _transition(current, new_state)

    # --- Autonomy Ladder calculation ---
    new_autonomy = "P-A1"  # Default: supervised

    if (health >= 0.90 and total_scores >= 50 and avg_quality_last_20 >= 85
            and evo_delta > 0 and guardian_triggers_30d == 0):
        new_autonomy = "P-A4"  # Full autonomy
    elif health >= 0.85 and total_scores >= 20 and avg_quality_last_20 >= 80 and evo_delta > 0:
        new_autonomy = "P-A3"  # Autonomous
    elif health >= 0.70 and total_scores >= 10 and avg_quality_last_10 >= 70:
        new_autonomy = "P-A2"  # Guided
    # else P-A1 (supervised)

    # Demotion override
    if new_state == "GUARDIAN":
        new_autonomy = "P-A1"
    elif new_state == "REFLECTIVE_PAUSE" and new_autonomy in ("P-A3", "P-A4"):
        new_autonomy = "P-A2"

    # Update state
    async with database.pool.connection() as conn:
        new_health = avg_quality_last_3 / 100.0
        await conn.execute("""
            UPDATE orch.operational_state
            SET system_health = %s, autonomy_level = %s, updated_at = NOW()
            WHERE id = 1
        """, (round(new_health, 3), new_autonomy))
        await conn.commit()

    if new_autonomy != state_data["autonomy_level"]:
        logger.info("Autonomy level: %s → %s", state_data["autonomy_level"], new_autonomy)


async def _transition(from_state: str, to_state: str):
    async with database.pool.connection() as conn:
        await conn.execute(
            "UPDATE orch.operational_state SET state = %s, last_state_change = NOW(), updated_at = NOW() WHERE id = 1",
            (to_state,)
        )
        await conn.execute("""
            INSERT INTO orch.audit_log (event_code, severity, entity_type, entity_id, details)
            VALUES (%s, %s, 'state', 'operational_state', %s)
        """, (
            f"DARIO_STATE_{from_state}_TO_{to_state}",
            "critical" if to_state == "GUARDIAN" else "warning",
            f'{{"from": "{from_state}", "to": "{to_state}"}}',
        ))
        await conn.commit()
    logger.info("State transition: %s → %s", from_state, to_state)
