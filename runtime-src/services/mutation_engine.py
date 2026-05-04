"""Mutation Engine — The self-evolution core.
Modifies orchestrator YAML files based on measured patterns.
Safety-bounded: max 3 mutations per session, protected files never touched.
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from ruamel.yaml import YAML

from .. import database
from ..config import settings

logger = logging.getLogger(__name__)
yaml_rt = YAML()
yaml_rt.preserve_quotes = True

PROTECTED_FILES = {"manifesto.yaml", "company.yaml"}
MAX_MUTATIONS_PER_SESSION = 3
_mutations_this_session = 0


async def apply_synaptic_reinforcement(skill_a: str, skill_b: str, score: float):
    """Reinforce or weaken a skill pair based on co-activation score."""
    global _mutations_this_session
    if _mutations_this_session >= MAX_MUTATIONS_PER_SESSION:
        logger.debug("Mutation limit reached, skipping synaptic update")
        return

    # Normalize pair order (alphabetical)
    pair = tuple(sorted([skill_a, skill_b]))

    # Get current weight from DB
    async with database.pool.connection() as conn:
        row = await conn.execute(
            "SELECT id, weight, co_activations, avg_combined_score FROM orch.synaptic_weights WHERE skill_a = %s AND skill_b = %s",
            pair
        )
        existing = await row.fetchone()

        if existing:
            old_weight = existing[1]
            co_act = existing[2] + 1
            # Running average
            new_avg = ((existing[3] * existing[2]) + score) / co_act

            # Apply reinforcement
            if score >= 80:
                new_weight = min(old_weight + 0.05, 1.0)
            elif score < 50:
                new_weight = max(old_weight - 0.03, 0.1)
            else:
                new_weight = old_weight  # neutral

            await conn.execute("""
                UPDATE orch.synaptic_weights
                SET weight = %s, co_activations = %s, avg_combined_score = %s, last_activated = NOW(), updated_at = NOW()
                WHERE id = %s
            """, (new_weight, co_act, new_avg, existing[0]))
        else:
            # New pair
            new_weight = 0.55 if score >= 80 else 0.47 if score < 50 else 0.5
            await conn.execute("""
                INSERT INTO orch.synaptic_weights (skill_a, skill_b, co_activations, avg_combined_score, weight, last_activated)
                VALUES (%s, %s, 1, %s, %s, NOW())
            """, (pair[0], pair[1], score, new_weight))
            old_weight = 0.5

        await conn.commit()

    # Write back to YAML if weight changed significantly
    if existing and abs(new_weight - old_weight) >= 0.03:
        await _mutate_yaml_weight(pair[0], pair[1], old_weight, new_weight, score)
        _mutations_this_session += 1

    logger.info("Synaptic: %s + %s = %.2f (weight: %.2f→%.2f)", pair[0], pair[1], score, old_weight, new_weight if existing else 0.5)


async def _mutate_yaml_weight(skill_a: str, skill_b: str, old_weight: float, new_weight: float, trigger_score: float):
    """Write the weight update back to synaptic_weights.yaml."""
    yaml_path = settings.orchestrator_path / "synaptic_weights.yaml"
    if not yaml_path.exists():
        return

    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml_rt.load(f)

        # Find the pair in affinity_graph
        pair_key = f"{skill_a} + {skill_b}"
        graph = data.get("affinity_graph", {})

        if pair_key in graph:
            graph[pair_key]["weight"] = round(new_weight, 2)
            graph[pair_key]["co_activations"] = (graph[pair_key].get("co_activations", 0) or 0) + 1
            graph[pair_key]["avg_combined_score"] = round(trigger_score, 1)
        else:
            # Add new pair
            graph[pair_key] = {
                "co_activations": 1,
                "avg_combined_score": round(trigger_score, 1),
                "weight": round(new_weight, 2),
                "notes": "Auto-discovered by evolution engine",
            }

        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml_rt.dump(data, f)

        # Log mutation to DB
        await _record_mutation(
            file_mutated="synaptic_weights.yaml",
            field_changed=f"affinity_graph.{pair_key}.weight",
            old_value=str(old_weight),
            new_value=str(new_weight),
            reason=f"Co-activation score {trigger_score:.0f} triggered reinforcement",
        )
        logger.info("MUTATION: synaptic_weights.yaml — %s weight %.2f→%.2f", pair_key, old_weight, new_weight)

    except Exception as e:
        logger.error("Failed to mutate YAML: %s", e)


async def _record_mutation(file_mutated: str, field_changed: str, old_value: str, new_value: str, reason: str):
    """Record mutation in DB for tracking and potential rollback."""
    async with database.pool.connection() as conn:
        # Get current generation and fitness
        row = await conn.execute("SELECT generation, fitness_score FROM orch.operational_state WHERE id = 1")
        r = await row.fetchone()
        generation = r[0] if r else 1
        fitness = r[1] if r else 0.0

        await conn.execute("""
            INSERT INTO orch.mutations (generation, file_mutated, field_changed, old_value, new_value, reason, confidence, fitness_before)
            VALUES (%s, %s, %s, %s, %s, %s, 0.7, %s)
        """, (generation, file_mutated, field_changed, old_value, new_value, reason, fitness))

        await conn.execute("""
            INSERT INTO orch.audit_log (event_code, severity, entity_type, details)
            VALUES ('DARIO_MUTATION_APPLIED', 'info', 'config', %s)
        """, (json.dumps({"file": file_mutated, "field": field_changed, "old": old_value, "new": new_value}),))

        await conn.commit()


def reset_session_counter():
    """Reset mutation counter — called at session start."""
    global _mutations_this_session
    _mutations_this_session = 0
