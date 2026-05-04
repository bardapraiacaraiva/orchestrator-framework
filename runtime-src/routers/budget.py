"""Budget tracking endpoints."""
from datetime import datetime, timezone

from fastapi import APIRouter

from .. import database
from ..models import BudgetAddInput

router = APIRouter(prefix="/budget")


@router.get("")
async def current_budget():
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    async with database.pool.connection() as conn:
        row = await conn.execute(
            "SELECT month, total_tokens, token_limit, percentage, by_project, by_skill, by_model FROM orch.budget_monthly WHERE month = %s",
            (month,),
        )
        r = await row.fetchone()
    if not r:
        return {"month": month, "total_tokens": 0, "limit": 50000000, "percentage": 0.0}
    return {
        "month": r[0], "total_tokens": r[1], "limit": r[2], "percentage": round(r[3], 2),
        "by_project": r[4], "by_skill": r[5], "by_model": r[6],
    }


@router.post("/add")
async def add_tokens(data: BudgetAddInput):
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    async with database.pool.connection() as conn:
        # Upsert month
        await conn.execute("""
            INSERT INTO orch.budget_monthly (month, total_tokens, token_limit)
            VALUES (%s, %s, 50000000)
            ON CONFLICT (month) DO UPDATE SET
                total_tokens = orch.budget_monthly.total_tokens + %s,
                percentage = (orch.budget_monthly.total_tokens + %s)::float / orch.budget_monthly.token_limit * 100,
                updated_at = NOW()
        """, (month, data.tokens, data.tokens, data.tokens))
        await conn.commit()
    return {"ok": True, "month": month, "tokens_added": data.tokens}


@router.get("/trend")
async def budget_trend():
    async with database.pool.connection() as conn:
        rows = await conn.execute(
            "SELECT month, total_tokens, percentage FROM orch.budget_monthly ORDER BY month DESC LIMIT 6"
        )
        results = await rows.fetchall()
    return [{"month": r[0], "tokens": r[1], "pct": round(r[2], 2)} for r in reversed(results)]
