import logging
from pathlib import Path

from psycopg_pool import AsyncConnectionPool

from .config import settings

logger = logging.getLogger(__name__)

pool: AsyncConnectionPool | None = None


async def init_pool():
    global pool
    pool = AsyncConnectionPool(
        conninfo=settings.database_url,
        min_size=2,
        max_size=10,
        open=False,
    )
    await pool.open()
    logger.info("Database pool opened")


async def close_pool():
    global pool
    if pool:
        await pool.close()
        logger.info("Database pool closed")


async def run_migrations():
    migration_file = Path(__file__).parent.parent / "migrations" / "001_initial_schema.sql"
    if not migration_file.exists():
        logger.warning("Migration file not found: %s", migration_file)
        return

    sql = migration_file.read_text(encoding="utf-8")
    async with pool.connection() as conn:
        await conn.execute(sql)
        await conn.commit()
    logger.info("Migrations applied successfully")


async def get_pool() -> AsyncConnectionPool:
    return pool
