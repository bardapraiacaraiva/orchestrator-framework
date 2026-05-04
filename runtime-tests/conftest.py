"""Shared test fixtures — uses the LIVE service on port 8421."""
import asyncio
import sys

import pytest
import httpx

BASE_URL = "http://localhost:8421"


@pytest.fixture(scope="session")
def event_loop_policy():
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture(scope="session")
def base_url():
    return BASE_URL


@pytest.fixture
async def client():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as c:
        yield c
