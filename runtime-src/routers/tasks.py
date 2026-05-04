"""Task endpoints — queryable view of orchestrator tasks."""
from fastapi import APIRouter, Query

from .. import database
from ..models import TaskStats
from ..services.task_sync import sync_tasks

router = APIRouter(prefix="/tasks")


@router.get("")
async def list_tasks(status: str | None = None, project: str | None = None, limit: int = 50):
    conditions = []
    params = []
    if status:
        conditions.append("status = %s")
        params.append(status)
    if project:
        conditions.append("project = %s")
        params.append(project)

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    params.append(limit)

    async with database.pool.connection() as conn:
        rows = await conn.execute(
            f"SELECT id, title, project, status, priority, assignee, skill, quality_score, created_at FROM orch.tasks {where} ORDER BY created_at DESC LIMIT %s",
            params,
        )
        results = await rows.fetchall()

    return [
        {"id": r[0], "title": r[1], "project": r[2], "status": r[3], "priority": r[4],
         "assignee": r[5], "skill": r[6], "quality_score": r[7],
         "created_at": r[8].isoformat() if r[8] else None}
        for r in results
    ]


@router.get("/stats", response_model=TaskStats)
async def task_stats():
    async with database.pool.connection() as conn:
        rows = await conn.execute("SELECT status, COUNT(*) FROM orch.tasks GROUP BY status")
        counts = dict(await rows.fetchall())
    return TaskStats(
        total=sum(counts.values()),
        backlog=counts.get("backlog", 0),
        todo=counts.get("todo", 0),
        in_progress=counts.get("in_progress", 0),
        in_review=counts.get("in_review", 0),
        done=counts.get("done", 0),
        blocked=counts.get("blocked", 0),
    )


@router.get("/{task_id}")
async def get_task(task_id: str):
    async with database.pool.connection() as conn:
        row = await conn.execute(
            "SELECT id, title, project, status, priority, assignee, skill, division, estimated_tokens, actual_tokens, quality_score, execution_policy, depends_on, created_at, started_at, completed_at FROM orch.tasks WHERE id = %s",
            (task_id,),
        )
        r = await row.fetchone()
    if not r:
        return {"error": "Task not found"}
    return {
        "id": r[0], "title": r[1], "project": r[2], "status": r[3], "priority": r[4],
        "assignee": r[5], "skill": r[6], "division": r[7], "estimated_tokens": r[8],
        "actual_tokens": r[9], "quality_score": r[10], "execution_policy": r[11],
        "depends_on": r[12], "created_at": r[13].isoformat() if r[13] else None,
        "started_at": r[14].isoformat() if r[14] else None,
        "completed_at": r[15].isoformat() if r[15] else None,
    }


@router.post("/sync")
async def trigger_sync():
    count = await sync_tasks()
    return {"ok": True, "tasks_synced": count}
