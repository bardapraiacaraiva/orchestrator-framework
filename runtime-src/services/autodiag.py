"""AutoDiag — Real diagnostic checks against the database.
Runs silently on every micro pulse. Reports only problems.
"""
import logging
from datetime import datetime, timezone, timedelta

from .. import database

logger = logging.getLogger(__name__)


async def run_autodiag() -> dict:
    """Run all diagnostic checks. Returns summary."""
    results = {
        "checks_run": 0,
        "warnings": 0,
        "failures": 0,
        "details": [],
    }

    checks = [
        _check_stale_tasks,
        _check_budget_drift,
        _check_quality_regression,
        _check_orphan_tasks,
    ]

    for check in checks:
        try:
            result = await check()
            results["checks_run"] += 1
            if result["status"] == "warn":
                results["warnings"] += 1
                results["details"].append(result)
            elif result["status"] == "fail":
                results["failures"] += 1
                results["details"].append(result)
        except Exception as e:
            logger.error("AutoDiag check %s failed: %s", check.__name__, e)

    # Log result
    if results["warnings"] == 0 and results["failures"] == 0:
        await _log_event("DARIO_AUTODIAG_OK", "info")
    elif results["failures"] > 0:
        await _log_event(f"DARIO_AUTODIAG_FAIL_{results['failures']}_issues", "critical")
    else:
        await _log_event(f"DARIO_AUTODIAG_WARN_{results['warnings']}_issues", "warning")

    return results


async def _check_stale_tasks() -> dict:
    """Tasks in_progress for more than 24h without update."""
    threshold = datetime.now(timezone.utc) - timedelta(hours=24)
    async with database.pool.connection() as conn:
        row = await conn.execute(
            "SELECT COUNT(*) FROM orch.tasks WHERE status = 'in_progress' AND updated_at < %s",
            (threshold,)
        )
        r = await row.fetchone()
        count = r[0]

    if count > 0:
        return {"check": "stale_tasks", "status": "warn", "message": f"{count} tasks stale (>24h in_progress)"}
    return {"check": "stale_tasks", "status": "ok"}


async def _check_budget_drift() -> dict:
    """Budget percentage above warning threshold."""
    async with database.pool.connection() as conn:
        row = await conn.execute(
            "SELECT percentage FROM orch.budget_monthly WHERE month = TO_CHAR(NOW(), 'YYYY-MM')"
        )
        r = await row.fetchone()
        pct = r[0] if r else 0.0

    if pct >= 95:
        return {"check": "budget", "status": "fail", "message": f"Budget CRITICAL: {pct:.1f}%"}
    elif pct >= 80:
        return {"check": "budget", "status": "warn", "message": f"Budget WARNING: {pct:.1f}%"}
    return {"check": "budget", "status": "ok"}


async def _check_quality_regression() -> dict:
    """Avg quality of last 5 tasks vs previous 5 — detect regression."""
    async with database.pool.connection() as conn:
        # Last 5
        row = await conn.execute(
            "SELECT AVG(composite_score) FROM (SELECT composite_score FROM orch.quality_scores ORDER BY scored_at DESC LIMIT 5) sub"
        )
        r = await row.fetchone()
        last_5 = r[0] or 0

        # Previous 5 (offset 5)
        row = await conn.execute(
            "SELECT AVG(composite_score) FROM (SELECT composite_score FROM orch.quality_scores ORDER BY scored_at DESC LIMIT 5 OFFSET 5) sub"
        )
        r = await row.fetchone()
        prev_5 = r[0] or 0

    if prev_5 > 0:
        delta = last_5 - prev_5
        if delta < -15:
            return {"check": "quality_regression", "status": "fail", "message": f"Quality dropped {delta:.1f} points (last 5 avg: {last_5:.1f})"}
        elif delta < -5:
            return {"check": "quality_regression", "status": "warn", "message": f"Quality dip: {delta:.1f} points"}
    return {"check": "quality_regression", "status": "ok"}


async def _check_orphan_tasks() -> dict:
    """Tasks with depends_on referencing non-existent tasks."""
    async with database.pool.connection() as conn:
        # Get all task IDs
        row = await conn.execute("SELECT id FROM orch.tasks")
        all_ids = {r[0] for r in await row.fetchall()}

        # Get tasks with dependencies
        row = await conn.execute("SELECT id, depends_on FROM orch.tasks WHERE depends_on IS NOT NULL AND array_length(depends_on, 1) > 0")
        orphans = 0
        for r in await row.fetchall():
            deps = r[1] or []
            for dep in deps:
                if dep not in all_ids:
                    orphans += 1

    if orphans > 0:
        return {"check": "orphan_deps", "status": "warn", "message": f"{orphans} broken dependency references"}
    return {"check": "orphan_deps", "status": "ok"}


async def _log_event(event_code: str, severity: str):
    async with database.pool.connection() as conn:
        await conn.execute("""
            INSERT INTO orch.audit_log (event_code, severity, entity_type)
            VALUES (%s, %s, 'system')
        """, (event_code, severity))
        await conn.commit()
