"""Test synaptic weights endpoints."""
import pytest
import httpx

BASE = "http://localhost:8421"


@pytest.mark.asyncio
async def test_weights_list():
    async with httpx.AsyncClient(base_url=BASE, timeout=5) as c:
        r = await c.get("/weights")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    if data:
        w = data[0]
        assert "skill_a" in w
        assert "skill_b" in w
        assert "weight" in w
        assert 0.1 <= w["weight"] <= 1.0


@pytest.mark.asyncio
async def test_weights_top():
    async with httpx.AsyncClient(base_url=BASE, timeout=5) as c:
        r = await c.get("/weights/top")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_weights_reinforce():
    async with httpx.AsyncClient(base_url=BASE, timeout=10) as c:
        r = await c.post("/weights/reinforce", json={
            "skill_a": "test-skill-a",
            "skill_b": "test-skill-b",
            "score": 90.0,
        })
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
