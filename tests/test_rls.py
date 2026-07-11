import asyncio, datetime

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

import shop.tables as t
from shop.security import apply_rls
from shop.keyservice import DbKeyService
from shop.services.bridge import BridgeService

APP_URI = 'postgresql+asyncpg://shop:secret@localhost:5432/shop'
RESEARCH_URI = 'postgresql+asyncpg://research:research@localhost:5432/shop'


async def denied(conn, sql, label):
    try:
        await conn.execute(text(sql))
        raise AssertionError(f'ДОСТУП НЕ ЗАКРЫТ: {label}')
    except ProgrammingError as e:
        assert 'permission denied' in str(e), e
        await conn.rollback()  # транзакция после отказа мертва
        print(f'  [ok] {label}: permission denied')


async def test_main():
    eng = create_async_engine(APP_URI, poolclass=NullPool)
    async with eng.begin() as conn:
        await conn.execute(text('DROP SCHEMA public CASCADE'))
        await conn.execute(text('CREATE SCHEMA public'))
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS postgis'))
        await conn.run_sync(t.Root.metadata.create_all)
        await apply_rls(conn)
    print('[ok] схема создана, RLS применён (роль, гранты, политики)')

    # данные в обоих доменах: персона + мост + свойства там и там
    Sess = async_sessionmaker(eng, expire_on_commit=False)
    ks = DbKeyService(Sess)
    await ks.create_key('escrow')
    async with Sess() as s:
        country = t.Country(iso2='ru', iso3='rus', name='Russia')
        s.add(country); await s.flush()
        place = t.Place(code='msk', name='Москва', country=country.id)
        s.add(place); await s.flush()
        person = t.Person(name={'last': 'Иванов'}, sex=True,
                          birthdate=datetime.date(1980, 5, 1), birth_place=place.id)
        s.add(person); await s.commit()
        bridge = BridgeService(session=s, keys=ks)
        link, pseudonym_id = await bridge.create_link('person', person.id, 'medical')
        s.add(t.Property(code='height', table='person', objectid=person.id,
                         value={'cm': 180}))                       # identity-строка
        s.add(t.Property(code='diagnosis', table='pseudonym', objectid=pseudonym_id,
                         value={'icd10': 'J06.9'}))                # operational-строка
        await s.commit()

    # приложение (владелец) видит всё
    async with eng.connect() as conn:
        n = (await conn.execute(text('SELECT count(*) FROM property'))).scalar_one()
        assert n == 2
    print('[ok] приложение (владелец схемы) видит обе строки property — RLS его не трогает')

    # исследователь
    r_eng = create_async_engine(RESEARCH_URI, poolclass=NullPool)
    async with r_eng.connect() as conn:
        await denied(conn, 'SELECT * FROM person', 'таблица person')
        await denied(conn, 'SELECT * FROM "user"', 'таблица user')
        await denied(conn, 'SELECT * FROM link', 'мост link')
        await denied(conn, 'SELECT * FROM access', 'копии DEK (access)')
        await denied(conn, 'SELECT * FROM pseudonym_pool', 'пул псевдонимов')

        rows = (await conn.execute(text('SELECT code, value FROM property'))).all()
        assert len(rows) == 1 and rows[0][0] == 'diagnosis', rows
        print(f'  [ok] property: видна только operational-строка ({rows[0][0]}), identity скрыта политикой')

        n = (await conn.execute(text('SELECT count(*) FROM country'))).scalar_one()
        assert n == 1
        n = (await conn.execute(text('SELECT count(*) FROM pseudonym'))).scalar_one()
        assert n >= 1
        n = (await conn.execute(text('SELECT count(*) FROM object'))).scalar_one()
        assert n > 0
        print('  [ok] справочники, псевдонимы и реестр читаются')

        # запись запрещена в принципе
        await denied(conn, "UPDATE property SET value = '{}'", 'запись в property')

    # идемпотентность
    async with eng.begin() as conn:
        await apply_rls(conn)
    print('[ok] повторный apply_rls: идемпотентно')

    await r_eng.dispose(); await eng.dispose()
    print('\nТЕСТ RLS ПРОЙДЕН')

