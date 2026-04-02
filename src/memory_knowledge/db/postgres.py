from __future__ import annotations

import asyncpg

from memory_knowledge.config import Settings

_pool: asyncpg.Pool | None = None


async def init_postgres(settings: Settings) -> asyncpg.Pool:
    global _pool
    connect_kwargs: dict = {}
    if settings.pg_ssl:
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        connect_kwargs["ssl"] = ctx
    if settings.pg_command_timeout:
        connect_kwargs["command_timeout"] = settings.pg_command_timeout
    # Disable prepared statement cache for PgBouncer/Supabase pooler connections
    if "pooler.supabase.com" in settings.database_url:
        connect_kwargs["statement_cache_size"] = 0
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
