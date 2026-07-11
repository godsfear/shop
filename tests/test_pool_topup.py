"""Фоновый добор пула псевдонимов до целевого размера."""
from sqlalchemy import text, select, func, delete
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

import shop.tables as t
from shop.services.bridge import BridgeService


URI = 'postgresql+asyncpg://shop:secret@localhost:5432/shop'


async def _pool(Sess) -> int:
    async with Sess() as s:
        return (await s.execute(select(func.count()).select_from(t.PseudonymPool))).scalar_one()


async def test_main():
    eng = create_async_engine(URI)
    async with eng.begin() as conn:
        await conn.execute(text('DROP SCHEMA public CASCADE'))
        await conn.execute(text('CREATE SCHEMA public'))
        await conn.run_sync(t.Root.metadata.create_all)
    Sess = async_sessionmaker(eng, expire_on_commit=False)

    # пустой пул -> добор до цели (target=100 по умолчанию)
    async with Sess() as s:
        created = await BridgeService(session=s).top_up_pool()
    assert created == 100 and await _pool(Sess) == 100, created
    print(f'[ok] пустой пул добран до цели: {created}')

    # полный пул -> добор ничего не делает (идемпотентно)
    async with Sess() as s:
        created = await BridgeService(session=s).top_up_pool()
    assert created == 0 and await _pool(Sess) == 100
    print('[ok] полный пул: добор no-op')

    # частичный расход -> добор восполняет ровно дефицит
    async with Sess() as s:
        ids = (await s.execute(select(t.PseudonymPool.id).limit(30))).scalars().all()
        await s.execute(delete(t.PseudonymPool).where(t.PseudonymPool.id.in_(ids)))
        await s.commit()
    assert await _pool(Sess) == 70
    async with Sess() as s:
        created = await BridgeService(session=s).top_up_pool()
    assert created == 30 and await _pool(Sess) == 100, created
    print('[ok] частичный расход: добор восполнил дефицит (30)')

    # явная цель ниже наличия -> no-op
    async with Sess() as s:
        created = await BridgeService(session=s).top_up_pool(target=50)
    assert created == 0
    print('[ok] цель ниже наличия: no-op')

    await eng.dispose()
    print('\nТЕСТ ДОБОРА ПУЛА ПРОЙДЕН')
