import asyncio, datetime

from fastapi import HTTPException
from sqlalchemy import text, select, func
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

import shop.tables as t
from shop.versioning import versions
from shop.models import CategoryCreate, CurrencyCreate, CurrencyUpdate
from shop.services.category import CategoryService
from shop.services.currency import CurrencyService
from shop.services.fsm import FSMService

URI = 'postgresql+asyncpg://shop:secret@localhost:5432/shop'


async def test_main():
    eng = create_async_engine(URI, poolclass=NullPool)
    async with eng.begin() as conn:
        await conn.execute(text('DROP SCHEMA public CASCADE'))
        await conn.execute(text('CREATE SCHEMA public'))
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS postgis'))
        await conn.run_sync(t.Root.metadata.create_all)
    Sess = async_sessionmaker(eng, expire_on_commit=False)

    async with Sess() as s:
        cat = await CategoryService(session=s).create(CategoryCreate(code='fiat'))
        cur = await CurrencyService(session=s).create(CurrencyCreate(
            category=cat.id, code='USD', name='Dollar', adjective='US',
            name_plural='dollars', name_minor='cent', name_minor_plural='cents',
            symbol='$', symbol_native='$'))
        cur_id = cur.id

    # --- версионный update: id стабилен, история копией ---
    async with Sess() as s:
        updated = await CurrencyService(session=s).update(cur_id, CurrencyUpdate(name='US Dollar'))
        assert updated.id == cur_id, 'id изменился — ссылки сломаны!'
    async with Sess() as s:
        hist = await versions(s, t.Currency, cur_id)
        assert len(hist) == 1 and hist[0].name == 'Dollar'
        assert hist[0].ends is not None and hist[0].version_of == cur_id
        current = (await s.execute(select(t.Currency).where(t.Currency.id == cur_id))).scalar_one()
        assert current.name == 'US Dollar' and current.begins == hist[0].ends
        in_registry = (await s.execute(select(func.count()).select_from(t.ObjectRegistry)
                       .where(t.ObjectRegistry.id == hist[0].id))).scalar_one()
        assert in_registry == 0, 'копия попала в реестр!'
        visible = (await s.execute(select(func.count()).select_from(t.Currency))).scalar_one()
        assert visible == 1, 'копия видна сквозь автофильтр!'
    print('[ok] update: id стабилен, копия с прежними значениями, периоды непрерывны')
    print('[ok] копия не в реестре и скрыта автофильтром; уникальность кода не пострадала')

    # --- конкурентные правки сериализуются блокировкой ---
    async def upd(name):
        async with Sess() as s:
            return await CurrencyService(session=s).update(cur_id, CurrencyUpdate(name=name))
    await asyncio.gather(upd('AAA'), upd('BBB'))
    async with Sess() as s:
        hist = await versions(s, t.Currency, cur_id)
        current = (await s.execute(select(t.Currency).where(t.Currency.id == cur_id))).scalar_one()
    assert len(hist) == 3, f'потеряна версия: {len(hist)}'
    assert current.name in ('AAA', 'BBB')
    print('[ok] конкурентные правки: обе применились по очереди, версий 3, текущая:', current.name)

    # --- правка закрытой строки невозможна ---
    async with Sess() as s:
        svc = CurrencyService(session=s)
        await svc.expire(cur_id)
        try:
            await svc.update(cur_id, CurrencyUpdate(name='X'))
            raise AssertionError('закрытая строка правится!')
        except HTTPException as e:
            assert e.status_code == 404
    print('[ok] правка закрытой строки: 404')

    # --- гонка FSM: два одновременных submit ---
    async with Sess() as s:
        country = t.Country(iso2='ru', iso3='rus', name='Russia')
        s.add(country); await s.flush()
        place = t.Place(code='msk', name='Москва', country=country.id)
        s.add(place); await s.flush()
        person = t.Person(name={'last': 'Иванов'}, sex=True,
                          birthdate=datetime.date(1980, 5, 1), birth_place=place.id)
        s.add(person); await s.flush()
        fsm_cat = t.Category(code='order', value={'fsm': {
            'states': ['draft', 'review'], 'initial': 'draft',
            'transitions': [{'event': 'submit', 'source': 'draft', 'dest': 'review'}],
        }})
        s.add(fsm_cat); await s.flush()
        entity = t.Entity(category=fsm_cat.id, code='order-1',
                          table='person', objectid=person.id)
        s.add(entity); await s.commit()
        eid = entity.id

    async def fire():
        async with Sess() as s:
            try:
                return (await FSMService(session=s).trigger('entity', eid, 'submit'))['state']
            except HTTPException as e:
                return e.status_code
    results = sorted(map(str, await asyncio.gather(fire(), fire())))
    assert results == ['409', 'review'], results
    async with Sess() as s:
        active = (await s.execute(select(func.count()).select_from(t.Property)
                  .where(t.Property.table == 'entity', t.Property.objectid == eid,
                         t.Property.code == 'state'))).scalar_one()
    assert active == 1, f'активных состояний: {active}'
    print('[ok] гонка FSM: один переход прошёл, второй 409, активное состояние одно')

    await eng.dispose()
    print('\nТЕСТ ВЕРСИОНИРОВАНИЯ ПРОЙДЕН')

