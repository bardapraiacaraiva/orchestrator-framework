"""Test task endpoints."""
import pytest
import httpx

BASE = "http://localhost:8421"


@pytest.mark.asyncio
async def test_task_list():
    async with httpx.AsyncClient(base_url=BASE, timeout=5) as c:
        r = await c.get("/tasks")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    if data:
        task = data[0]
        assert "id" in task
        assert "title" in task
        assert "status" in task


@pytest.mark.asyncio
async def test_task_stats():
    async with httpx.AsyncClient(base_url=BASE, timeout=5) as c:
        r = await c.get("/tasks/stats")
    assert r.status_code == 200
    data = r.json()
    assert "total" in data
    assert data["total"] >= 0
    assert "done" in data
    assert "in_progress" in data


@pytest.mark.asyncio
async def test_task_sync():
    async with httpx.AsyncClient(base_url=BASE, timeout=10) as c:
        r = await c.post("/tasks/sync")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert "tasks_synced" in data


@pytest.mark.asyncio
async def test_task_get_nonexistent():
    async with httpx.AsyncClient(base_url=BASE, timeout=5) as c:
        r = await c.get("/tasks/NONEXISTENT-999")
    assert r.status_code == 200
    data = r.json()
    assert "error" in data
