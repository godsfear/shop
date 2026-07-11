"""Consent -> KeyService: одобрение медицинского согласия открывает криптодоступ
(ACL ключа пациента), отзыв — закрывает. Покрыты оба пути:
- согласие одобрено ДО enroll (ключа ещё нет) -> доступ догрантивает enroll (re-sync);
- согласие одобрено ПОСЛЕ enroll -> грант сразу в decide.
Требует Redis (кэш моста)."""
import datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

import shop.tables as t
from shop.cache import get_cache
from shop.keyservice import DbKeyService
from shop.models.auth import TokenPayload
from shop.models.consent import ConsentDecision, ConsentRequest
from shop.models.user import Contact, UserCreate
from shop.services.bridge import BridgeService
from shop.services.consent import ConsentService
from shop.services.medaccess import MedAccessService
from shop.services.user import UserService

URI = 'postgresql+asyncpg://shop:secret@localhost:5432/shop'


def _svc(s, ks, payload, link_id=None, key_id=None):
    return MedAccessService(session=s, bridge=BridgeService(session=s, keys=ks),
                            payload=payload, link_id=link_id, key_id=key_id)


async def _mkuser(s, place_id, email):
    person = t.Person(name={'last': email}, sex=True,
                      birthdate=datetime.date(1980, 5, 1), birth_place=place_id)
    s.add(person); await s.commit()
    user = await UserService(session=s).create(UserCreate(
        person=person.id, contact=Contact(email=email), password='correct-horse'))
    return person.id, user.id


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
        owner_person, owner_uid = await _mkuser(s, place_id, 'owner@x.com')
        _, doc_a = await _mkuser(s, place_id, 'doc-a@x.com')
        _, doc_b = await _mkuser(s, place_id, 'doc-b@x.com')

    ks = DbKeyService(Sess)
    owner = TokenPayload(sub=owner_uid)
    key_id = f'patient:{owner_uid}'

    # --- согласие врача A одобрено ДО enroll: ключа нет, грант отложен ---
    async with Sess() as s:
        c_a = await ConsentService(session=s, keys=ks).request(ConsentRequest(
            subject_table='person', subject_id=owner_person, scope='medical',
            reason='лечащий врач'), TokenPayload(sub=doc_a))
    async with Sess() as s:
        await ConsentService(session=s, keys=ks).decide(
            c_a.id, True, ConsentDecision(until=None), owner)
    print('[ok] согласие A одобрено до enroll (ключа ещё нет)')

    # --- enroll: выпуск моста + re-sync ранее одобренных согласий ---
    async with Sess() as s:
        await _svc(s, ks, owner).enroll()
    async with Sess() as s:
        grants = await _svc(s, ks, TokenPayload(sub=doc_a)).grants()
    assert len(grants) == 1 and grants[0]['key_id'] == key_id, grants
    link_id = grants[0]['link_id']
    async with Sess() as s:
        props = await _svc(s, ks, TokenPayload(sub=doc_a), link_id, key_id).properties()
    assert props == [], props
    print('[ok] enroll догрантил согласие A: врач резолвит мост (re-sync)')

    # --- согласие врача B одобрено ПОСЛЕ enroll: грант сразу ---
    async with Sess() as s:
        c_b = await ConsentService(session=s, keys=ks).request(ConsentRequest(
            subject_table='person', subject_id=owner_person, scope='medical',
            reason='консультант'), TokenPayload(sub=doc_b))
    async with Sess() as s:
        await ConsentService(session=s, keys=ks).decide(
            c_b.id, True, ConsentDecision(until=None), owner)
    async with Sess() as s:
        props = await _svc(s, ks, TokenPayload(sub=doc_b), link_id, key_id).properties()
    assert props == [], props
    print('[ok] approve после enroll: врач B получил доступ сразу')

    # --- отзыв согласия A закрывает ACL; кэш моста чистим руками (известная цена TTL) ---
    async with Sess() as s:
        await ConsentService(session=s, keys=ks).revoke(c_a.id, owner)
    await get_cache().delete(f'bridge:{link_id}:{key_id}:{doc_a}')
    async with Sess() as s:
        with pytest.raises(HTTPException) as ei:
            await _svc(s, ks, TokenPayload(sub=doc_a), link_id, key_id).properties()
        assert ei.value.status_code == 403
    print('[ok] revoke согласия A -> 403 (ACL закрыт); врач B не задет')

    async with Sess() as s:
        props = await _svc(s, ks, TokenPayload(sub=doc_b), link_id, key_id).properties()
    assert props == [], props

    await eng.dispose()
    print('\nТЕСТ СВЯЗКИ CONSENT -> KEYSERVICE ПРОЙДЕН')
