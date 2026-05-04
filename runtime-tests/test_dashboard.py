"""Test dashboard endpoints."""
import pytest
import httpx

BASE = "http://localhost:8421"


@pytest.mark.asyncio
async def test_dashboard_html():
    async with httpx.AsyncClient(base_url=BASE, timeout=5) as c:
        r = await c.get("/dashboard")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "DARIO Orchestrator" in r.text
    assert "Generation" in r.text or "generation" in r.text


@pytest.mark.asyncio
async def test_dashboard_data():
    async with httpx.AsyncClient(base_url=BASE, timeout=10) as c:
        r = await c.get("/dashboard/data")
    assert r.status_code == 200
    data = r.json()
    assert "state" in data
    assert "tasks" in data
    assert "fitness_trend" in data
    assert "quality_recent" in data
    assert "mutations" in data
    assert "patterns" in data
    assert "weights" in data
    assert isinstance(data["fitness_trend"], list)
