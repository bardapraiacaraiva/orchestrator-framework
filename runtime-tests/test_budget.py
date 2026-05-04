"""Test budget endpoints."""
import pytest
import httpx

BASE = "http://localhost:8421"


@pytest.mark.asyncio
async def test_budget_current():
    async with httpx.AsyncClient(base_url=BASE, timeout=5) as c:
        r = await c.get("/budget")
    assert r.status_code == 200
    data = r.json()
    assert "month" in data
    assert "total_tokens" in data
    assert "percentage" in data
    assert data["percentage"] >= 0


@pytest.mark.asyncio
async def test_budget_add():
    async with httpx.AsyncClient(base_url=BASE, timeout=5) as c:
        r = await c.post("/budget/add", json={
            "tokens": 1000,
            "project": "test-project",
            "skill": "dario-brand",
            "model": "opus",
        })
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["tokens_added"] == 1000


@pytest.mark.asyncio
async def test_budget_trend():
    async with httpx.AsyncClient(base_url=BASE, timeout=5) as c:
        r = await c.get("/budget/trend")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
