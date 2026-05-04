"""Sync task YAML files to PostgreSQL for queryable access."""
import logging
from pathlib import Path

from ruamel.yaml import YAML

from ..config import settings
from .. import database

logger = logging.getLogger(__name__)
yaml = YAML()


async def sync_tasks():
    """Scan active + done task YAMLs and upsert into DB."""
    count = 0
    for folder in [settings.tasks_active_path, settings.tasks_done_path]:
        if not folder.exists():
            continue
        for f in folder.glob("*.yaml"):
            try:
                data = yaml.load(f)
                if not data or "id" not in data:
                    continue
                await _upsert_task(data)
                count += 1
            except Exception as e:
                logger.warning("Failed to sync %s: %s", f.name, e)
    logger.info("Synced %d tasks to DB", count)
    return count


async def _upsert_task(data: dict):
    async with database.pool.connection() as conn:
        await conn.execute("""
            INSERT INTO orch.tasks (id, title, project, status, priority, assignee, skill,
                                    division, estimated_tokens, actual_tokens, quality_score,
                                    execution_policy, depends_on, created_at, updated_at)
            VALUES (%(id)s, %(title)s, %(project)s, %(status)s, %(priority)s, %(assignee)s,
                    %(skill)s, %(division)s, %(estimated_tokens)s, %(actual_tokens)s,
                    %(quality_score)s, %(execution_policy)s, %(depends_on)s,
                    %(created_at)s, NOW())
            ON CONFLICT (id) DO UPDATE SET
                title = EXCLUDED.title,
                project = EXCLUDED.project,
                status = EXCLUDED.status,
                priority = EXCLUDED.priority,
                assignee = EXCLUDED.assignee,
                skill = EXCLUDED.skill,
                actual_tokens = EXCLUDED.actual_tokens,
                quality_score = EXCLUDED.quality_score,
                updated_at = NOW()
        """, {
            "id": data.get("id", ""),
            "title": data.get("title", ""),
            "project": data.get("project"),
            "status": data.get("status", "backlog"),
            "priority": data.get("priority", "normal"),
            "assignee": data.get("assignee"),
            "skill": data.get("skill"),
            "division": data.get("division"),
            "estimated_tokens": data.get("estimated_tokens"),
            "actual_tokens": data.get("actual_tokens"),
            "quality_score": None,
            "execution_policy": data.get("execution_policy"),
            "depends_on": data.get("depends_on", []),
            "created_at": data.get("created_at", "2026-01-01T00:00:00Z"),
        })
        await conn.commit()
