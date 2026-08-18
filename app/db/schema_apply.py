from pathlib import Path

import asyncpg

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


async def apply_schema(pool: asyncpg.Pool) -> None:
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    async with pool.acquire() as con:
        await con.execute(sql)
