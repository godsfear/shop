"""DB-подстраховка: триггеры реестра/доменов ловят сырые INSERT'ы,
уникальность активного FSM-состояния держит БД, break-glass уведомляет владельца."""
import datetime
import tempfile

import pytest
from sqlalchemy import text, select, func
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

import shop.tables as t
from shop.keyservice import StubKeyService, EMERGENCY
from shop.models.user import UserCreate, Contact
from conftest import drain
from shop.services.bridge import BridgeService
from shop.services.user import UserService

URI = 'postgresql+asyncpg://shop:secret@localhost:5432/shop'


async def test_main():
    eng = create_async_engine(URI)
    async with eng.begin() as conn:
        await conn.execute(text('DROP SCHEMA public CASCADE'))
        await conn.execute(text('CREATE SCHEMA public'))
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS postgis'))
        await conn.run_sync(t.Root.metadata.create_all)
    Sess = async_sessionmaker(eng, expire_on_commit=False)

    async with Sess() as s:
        country = t.Country(iso2='ru', iso3='rus', name='Russia')
        s.add(country); await s.flush()
        place = t.Place(code='msk', name='Москва', country=country.id)
        s.add(place); await s.commit()
        place_id = place.id

    # --- сырой INSERT якорной таблицы: триггер регистрирует с доменом ---
    async with eng.begin() as conn:
        pid = (await conn.execute(text(
            "INSERT INTO person (id, name, sex, birthdate, birth_place) "
            "VALUES (gen_random_uuid(), '{}', true, '1980-01-01', :bp) RETURNING id"),
            {'bp': place_id})).scalar_one()
        dom = (await conn.execute(text(
            'SELECT domain FROM object WHERE id = :i'), {'i': pid})).scalar_one()
        assert dom == 'identity'
    print('[ok] сырой INSERT person: триггер зарегистрировал в реестре (identity)')

    # --- сырой INSERT CrossTable: домен унаследован от цели ---
    async with eng.begin() as conn:
        prop_id = (await conn.execute(text(
            "INSERT INTO property (id, code, \"table\", objectid, value) "
            "VALUES (gen_random_uuid(), 'height', 'person', :p, '{}') RETURNING id"),
            {'p': pid})).scalar_one()
        dom = (await conn.execute(text(
            'SELECT domain FROM object WHERE id = :i'), {'i': prop_id})).scalar_one()
        assert dom == 'identity'
    print('[ok] сырой INSERT property: домен унаследован от цели триггером')

    # --- сырая связь через границу доменов: триггер отвергает ---
    async with eng.begin() as conn:
        psid = (await conn.execute(text(
            'INSERT INTO pseudonym (id) VALUES (gen_random_uuid()) RETURNING id'))).scalar_one()
    with pytest.raises(DBAPIError, match='запрещена'):
        async with eng.begin() as conn:
            await conn.execute(text(
                "INSERT INTO relation (id, code, \"table\", objectid, related_table, related_id) "
                "VALUES (gen_random_uuid(), 'is', 'person', :p, 'pseudonym', :ps)"),
                {'p': pid, 'ps': psid})
    print('[ok] сырая Relation identity<->operational: отвергнута триггером')

    # --- operational<->reference теперь РАЗРЕШЕНО (справочник публичен) ---
    async with eng.begin() as conn:
        await conn.execute(text(
            "INSERT INTO relation (id, code, \"table\", objectid, related_table, related_id) "
            "VALUES (gen_random_uuid(), 'lives_in', 'pseudonym', :ps, 'place', :pl)"),
            {'ps': psid, 'pl': place_id})
    print('[ok] сырая Relation operational->reference: разрешена')

    # --- сырой мост к не-identity: триггер отвергает ---
    with pytest.raises(DBAPIError, match='identity'):
        async with eng.begin() as conn:
            await conn.execute(text(
                "INSERT INTO link (id, \"table\", objectid, scope, payload) "
                "VALUES (gen_random_uuid(), 'pseudonym', :ps, 'medical', '\\x00')"),
                {'ps': psid})
    print('[ok] сырой Link к операционному объекту: отвергнут триггером')

    # --- одно активное FSM-состояние держит БД ---
    async with eng.begin() as conn:
        await conn.execute(text(
            "INSERT INTO property (id, code, \"table\", objectid, value) "
            "VALUES (gen_random_uuid(), 'state', 'person', :p, '{\"state\": \"a\"}')"),
            {'p': pid})
    with pytest.raises(IntegrityError):
        async with eng.begin() as conn:
            await conn.execute(text(
                "INSERT INTO property (id, code, \"table\", objectid, value) "
                "VALUES (gen_random_uuid(), 'state', 'person', :p, '{\"state\": \"b\"}')"),
                {'p': pid})
    print('[ok] второе активное состояние: uq_property_active_state отверг')

    # --- break-glass уведомляет владельца через outbox ---
    ks = StubKeyService(tempfile.mkdtemp(), approvals_required=2)
    ks.create_key('escrow')
    async with Sess() as s:
        person = t.Person(name={'last': 'Иванов'}, sex=True,
                          birthdate=datetime.date(1980, 5, 1), birth_place=place_id)
        s.add(person); await s.commit()
        user = await UserService(session=s).create(UserCreate(
            person=person.id, contact=Contact(email='owner@x.com'),
            password='correct-horse'))
        bridge = BridgeService(session=s, keys=ks)
        link, pseudonym_id = await bridge.create_link('person', person.id, 'medical')

        rid = ks.request_breakglass(EMERGENCY, 'escrow', 'nurse-1', 'без сознания')
        ks.approve(rid, 'kh-1'); ks.approve(rid, 'kh-2')
        resolved = await bridge.breakglass_resolve(link.id, rid)
        assert resolved == pseudonym_id

    await drain(Sess)  # разобрать outbox (уведомление break-glass)
    async with Sess() as s:
        msg = (await s.execute(select(t.Message).where(
            t.Message.receiver == user.id))).scalars().one()
        assert msg.code == 'breakglass' and 'medical' in msg.content
    print('[ok] break-glass: владельцу доставлено Message через outbox')

    await eng.dispose()
