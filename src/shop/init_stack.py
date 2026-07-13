"""Инициализация стека для контейнерного запуска (идемпотентно, БЕЗ удаления данных).

Одноразовый init-контейнер (см. docker-compose): схема (alembic) + роли/RLS +
медицинский сид. Запускается как владелец схемы (shop) до api/worker.
    python -m shop.init_stack
"""
import asyncio

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from .database import db_helper
from .medical_seed import seed_medical
from .security import apply_rls


async def _prepare() -> None:
    # образ PostGIS тянет схему tiger со своей таблицей place — она затеняет
    # public.place в search_path (create_all пропускает нашу как «уже есть»).
    # Фиксируем public на уровне БД: применяется ко всем последующим сессиям.
    async with db_helper.engine.connect() as conn:
        db = (await conn.execute(text('SELECT current_database()'))).scalar_one()
        await conn.execute(text(f'ALTER DATABASE "{db}" SET search_path TO public'))
        await conn.commit()


async def _rls_and_seed() -> None:
    async with db_helper.engine.begin() as conn:
        await apply_rls(conn)                 # роли app/research + FORCE RLS + политики
    async with db_helper.session_factory() as session:
        await seed_medical(session)           # справочник (концепты + элементы)


def main() -> None:
    asyncio.run(_prepare())                          # search_path -> public
    command.upgrade(Config('alembic.ini'), 'head')   # схема, триггеры, расширения
    asyncio.run(_rls_and_seed())
    print('init: схема, RLS и медицинский сид готовы')


if __name__ == '__main__':
    main()
