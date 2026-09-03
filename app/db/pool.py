import json

import asyncpg


async def _init_connection(conn: asyncpg.Connection) -> None:
    # asyncpg does not decode json/jsonb columns to dict/list by default —
    # without this codec, every jsonb column (e.g. applications.project_context)
    # comes back as a raw str, which breaks any code expecting a dict.
    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )
    await conn.set_type_codec(
        "json",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )


async def create_pool(database_url: str) -> asyncpg.Pool:
    return await asyncpg.create_pool(
        database_url, min_size=1, max_size=5, init=_init_connection
    )
