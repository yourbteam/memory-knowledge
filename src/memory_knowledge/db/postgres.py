from __future__ import annotations

import asyncpg

from memory_knowledge.config import Settings

_pool: asyncpg.Pool | None = None


async def init_postgres(settings: Settings) -> asyncpg.Pool:
    global _pool
    connect_kwargs: dict = {}
    if settings.pg_ssl:
        connect_kwargs["ssl"] = "require"
    if settings.pg_command_timeout:
        connect_kwargs["command_timeout"] = settings.pg_command_timeout
    _pool = await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=settings.pg_pool_min_size,
        max_size=settings.pg_pool_max_size,
        **connect_kwargs,
    )
    return _pool


def get_pg_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("PostgreSQL pool not initialized")
    return _pool


async def close_postgres() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
