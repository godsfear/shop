"""API Property, Слой A (owner-сессия): разворот моста -> Redis-сессия -> скоуп псевдонима.

Требует Redis (сессия — состояние в Redis). Проверяет: без сессии 401, открытие
разворачивает мост, чтение/запись скоупятся на псевдоним, проекция не раскрывает
objectid (псевдоним), закрытие отзывает доступ."""
import datetime
import os

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

import shop.tables as t
from shop.keyservice import DbKeyService
from shop.medical_seed import seed_medical
from shop.models.auth import TokenPayload
from shop.models.medical import MedPropertyIn, MedPropertyOut
from shop.models.property import PropertyCreate
from shop.models.user import UserCreate, Contact
from shop.services.bridge import BridgeService
from shop.services.medaccess import MedAccessService
from shop.services.property import PropertyService
from shop.services.user import UserService

URI = os.getenv('TEST_DATABASE_URI', 'postgresql+asyncpg://shop:secret@localhost:5432/shop')


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
        ids = await seed_medical(s)
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

    # ключ пациента: MVP-стенд-ин клиентской owner-крипты (сервер-резолвимый ключ)
    ks = DbKeyService(Sess)
    await ks.create_key('escrow')                       # create_link всегда пишет escrow-копию
    key_id = f'patient:{user_id}'
    await ks.create_key(key_id); await ks.grant(key_id, str(user_id))

    async with Sess() as s:
        link, pseudonym_id = await BridgeService(session=s, keys=ks).create_link(
            'person', person_id, 'medical', groups={key_id: person_id})
        link_id = link.id
    # предзаписанный факт на псевдониме (как будто заведён ранее)
    async with Sess() as s:
        await PropertyService(session=s).create(PropertyCreate(
            category=None, code='allergy', table='pseudonym', objectid=pseudonym_id,
            value={'agent': 'пенициллин', 'status': 'present'}))

    payload = TokenPayload(sub=user_id)

    # --- без сессии: 401 ---
    async with Sess() as s:
        with pytest.raises(HTTPException) as ei:
            await _svc(s, ks, payload).properties()
        assert ei.value.status_code == 401
    print('[ok] без сессии — 401')

    # --- открыть сессию: owner-автодискавери моста по JWT -> псевдоним в Redis ---
    async with Sess() as s:
        ttl = await _svc(s, ks, payload).open_session()
    assert ttl > 0

    # --- читать свои данные (скоуп сессии) + проекция скрывает псевдоним ---
    async with Sess() as s:
        props = await _svc(s, ks, payload).properties()
    assert len(props) == 1 and props[0].code == 'allergy', props
    out = MedPropertyOut.model_validate(props[0])
    assert not hasattr(out, 'objectid'), 'проекция не должна раскрывать псевдоним'
    print('[ok] сессия открыта, данные видны, objectid (псевдоним) скрыт')

    # --- запись факта: сервер ставит objectid = псевдоним сессии ---
    async with Sess() as s:
        created = await _svc(s, ks, payload).add_property(
            MedPropertyIn(code='symptom', value={'text': 'кашель'}))
    assert created.objectid == pseudonym_id, 'сервер обязан скоупить на псевдоним сессии'
    async with Sess() as s:
        with pytest.raises(HTTPException) as ei:
            await _svc(s, ks, payload).add_property(
                MedPropertyIn(code='symptom', value={'text': 'повтор'}))
        assert ei.value.status_code == 409 and ei.value.detail == 'property_exists'
    async with Sess() as s:
        props = await _svc(s, ks, payload).properties()
    assert {p.code for p in props} == {'allergy', 'symptom'}, props
    print('[ok] запись факта скоупится на псевдоним сессии, дубли отклоняются')

    # --- профильный показатель и ситуационные замеры строго разделены ---
    async with Sess() as s:
        svc = _svc(s, ks, payload)
        pressure = await svc.add_property(MedPropertyIn(
            category=ids['vital'], code='blood_pressure', name='Давление',
            value={'value': '120/80', 'unit': 'мм рт. ст.'}))
    assert pressure.value['source'] == 'profile'
    async with Sess() as s:
        svc = _svc(s, ks, payload)
        await svc.add_diary_entry(MedPropertyIn(
            category=ids['vital'], code='blood_pressure', name='Давление',
            value={'value': '135/90', 'unit': 'мм рт. ст.'}))
        await svc.add_diary_entry(MedPropertyIn(
            category=ids['vital'], code='blood_pressure', name='Давление',
            value={'value': '130/85', 'unit': 'мм рт. ст.'}))
    async with Sess() as s:
        svc = _svc(s, ks, payload)
        profile_vitals = await svc.properties(category=ids['vital'])
        diary = await svc.diary()
    assert [(p.code, p.value['value']) for p in profile_vitals] == [
        ('blood_pressure', '120/80')
    ]
    assert [p.value['value'] for p in diary] == ['130/85', '135/90']

    # Повторное профильное значение обновляет тот же id и попадает в историю.
    async with Sess() as s:
        svc = _svc(s, ks, payload)
        updated = await svc.update_property(
            pressure.id, {'value': '125/85', 'unit': 'мм рт. ст.'})
        history = await svc.property_history(updated.id)
    assert updated.id == pressure.id
    assert [p.value['value'] for p in history] == ['120/80', '125/85']
    assert all(p.value['source'] == 'profile' for p in history)

    # Профильный vital нельзя закрыть, но дневниковый замер — можно.
    async with Sess() as s:
        svc = _svc(s, ks, payload)
        with pytest.raises(HTTPException) as ei:
            await svc.close_property(pressure.id)
        assert ei.value.status_code == 409
        await svc.close_property(diary[0].id)
        assert len(await svc.diary()) == 1

    # Даже конкурентный/прямой обход сервисной проверки упирается в индекс БД;
    # множественные source=diary выше при этом разрешены.
    async with Sess() as s:
        s.add(t.Property(
            category=ids['vital'], code='blood_pressure', name='Давление',
            table='pseudonym', objectid=pseudonym_id,
            value={'value': '140/90', 'unit': 'мм рт. ст.', 'source': 'profile'}))
        with pytest.raises(IntegrityError):
            await s.commit()
        await s.rollback()
    print('[ok] профильный vital единственный; дневниковые замеры отдельны и множественны')

    # --- закрыть сессию -> снова 401 ---
    async with Sess() as s:
        svc = _svc(s, ks, payload)
        await svc.close_session()
        with pytest.raises(HTTPException) as ei:
            await svc.properties()
        assert ei.value.status_code == 401
    print('[ok] закрытие сессии отзывает доступ')

    await eng.dispose()
    print('\nТЕСТ СЕССИИ ПАЦИЕНТА (Слой A) ПРОЙДЕН')
