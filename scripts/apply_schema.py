"""Standalone one-off: apply app/db/schema.sql to DATABASE_URL. Safe to re-run (idempotent DDL).

Usage: python -m scripts.apply_schema
"""

from __future__ import annotations

import asyncio

from app.config import get_settings
from app.db.pool import create_pool
from app.db.schema_apply import apply_schema


async def main() -> None:
    settings = get_settings()
    pool = await create_pool(settings.database_url)
    try:
        await apply_schema(pool)
        print("Schema applied successfully.")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
