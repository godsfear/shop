"""Онбординг веб-флоу: enroll (выпуск моста пациента) -> open_session без тела
(owner авто-дискавери по JWT) -> скоуп псевдонима. Идемпотентность enroll.
Требует Redis (сессия)."""
import datetime
import tempfile

import pytest
from fastapi import HTTPException
from sqlalchemy import text, select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

import shop.tables as t
from shop.keyservice import StubKeyService
from shop.models.auth import TokenPayload
from shop.models.medical import MedPropertyIn
from shop.models.user import UserCreate, Contact
from shop.services.bridge import BridgeService
from shop.services.medaccess import MedAccessService
from shop.services.user import UserService

URI = 'postgresql+asyncpg://shop:secret@localhost:5432/shop'


def _svc(s, ks, payload):
    return MedAccessService(session=s, bridge=BridgeService(session=s, keys=ks), payload=payload)


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
    async with Sess() as s:
        person = t.Person(name={'last': 'Иванов'}, sex=True,
                          birthdate=datetime.date(1980, 5, 1), birth_place=place_id)
        s.add(person); await s.commit()
        person_id = person.id
        user = await UserService(session=s).create(UserCreate(
            person=person_id, contact=Contact(email='p@x.com'), password='correct-horse'))
        user_id = user.id

    ks = StubKeyService(tempfile.mkdtemp())          # ключи выпускает сам enroll
    payload = TokenPayload(sub=user_id)

    # --- до enroll: сессию открыть нельзя (моста нет) -> 409 ---
    async with Sess() as s:
        with pytest.raises(HTTPException) as ei:
            await _svc(s, ks, payload).open_session()
        assert ei.value.status_code == 409
    print('[ok] open_session до enroll -> 409')

    # --- enroll выпускает мост (идемпотентно) ---
    async with Sess() as s:
        await _svc(s, ks, payload).enroll()
    async with Sess() as s:
        await _svc(s, ks, payload).enroll()          # повтор — no-op
    async with Sess() as s:
        n = (await s.execute(select(func.count()).select_from(t.Link).where(
            t.Link.table == 'person', t.Link.objectid == person_id,
            t.Link.scope == 'medical'))).scalar_one()
    assert n == 1, n
    print('[ok] enroll выпустил мост, повторный enroll идемпотентен (1 Link)')

    # --- open_session без тела: owner авто-дискавери по JWT ---
    async with Sess() as s:
        ttl = await _svc(s, ks, payload).open_session()
    assert ttl > 0
    # --- сессия скоупит данные пациента (round-trip через псевдоним) ---
    async with Sess() as s:
        await _svc(s, ks, payload).add_property(
            MedPropertyIn(code='allergy', value={'agent': 'пенициллин'}))
    async with Sess() as s:
        props = await _svc(s, ks, payload).properties()
    assert len(props) == 1 and props[0].code == 'allergy', props
    print('[ok] open_session (owner, без тела) -> сессия скоупит псевдоним')

    await eng.dispose()
    print('\nТЕСТ ОНБОРДИНГА ПРОЙДЕН')
