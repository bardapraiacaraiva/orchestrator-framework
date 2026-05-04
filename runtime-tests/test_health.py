"""Test health and status endpoints."""
import pytest
import httpx

BASE = "http://localhost:8421"


@pytest.mark.asyncio
async def test_root():
    async with httpx.AsyncClient(base_url=BASE, timeout=5) as c:
        r = await c.get("/")
    assert r.status_code == 200
    data = r.json()
    assert data["service"] == "dario-orch"
    assert data["version"] == "1.0.0"
    assert data["status"] == "running"


@pytest.mark.asyncio
async def test_health():
    async with httpx.AsyncClient(base_url=BASE, timeout=5) as c:
        r = await c.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "healthy"
    assert data["database"] == "up"
    assert "uptime_seconds" in data


@pytest.mark.asyncio
async def test_status():
    async with httpx.AsyncClient(base_url=BASE, timeout=5) as c:
        r = await c.get("/status")
    assert r.status_code == 200
    data = r.json()
    assert data["state"] in ("ACTIVE", "REFLECTIVE_PAUSE", "GUARDIAN", "EXPANSION")
    assert data["autonomy_level"] in ("P-A1", "P-A2", "P-A3", "P-A4")
    assert 0 <= data["system_health"] <= 1.0
    assert data["generation"] >= 1
