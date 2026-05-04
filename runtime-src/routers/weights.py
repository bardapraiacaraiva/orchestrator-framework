"""Synaptic weights endpoints."""
from fastapi import APIRouter
from pydantic import BaseModel

from .. import database
from ..services.mutation_engine import apply_synaptic_reinforcement

router = APIRouter(prefix="/weights")


class ReinforcePair(BaseModel):
    skill_a: str
    skill_b: str
    score: float


@router.get("")
async def list_weights():
    async with database.pool.connection() as conn:
        rows = await conn.execute(
            "SELECT skill_a, skill_b, co_activations, avg_combined_score, weight, last_activated FROM orch.synaptic_weights ORDER BY weight DESC"
        )
        results = await rows.fetchall()
    return [
        {"skill_a": r[0], "skill_b": r[1], "co_activations": r[2],
         "avg_score": round(r[3], 1), "weight": round(r[4], 3),
         "last_activated": r[5].isoformat() if r[5] else None}
        for r in results
    ]


@router.get("/top")
async def top_pairs(limit: int = 10):
    async with database.pool.connection() as conn:
        rows = await conn.execute(
            "SELECT skill_a, skill_b, weight, avg_combined_score, co_activations FROM orch.synaptic_weights ORDER BY weight DESC LIMIT %s",
            (limit,)
        )
        results = await rows.fetchall()
    return [
        {"pair": f"{r[0]} + {r[1]}", "weight": round(r[2], 3), "avg_score": round(r[3], 1), "co_activations": r[4]}
        for r in results
    ]


@router.post("/reinforce")
async def reinforce_pair(data: ReinforcePair):
    """Record a co-activation and update synaptic weight."""
    await apply_synaptic_reinforcement(data.skill_a, data.skill_b, data.score)
    return {"ok": True, "pair": f"{data.skill_a} + {data.skill_b}", "score": data.score}
