"""DARIO Orchestrator Runtime Launcher."""
import asyncio
import sys

# Windows fix: psycopg3 async requires SelectorEventLoop
# MUST be set BEFORE any async imports
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn

if __name__ == "__main__":
    config = uvicorn.Config(
        "src.main:app",
        host="0.0.0.0",
        port=8421,
        loop="none",
        reload=False,
    )
    server = uvicorn.Server(config)
    asyncio.run(server.serve())
