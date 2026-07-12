"""Фаза 3: полнота секций (данные) + красные флаги (код) — read-only assess."""
from sqlalchemy import text, select
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

import shop.tables as t
from shop.medical_seed import seed_medical
from shop.models.entity import EntityCreate
from shop.models.property import PropertyCreate
from shop.services.entity import EntityService
from shop.services.property import PropertyService
from shop.services.medical import MedicalService

URI = 'postgresql+asyncpg://shop:secret@localhost:5432/shop'


async def test_main():
    eng = create_async_engine(URI, poolclass=NullPool)
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

    # эпизод болезни + два симптома present (боль в груди + одышка = флаг acs)
    async with Sess() as s:
        ep = await EntityService(session=s).create(EntityCreate(
            category=ids['illness'], code='ep-1', name='Эпизод',
            table='pseudonym', objectid=pid))
        eid = ep.id
    async with Sess() as s:
        psvc = PropertyService(session=s)
        await psvc.create(PropertyCreate(
            category=ids['symptom'], code='chest_pain', table='entity', objectid=eid,
            value={'status': 'present', 'source': 'self'}))
        await psvc.create(PropertyCreate(
            category=ids['symptom'], code='dyspnea', table='entity', objectid=eid,
            value={'status': 'present', 'source': 'self'}))

    # --- оценка: симптомы есть, пациентские секции пусты, флаг acs горит ---
    async with Sess() as s:
        r = await MedicalService(session=s).assess(pid, eid)
    assert 'symptom' not in r['gaps'], r          # симптомы заполнены
    assert set(r['gaps']) == {'medication', 'allergy', 'chronic', 'heredity', 'surgery', 'social'}, r
    assert r['alerts'] == ['acs'], r
    print('[ok] пробелы найдены (medication/allergy/heredity), флаг acs сработал')

    # --- заполнить лекарство пациента -> секция medication уходит из пробелов ---
    async with Sess() as s:
        await PropertyService(session=s).create(PropertyCreate(
            category=ids['medication'], code='aspirin', table='pseudonym', objectid=pid,
            value={'dose': '100 мг'}))
    async with Sess() as s:
        r = await MedicalService(session=s).assess(pid, eid)
    assert 'medication' not in r['gaps'], r
    assert set(r['gaps']) == {'allergy', 'chronic', 'heredity', 'surgery', 'social'}, r
    print('[ok] после записи лекарства секция medication закрыта')

    # --- убрать боль в груди (absent) -> флаг acs гаснет ---
    async with Sess() as s:
        await PropertyService(session=s).create(PropertyCreate(
            category=ids['symptom'], code='fever', table='entity', objectid=eid,
            value={'status': 'present', 'source': 'self'}))
        # chest_pain остаётся present -> флаг всё ещё горит; проверим обратное отдельно
    # отдельный эпизод без боли в груди: флаг не горит
    async with Sess() as s:
        ep2 = await EntityService(session=s).create(EntityCreate(
            category=ids['illness'], code='ep-2', name='Эпизод 2',
            table='pseudonym', objectid=pid))
        eid2 = ep2.id
    async with Sess() as s:
        await PropertyService(session=s).create(PropertyCreate(
            category=ids['symptom'], code='dyspnea', table='entity', objectid=eid2,
            value={'status': 'present', 'source': 'self'}))
    async with Sess() as s:
        r2 = await MedicalService(session=s).assess(pid, eid2)
    assert r2['alerts'] == [], r2                  # одна одышка без боли в груди — не acs
    print('[ok] флаг acs НЕ срабатывает на одной одышке (нужна боль в груди)')

    await eng.dispose()
    print('\nТЕСТ ПОЛНОТЫ ПРОЙДЕН')
