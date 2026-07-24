"""Дев-бутстрап: свежая схема + RLS + справочники. Запуск: uv run python scripts/bootstrap_dev.py
ВНИМАНИЕ: сносит схему public — только для локальной разработки."""
import asyncio

from sqlalchemy import text

import shop.tables as t
from shop.database import db_helper
from shop.geography_seed import seed_geography
from shop.medical_seed import seed_medical
from shop.security import apply_rls


async def main() -> None:
    async with db_helper.engine.begin() as conn:
        await conn.execute(text('DROP SCHEMA public CASCADE'))
        await conn.execute(text('CREATE SCHEMA public'))
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS postgis'))
        await conn.run_sync(t.Root.metadata.create_all)
        await apply_rls(conn)
    async with db_helper.session_factory() as s:
        await seed_medical(s)
    async with db_helper.session_factory() as s:
        await seed_geography(s)
    print('готово: схема + RLS + справочники')


asyncio.run(main())
