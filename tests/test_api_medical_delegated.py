"""API Property, Слой B (доступ по мосту, вариант b): врач/близкий резолвит
псевдоним по link_id + групповому ключу (ACL KeyService), БЕЗ сессии; псевдоним
в поверхность API не попадает. Чужой actor -> 403; link_id без key_id -> 400.

Сессии/Redis не требует — резолв статeless (bridge.resolve мягко деградирует)."""
import datetime
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

import shop.tables as t
from shop.keyservice import DbKeyService
from shop.models.auth import TokenPayload
from shop.models.property import PropertyCreate
from shop.services.bridge import BridgeService
from shop.services.medaccess import MedAccessService
from shop.services.property import PropertyService

URI = 'postgresql+asyncpg://shop:secret@localhost:5432/shop'


def _svc(s, ks, payload):
    return MedAccessService(session=s, bridge=BridgeService(session=s, keys=ks), payload=payload)


async def test_main():
    eng = create_async_engine(URI, poolclass=NullPool)
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

    group_key = 'clinic-a'
    doctor = uuid.uuid4()          # actor'ом в KeyService выступает sub токена
    intruder = uuid.uuid4()
    ks = DbKeyService(Sess)
    await ks.create_key('escrow')                     # escrow-копия в create_link
    await ks.create_key(group_key); await ks.grant(group_key, str(doctor))

    async with Sess() as s:
        link, pseudonym_id = await BridgeService(session=s, keys=ks).create_link(
            'person', person_id, 'medical', groups={group_key: person_id})
        link_id = link.id
    async with Sess() as s:
        await PropertyService(session=s).create(PropertyCreate(
            category=None, code='diagnosis', table='pseudonym', objectid=pseudonym_id,
            value={'icd10': 'J06.9'}))

    # --- врач (грант группы) резолвит по мосту, без сессии ---
    async with Sess() as s:
        props = await _svc(s, ks, TokenPayload(sub=doctor)).properties(
            link_id=link_id, key_id=group_key)
    assert len(props) == 1 and props[0].code == 'diagnosis', props
    print('[ok] врач видит данные по мосту (link_id+ключ), без сессии')

    # --- чужой actor (нет в ACL ключа) -> 403 ---
    async with Sess() as s:
        with pytest.raises(HTTPException) as ei:
            await _svc(s, ks, TokenPayload(sub=intruder)).properties(
                link_id=link_id, key_id=group_key)
        assert ei.value.status_code == 403
    print('[ok] чужой actor -> 403 (ACL ключа)')

    # --- link_id без key_id -> 400 ---
    async with Sess() as s:
        with pytest.raises(HTTPException) as ei:
            await _svc(s, ks, TokenPayload(sub=doctor)).properties(link_id=link_id)
        assert ei.value.status_code == 400
    print('[ok] link_id без key_id -> 400')

    await eng.dispose()
    print('\nТЕСТ ДЕЛЕГИРОВАННОГО ДОСТУПА (Слой B) ПРОЙДЕН')
