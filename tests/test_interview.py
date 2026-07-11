"""Интервью (сбор анамнеза по anamnez.md): полный проход протокола —
жалоба -> цикл симптомов (11 слотов, связанные в очередь) -> ROS (позитив
возвращает в цикл) -> анамнез жизни -> полнота -> резюме -> подтверждение;
отдельно — красный флаг прерывает опрос (emergency) и resume.
Требует Redis (owner-сессия)."""
import datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

import shop.tables as t
from shop.keyservice import DbKeyService
from shop.medical_seed import SYMPTOM_SCHEMA, seed_medical
from shop.models.auth import TokenPayload
from shop.models.medical import EpisodeIn
from shop.models.user import Contact, UserCreate
from shop.services.bridge import BridgeService
from shop.services.interview import HISTORY_SECTIONS
from shop.services.medaccess import MedAccessService
from shop.services.user import UserService

URI = 'postgresql+asyncpg://shop:secret@localhost:5432/shop'
SLOTS = [s['code'] for s in SYMPTOM_SCHEMA]


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
        person = t.Person(name={'last': 'Иванов'}, sex=True,
                          birthdate=datetime.date(1980, 5, 1), birth_place=place.id)
        s.add(person); await s.commit()
        user = await UserService(session=s).create(UserCreate(
            person=person.id, contact=Contact(email='p@x.com'), password='correct-horse'))
        user_id, person_id = user.id, person.id

    ks = DbKeyService(Sess)
    await ks.create_key('escrow')
    key_id = f'patient:{user_id}'
    await ks.create_key(key_id); await ks.grant(key_id, str(user_id))
    async with Sess() as s:
        await BridgeService(session=s, keys=ks).create_link(
            'person', person_id, 'medical', groups={key_id: person_id})
    payload = TokenPayload(sub=user_id)
    async with Sess() as s:
        await _svc(s, ks, payload).open_session()

    async def episode(code):
        async with Sess() as s:
            ep = await _svc(s, ks, payload).open_episode(
                EpisodeIn(category=ids['illness'], code=code, name=code))
            return ep.id

    async def ask(eid, body):
        async with Sess() as s:
            return await _svc(s, ks, payload).interview_answer(eid, body)

    async def run_slots(eid, associations=None, severity=3):
        """Прогоняет 11 слотов текущего симптома; возвращает последний ответ."""
        r = None
        for slot in SLOTS:
            value = {'severity': severity,
                     'associations': associations or []}.get(slot, f'ответ:{slot}')
            r = await ask(eid, {'value': value})
            if r['state'] == 'emergency':
                return r
        return r

    # ================= Сценарий A: полный проход до подтверждения =========
    eid = await episode('ep-full')
    async with Sess() as s:
        r = await _svc(s, ks, payload).interview_open(eid)
    assert r['state'] == 'complaint', r
    # идемпотентность открытия
    async with Sess() as s:
        assert (await _svc(s, ks, payload).interview_open(eid))['state'] == 'complaint'
    print('[ok] интервью открыто (идемпотентно), стартовое состояние complaint')

    r = await ask(eid, {'symptom': 'headache'})
    assert r['state'] == 'symptom' and r['question']['symptom'] == 'headache'
    assert r['question']['slot'] == 'onset'
    print('[ok] главная жалоба принята, цикл уточнения начат (слот onset)')

    # 11 слотов головной боли; associations добавляет тошноту в очередь
    r = await run_slots(eid, associations=['nausea'])
    assert r['state'] == 'symptom' and r['question']['symptom'] == 'nausea', r
    print('[ok] связанный симптом ушёл в очередь и взят в разбор (рекурсия жалоб)')

    r = await run_slots(eid)                      # тошнота без новых связей
    assert r['state'] == 'ros', r
    print('[ok] очередь пуста -> обзор систем (ROS)')

    # ROS: все системы чистые, кроме msk -> новый симптом weakness
    while r['state'] == 'ros':
        system = r['question']['system']
        if system == 'msk':
            r = await ask(eid, {'positive': True, 'symptoms': ['weakness']})
            assert r['state'] == 'symptom' and r['question']['symptom'] == 'weakness'
            print('[ok] позитивная система вернула в цикл симптомов')
            r = await run_slots(eid)
        else:
            r = await ask(eid, {'positive': False})
    assert r['state'] == 'history', r
    assert set(r['done']) == {'headache', 'nausea', 'weakness'}
    print('[ok] ROS обойдён (9 систем), три симптома разобраны -> анамнез жизни')

    # анамнез жизни: лекарство + наследственность, остальное — явный «нет»
    items = {'medication': [{'code': 'aspirin', 'dose': '100мг'}],
             'heredity': [{'code': 'diabetes_family'}]}
    for section in HISTORY_SECTIONS:
        assert r['state'] == 'history' and r['question']['section'] == section, r
        r = await ask(eid, {'items': items.get(section, [])})
    # все секции полноты закрыты (пустые — значимым отрицанием) -> сразу резюме
    assert r['state'] == 'summary', r
    assert r['summary']['chief_complaint'] == 'headache'
    assert set(r['summary']['symptoms']) == {'headache', 'nausea', 'weakness'}
    assert r['summary']['symptoms']['headache']['severity'] == 3
    assert r['summary']['ros']['cardio'] == 'clear'
    print('[ok] полнота закрыта -> резюме собрано (жалоба, слоты, ROS)')

    # «да, ещё...» возвращает в цикл; затем подтверждение
    r = await ask(eid, {'more': ['dizziness']})
    assert r['state'] == 'symptom' and r['question']['symptom'] == 'dizziness'
    r = await run_slots(eid)
    assert r['state'] == 'summary'
    r = await ask(eid, {'confirmed': True})
    assert r['state'] == 'confirmed', r
    print('[ok] «да, ещё...» -> разбор -> подтверждение пациентом (confirmed)')

    # подтверждённое резюме зафиксировано на эпизоде; ответы больше не принимаются
    async with Sess() as s:
        row = (await s.execute(select(t.Property).where(
            t.Property.table == 'entity', t.Property.objectid == eid,
            t.Property.code == 'summary'))).scalars().one()
        assert row.value['confirmed'] is True
    with pytest.raises(HTTPException) as ei:
        await ask(eid, {'symptom': 'cough'})
    assert ei.value.status_code == 409
    print('[ok] резюме на эпизоде, confirmed — терминальное состояние')

    # полнота эпизода: пробелов нет (интервью закрыло все секции)
    async with Sess() as s:
        a = await _svc(s, ks, payload).assess(eid)
    assert a['gaps'] == [], a
    print('[ok] assess: пробелов после интервью нет')

    # ================= Сценарий B: красный флаг прерывает опрос ============
    eid2 = await episode('ep-acs')
    async with Sess() as s:
        await _svc(s, ks, payload).interview_open(eid2)
    await ask(eid2, {'symptom': 'chest_pain'})
    r = await run_slots(eid2, associations=['dyspnea'], severity=8)
    assert r['question']['symptom'] == 'dyspnea'
    r = await ask(eid2, {'value': 'внезапно'})     # первый же ответ по одышке
    assert r['state'] == 'emergency' and r['alerts'] == ['acs'], r
    with pytest.raises(HTTPException) as ei:
        await ask(eid2, {'value': 'ещё ответ'})    # опрос прерван
    assert ei.value.status_code == 409
    print('[ok] красный флаг acs -> emergency, опрос прерван')

    r = await ask(eid2, {'resume': True})
    assert r['state'] == 'symptom' and r['question']['symptom'] == 'dyspnea'
    print('[ok] resume после оказания помощи — опрос продолжен с того же места')

    await eng.dispose()
    print('\nТЕСТ ИНТЕРВЬЮ (ПРОТОКОЛ АНАМНЕЗА) ПРОЙДЕН')
