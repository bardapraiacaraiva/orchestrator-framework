"""Weekly Evolution Pulse — Full evolution cycle.
Runs on Sundays or when triggered manually.
Checkpoints, fitness review, mutation survival, pruning, generation increment.
"""
import json
import logging
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path

from ruamel.yaml import YAML

from .. import database
from ..config import settings
from .fitness import calculate_fitness
from .crystallizer import detect_and_crystallize, analyze_session_patterns

logger = logging.getLogger(__name__)
yaml_rt = YAML()


async def run_weekly_evolution() -> dict:
    """Full weekly evolution cycle."""
    result = {
        "checkpoint_created": False,
        "fitness_review": None,
        "mutations_survived": 0,
        "mutations_reverted": 0,
        "patterns_crystallized": 0,
        "generation_incremented": False,
        "pruned": 0,
    }

    # Step 1: Checkpoint
    result["checkpoint_created"] = await _create_checkpoint()

    # Step 2: Fitness review vs 4-week baseline
    result["fitness_review"] = await _fitness_review()

    # Step 3: Mutation survival check
    survived, reverted = await _check_mutation_survival()
    result["mutations_survived"] = survived
    result["mutations_reverted"] = reverted

    # Step 4: Pattern analysis + crystallization
    await analyze_session_patterns()
    crystal = await detect_and_crystallize()
    result["patterns_crystallized"] = crystal["crystallized"]

    # Step 5: Prune dead patterns
    result["pruned"] = await _prune_dead()

    # Step 6: Increment generation
    await _increment_generation()
    result["generation_incremented"] = True

    # Step 7: Log
    async with database.pool.connection() as conn:
        await conn.execute("""
            INSERT INTO orch.audit_log (event_code, severity, entity_type, details)
            VALUES ('DARIO_WEEKLY_EVOLUTION', 'info', 'system', %s)
        """, (json.dumps(result, default=str),))

        await conn.execute("""
            INSERT INTO orch.evolution_journal (pulse_type, generation, patterns_detected)
            VALUES ('weekly', (SELECT generation FROM orch.operational_state WHERE id = 1), %s)
        """, (json.dumps(result, default=str),))
        await conn.commit()

    logger.info("WEEKLY EVOLUTION COMPLETE: %s", json.dumps(result, default=str))
    return result


async def _create_checkpoint() -> bool:
    """Snapshot all mutable YAML files."""
    checkpoint_dir = settings.orchestrator_path / "evolution" / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ckpt_path = checkpoint_dir / f"ckpt_{date_str}"
    ckpt_path.mkdir(exist_ok=True)

    mutable_files = [
        "synaptic_weights.yaml",
        "composite_modes.yaml",
        "autodiag.yaml",
        "operational_states.yaml",
        "fallback_matrix.yaml",
    ]

    copied = 0
    for fname in mutable_files:
        src = settings.orchestrator_path / fname
        if src.exists():
            shutil.copy2(src, ckpt_path / fname)
            copied += 1

    logger.info("Checkpoint created: %s (%d files)", ckpt_path, copied)

    # Keep only last 8 checkpoints
    all_ckpts = sorted(checkpoint_dir.glob("ckpt_*"))
    while len(all_ckpts) > 8:
        shutil.rmtree(all_ckpts.pop(0))

    return copied > 0


async def _fitness_review() -> dict:
    """Compare current fitness vs 4-week baseline."""
    async with database.pool.connection() as conn:
        # Current fitness
        row = await conn.execute(
            "SELECT fitness_score FROM orch.fitness_history ORDER BY measured_at DESC LIMIT 1"
        )
        r = await row.fetchone()
        current = r[0] if r else 0.0

        # 4-week ago fitness
        four_weeks_ago = datetime.now(timezone.utc) - timedelta(weeks=4)
        row = await conn.execute(
            "SELECT fitness_score FROM orch.fitness_history WHERE measured_at <= %s ORDER BY measured_at DESC LIMIT 1",
            (four_weeks_ago,)
        )
        r = await row.fetchone()
        baseline = r[0] if r else current  # If no baseline, use current (no rollback)

    delta_pct = ((current - baseline) / max(baseline, 0.01)) * 100

    review = {
        "current_fitness": round(current, 4),
        "baseline_fitness": round(baseline, 4),
        "delta_pct": round(delta_pct, 1),
        "action": "none",
    }

    if delta_pct < -15:
        review["action"] = "FULL_ROLLBACK"
        logger.critical("FITNESS REGRESSION >15%% (%.1f%%) — ROLLBACK TRIGGERED", delta_pct)
        await _full_rollback()
    elif delta_pct < -5:
        review["action"] = "warning"
        logger.warning("Fitness declining: %.1f%%", delta_pct)

    return review


