import time

import httpx
from fastapi import APIRouter

from ..config import settings
from .. import database
from ..models import HealthResponse, StatusResponse
from ..services.state_machine import get_state

router = APIRouter()
_start_time = time.time()


@router.get("/")
async def root():
    return {"service": "dario-orch", "version": "1.0.0", "status": "running"}


@router.get("/health", response_model=HealthResponse)
async def health():
    # Check DB
    db_status = "down"
    try:
        async with database.pool.connection() as conn:
            await conn.execute("SELECT 1")
        db_status = "up"
    except Exception:
        pass

    # Check RAG
    rag_status = "down"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{settings.rag_engine_url}/health")
            if r.status_code == 200:
                rag_status = "up"
    except Exception:
        pass

    overall = "healthy" if db_status == "up" else "degraded"
    return HealthResponse(
        status=overall,
        uptime_seconds=round(time.time() - _start_time, 1),
        database=db_status,
        rag_engine=rag_status,
    )


@router.get("/status", response_model=StatusResponse)
async def status():
    state_data = await get_state()
    return StatusResponse(
        state=state_data["state"],
        autonomy_level=state_data["autonomy_level"],
        system_health=state_data["system_health"],
        fitness_score=state_data["fitness_score"],
        generation=state_data["generation"],
        total_tasks_completed=state_data["total_tasks_completed"],
        last_pulse=state_data["last_pulse"],
        started_at=state_data["started_at"],
    )
