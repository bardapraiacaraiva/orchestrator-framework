"""Test evolution engine endpoints."""
import pytest
import httpx

BASE = "http://localhost:8421"


@pytest.mark.asyncio
async def test_evolution_status():
    async with httpx.AsyncClient(base_url=BASE, timeout=5) as c:
        r = await c.get("/evolution")
    assert r.status_code == 200
    data = r.json()
    assert "generation" in data
    assert data["generation"] >= 1
    assert "fitness_score" in data
    assert "mutations_applied" in data
    assert "fitness_trend" in data
    assert isinstance(data["fitness_trend"], list)


@pytest.mark.asyncio
async def test_evolution_fitness():
    async with httpx.AsyncClient(base_url=BASE, timeout=5) as c:
        r = await c.get("/evolution/fitness")
    assert r.status_code == 200
    data = r.json()
    assert "entries" in data
    assert isinstance(data["entries"], list)


@pytest.mark.asyncio
async def test_evolution_mutations():
    async with httpx.AsyncClient(base_url=BASE, timeout=5) as c:
        r = await c.get("/evolution/mutations")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    if data:
        mut = data[0]
        assert "file" in mut
        assert "status" in mut
        assert mut["status"] in ("applied", "survived", "reverted", "reinforced")


@pytest.mark.asyncio
async def test_evolution_patterns():
    async with httpx.AsyncClient(base_url=BASE, timeout=5) as c:
        r = await c.get("/evolution/patterns")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_evolution_pulse_micro():
    async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
        r = await c.post("/evolution/pulse/micro")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["pulse_type"] == "micro"
    assert "fitness" in data


@pytest.mark.asyncio
async def test_evolution_pulse_session():
    async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
        r = await c.post("/evolution/pulse/session")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert "crystallized" in data


@pytest.mark.asyncio
async def test_evolution_pulse_invalid():
    async with httpx.AsyncClient(base_url=BASE, timeout=5) as c:
        r = await c.post("/evolution/pulse/invalid")
    assert r.status_code == 200
    data = r.json()
    assert "error" in data
