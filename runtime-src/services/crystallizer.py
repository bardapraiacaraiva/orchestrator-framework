"""Pattern Crystallizer — Transforms repeated observations into permanent rules.
When a pattern repeats N times (threshold=5), it crystallizes into an actionable rule.
"""
import json
import logging
from datetime import datetime, timezone

from .. import database
from ..config import settings
from .mutation_engine import _record_mutation

logger = logging.getLogger(__name__)

THRESHOLD = 5  # Pattern must repeat N times before becoming a rule


async def detect_and_crystallize() -> dict:
    """Scan patterns table. Crystallize any that hit threshold."""
    result = {"patterns_checked": 0, "crystallized": 0, "details": []}

    async with database.pool.connection() as conn:
        # Get uncrystallized patterns at or above threshold
        rows = await conn.execute(
            "SELECT id, pattern_type, description, occurrences, meta FROM orch.patterns WHERE crystallized = FALSE AND occurrences >= %s",
            (THRESHOLD,)
        )
        ready = await rows.fetchall()
        result["patterns_checked"] = len(ready)

        for pat in ready:
            pat_id, pat_type, description, occurrences, meta = pat
            meta = meta or {}

            rule = await _crystallize_pattern(pat_type, description, meta)
            if rule:
                # Mark as crystallized
                await conn.execute("""
                    UPDATE orch.patterns SET crystallized = TRUE, rule_applied = %s, crystallized_at = NOW()
                    WHERE id = %s
                """, (rule, pat_id))

                await conn.execute("""
                    INSERT INTO orch.audit_log (event_code, severity, entity_type, entity_id, details)
                    VALUES ('DARIO_PATTERN_CRYSTALLIZED', 'info', 'pattern', %s, %s)
                """, (str(pat_id), json.dumps({"type": pat_type, "rule": rule})))

                result["crystallized"] += 1
                result["details"].append({"type": pat_type, "rule": rule})
                logger.info("CRYSTALLIZED: [%s] %s → %s", pat_type, description, rule)

        await conn.commit()

    return result


async def record_pattern(pattern_type: str, description: str, meta: dict = None):
    """Record an observation. If pattern already exists, increment count."""
    async with database.pool.connection() as conn:
        # Check if pattern already exists (same type + description)
        row = await conn.execute(
            "SELECT id, occurrences FROM orch.patterns WHERE pattern_type = %s AND description = %s",
            (pattern_type, description)
        )
        existing = await row.fetchone()

        if existing:
            await conn.execute(
                "UPDATE orch.patterns SET occurrences = occurrences + 1, last_seen = NOW(), meta = COALESCE(%s, meta) WHERE id = %s",
                (json.dumps(meta) if meta else None, existing[0])
            )
            new_count = existing[1] + 1
        else:
            await conn.execute("""
                INSERT INTO orch.patterns (pattern_type, description, occurrences, meta)
                VALUES (%s, %s, 1, %s)
            """, (pattern_type, description, json.dumps(meta) if meta else None))
            new_count = 1

        await conn.commit()

    logger.debug("Pattern [%s] '%s' now at %d/%d", pattern_type, description[:50], new_count, THRESHOLD)
    return new_count


async def _crystallize_pattern(pattern_type: str, description: str, meta: dict) -> str | None:
    """Convert a pattern into an actionable rule. Returns rule description."""

    if pattern_type == "dispatch_correction":
        # User corrected dispatch — learn the correct routing
        correct_skill = meta.get("correct_skill", "")
        keyword = meta.get("keyword", "")
        if correct_skill and keyword:
            rule = f"Route '{keyword}' → {correct_skill} (learned from {THRESHOLD}+ corrections)"
            # Future: write to dispatch rules YAML
            return rule

    elif pattern_type == "quality_low_dimension":
        # Skill consistently scores low on a dimension
        skill = meta.get("skill", "")
        dimension = meta.get("dimension", "")
        if skill and dimension:
            rule = f"Skill '{skill}' weak on '{dimension}' — add pre-execution hint"
            return rule

    elif pattern_type == "co_activation_success":
        # Skills consistently co-activate with high scores
        skill_a = meta.get("skill_a", "")
        skill_b = meta.get("skill_b", "")
        if skill_a and skill_b:
            rule = f"Auto-suggest composite mode: {skill_a} + {skill_b} (proven affinity)"
            return rule

    elif pattern_type == "fallback_success":
        # When skill X fails, skill Y consistently succeeds
        primary = meta.get("primary_skill", "")
        fallback = meta.get("fallback_skill", "")
        if primary and fallback:
            rule = f"Update fallback: {primary}.fallback = {fallback} (proven by {THRESHOLD}+ recoveries)"
            return rule

    elif pattern_type == "token_overrun":
        # Tasks consistently use more tokens than estimated
        skill = meta.get("skill", "")
        avg_actual = meta.get("avg_actual", 0)
        if skill:
            rule = f"Increase token estimate for '{skill}' to {int(avg_actual * 1.2)} (consistently over-budget)"
            return rule

    # Generic fallback
    return f"Pattern noted: {description} (occurred {THRESHOLD}+ times)"


async def analyze_session_patterns():
    """Analyze recent quality scores and task data for emerging patterns.
    Called by session pulse.
    """
    patterns_found = 0

    async with database.pool.connection() as conn:
        # Pattern: Skill consistently scores low on a dimension
        # Check last 10 scores per skill — if any dimension avg < 0.5
        rows = await conn.execute("""
            SELECT skill,
                   AVG(specificity) as avg_s, AVG(actionability) as avg_a,
                   AVG(completeness) as avg_c, AVG(accuracy) as avg_ac, AVG(tone) as avg_t,
                   COUNT(*) as cnt
            FROM orch.quality_scores
            GROUP BY skill
            HAVING COUNT(*) >= 3
        """)
        for r in await rows.fetchall():
            skill = r[0]
            dimensions = {"specificity": r[1], "actionability": r[2], "completeness": r[3], "accuracy": r[4], "tone": r[5]}
            for dim, avg in dimensions.items():
                if avg and avg < 0.5:
                    await record_pattern(
                        "quality_low_dimension",
                        f"{skill} weak on {dim} (avg {avg:.2f})",
                        {"skill": skill, "dimension": dim, "avg_score": avg}
                    )
                    patterns_found += 1

        # Pattern: Co-activation success (skills that appear in sequence with high scores)
        rows = await conn.execute("""
            SELECT skill_a, skill_b, co_activations, avg_combined_score
            FROM orch.synaptic_weights
            WHERE co_activations >= 3 AND avg_combined_score >= 85
        """)
        for r in await rows.fetchall():
            await record_pattern(
                "co_activation_success",
                f"{r[0]} + {r[1]} high affinity (avg {r[3]:.0f}, {r[2]} co-activations)",
                {"skill_a": r[0], "skill_b": r[1]}
            )
            patterns_found += 1

    logger.info("Session pattern analysis: %d patterns detected", patterns_found)
    return patterns_found
