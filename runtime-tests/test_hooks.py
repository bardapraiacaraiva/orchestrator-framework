"""Test hook integration endpoints."""
import pytest
import httpx

BASE = "http://localhost:8421"


@pytest.mark.asyncio
async def test_session_start_hook():
    async with httpx.AsyncClient(base_url=BASE, timeout=10) as c:
        r = await c.post("/hooks/session-start", json={"session_id": "test-001"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert "tasks_synced" in data


@pytest.mark.asyncio
async def test_session_end_hook():
    async with httpx.AsyncClient(base_url=BASE, timeout=10) as c:
        r = await c.post("/hooks/session-end", json={"session_id": "test-001"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert "fitness" in data


@pytest.mark.asyncio
async def test_task_complete_hook():
    async with httpx.AsyncClient(base_url=BASE, timeout=10) as c:
        r = await c.post("/hooks/task-complete", json={
            "task_id": "TEST-001",
            "skill": "dario-brand",
            "quality_score": 85.0,
            "tokens_used": 5000,
        })
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["score"] == 85.0


@pytest.mark.asyncio
async def test_task_complete_hook_no_skill():
    async with httpx.AsyncClient(base_url=BASE, timeout=5) as c:
        r = await c.post("/hooks/task-complete", json={
            "task_id": "TEST-002",
        })
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is False
