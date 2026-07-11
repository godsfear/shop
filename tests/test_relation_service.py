"""RelationService (generic): CRUD из CrudService + find по любому концу связи.

Проверяет и то, что ORM-путь пропускает operational->reference (domain-guard
ослаблен): пациент(псевдоним) -> лекарство(справочник)."""
import pytest
from fastapi import HTTPException
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

import shop.tables as t
from shop.medical_seed import seed_medical
from shop.models.relation import RelationCreate, RelationUpdate, RelationFilter
from shop.services.relation import RelationService

URI = 'postgresql+asyncpg://shop:secret@localhost:5432/shop'


async def test_main():
    eng = create_async_engine(URI)
    async with eng.begin() as conn:
        await conn.execute(text('DROP SCHEMA public CASCADE'))
        await conn.execute(text('CREATE SCHEMA public'))
        await conn.run_sync(t.Root.metadata.create_all)
    Sess = async_sessionmaker(eng, expire_on_commit=False)

    async with Sess() as s:
        ids = await seed_medical(s)
    async with Sess() as s:
        pseud = t.Pseudonym(); s.add(pseud); await s.commit()
        pid = pseud.id
    async with Sess() as s:
        aspirin = (await s.execute(select(t.Entity.id).where(
            t.Entity.code == 'aspirin'))).scalar_one()

    # --- create: пациент(operational) -> лекарство(reference) ---
    async with Sess() as s:
        rel = await RelationService(session=s).create(RelationCreate(
            category=ids['medication'], code='takes',
            table='pseudonym', objectid=pid,
            related_table='entity', related_id=aspirin))
        rid = rel.id
    print('[ok] Relation создан через RelationService (operational->reference)')

    # --- find по любому концу ---
    async with Sess() as s:
        rsvc = RelationService(session=s)
        by_src = await rsvc.find(RelationFilter(table='pseudonym', objectid=pid))
        by_trg = await rsvc.find(RelationFilter(related_table='entity', related_id=aspirin))
        by_code = await rsvc.find(RelationFilter(code='takes'))
    assert len(by_src) == 1 and by_src[0].related_id == aspirin
    assert len(by_trg) == 1 and by_trg[0].objectid == pid
    assert len(by_code) == 1
    print('[ok] find по источнику / цели / коду')

    # --- пустой фильтр -> 400 (из CrudService._where) ---
    async with Sess() as s:
        with pytest.raises(HTTPException) as ei:
            await RelationService(session=s).find(RelationFilter())
        assert ei.value.status_code == 400
    print('[ok] пустой фильтр -> 400')

    # --- update описательного поля ---
    async with Sess() as s:
        upd = await RelationService(session=s).update(rid, RelationUpdate(name='Принимает'))
        assert upd.name == 'Принимает'
    print('[ok] update name')

    # --- expire: уходит из активной выборки ---
    async with Sess() as s:
        await RelationService(session=s).expire(upd.id)
    async with Sess() as s:
        left = await RelationService(session=s).find(RelationFilter(objectid=pid))
    assert left == [], left
    print('[ok] expire -> связь ушла из активных')

    await eng.dispose()
    print('\nТЕСТ RELATION SERVICE ПРОЙДЕН')