async def _full_rollback():
    """Restore last checkpoint YAMLs."""
    checkpoint_dir = settings.orchestrator_path / "evolution" / "checkpoints"
    all_ckpts = sorted(checkpoint_dir.glob("ckpt_*"))

    if len(all_ckpts) < 2:
        logger.error("Cannot rollback — not enough checkpoints")
        return

    # Use second-to-last (last is current state, we want previous)
    restore_from = all_ckpts[-2]
    logger.warning("ROLLING BACK to checkpoint: %s", restore_from.name)

    for f in restore_from.glob("*.yaml"):
        dest = settings.orchestrator_path / f.name
        shutil.copy2(f, dest)
        logger.info("Restored: %s", f.name)

    # Mark all recent mutations as reverted
    async with database.pool.connection() as conn:
        await conn.execute(
            "UPDATE orch.mutations SET status = 'reverted', evaluated_at = NOW() WHERE status = 'applied'"
        )
        await conn.execute("""
            INSERT INTO orch.audit_log (event_code, severity, entity_type, details)
            VALUES ('DARIO_FULL_ROLLBACK', 'critical', 'system', '{"reason": "fitness_regression_gt_15pct"}')
        """)
        await conn.commit()


async def _check_mutation_survival() -> tuple[int, int]:
    """Evaluate mutations: survived or reverted based on fitness impact."""
    survived = 0
    reverted = 0

    async with database.pool.connection() as conn:
        # Get mutations that have had 10+ tasks since applied and haven't been evaluated
        rows = await conn.execute("""
            SELECT id, fitness_before FROM orch.mutations
            WHERE status = 'applied' AND tasks_since_applied >= 10 AND evaluated_at IS NULL
        """)
        pending = await rows.fetchall()

        if not pending:
            return 0, 0

        # Get current fitness
        row = await conn.execute("SELECT fitness_score FROM orch.operational_state WHERE id = 1")
        r = await row.fetchone()
        current_fitness = r[0] if r else 0.0

        for mut_id, fitness_before in pending:
            if fitness_before is None:
                # Can't evaluate without baseline
                await conn.execute(
                    "UPDATE orch.mutations SET status = 'survived', evaluated_at = NOW(), fitness_after = %s WHERE id = %s",
                    (current_fitness, mut_id)
                )
                survived += 1
            elif current_fitness >= fitness_before * 0.95:
                # Fitness didn't drop more than 5% → survived
                await conn.execute(
                    "UPDATE orch.mutations SET status = 'survived', evaluated_at = NOW(), fitness_after = %s WHERE id = %s",
                    (current_fitness, mut_id)
                )
                survived += 1
            else:
                # Fitness dropped → revert (mark only, actual YAML revert in full_rollback)
                await conn.execute(
                    "UPDATE orch.mutations SET status = 'reverted', evaluated_at = NOW(), fitness_after = %s WHERE id = %s",
                    (current_fitness, mut_id)
                )
                reverted += 1

        await conn.commit()

    logger.info("Mutation survival: %d survived, %d reverted", survived, reverted)
    return survived, reverted


async def _prune_dead() -> int:
    """Remove patterns that haven't been seen in 30 days and have low occurrences."""
    threshold = datetime.now(timezone.utc) - timedelta(days=30)
    async with database.pool.connection() as conn:
        row = await conn.execute(
            "DELETE FROM orch.patterns WHERE crystallized = FALSE AND occurrences < 3 AND last_seen < %s RETURNING id",
            (threshold,)
        )
        deleted = len(await row.fetchall())
        await conn.commit()
    if deleted:
        logger.info("Pruned %d dead patterns", deleted)
    return deleted


async def _increment_generation():
    """Increment the generation counter."""
    async with database.pool.connection() as conn:
        await conn.execute("UPDATE orch.operational_state SET generation = generation + 1, updated_at = NOW() WHERE id = 1")
        await conn.commit()

    # Update CHANGELOG
    changelog = settings.orchestrator_path / "evolution" / "CHANGELOG.md"
    if changelog.exists():
        async with database.pool.connection() as conn:
            row = await conn.execute("SELECT generation, fitness_score FROM orch.operational_state WHERE id = 1")
            r = await row.fetchone()
            gen = r[0]
            fitness = r[1]

            row = await conn.execute("SELECT COUNT(*) FROM orch.mutations WHERE status = 'applied'")
            r = await row.fetchone()
            total_mutations = r[0]

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        entry = f"\n## Generation {gen} — {date_str}\n- Fitness: {fitness:.4f}\n- Total mutations: {total_mutations}\n"

        with open(changelog, "a", encoding="utf-8") as f:
            f.write(entry)

    logger.info("Generation incremented")
