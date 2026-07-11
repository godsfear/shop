"""API `/me`, эпизод-скоуп + assess: открытие/список эпизодов, симптомы на эпизоде,
FSM-переход, полнота+флаги (Фаза 3) — всё через сессию, со скоупом на псевдоним.
Ключевое: ворота владения — чужой episode_id -> 404. Требует Redis (сессия)."""
import datetime
import tempfile

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

import shop.tables as t
from shop.keyservice import StubKeyService
from shop.medical_seed import seed_medical
from shop.models.auth import TokenPayload
from shop.models.medical import EpisodeIn, EpisodeOut, MedPropertyIn
from shop.models.user import UserCreate, Contact
from shop.services.bridge import BridgeService
from shop.services.medaccess import MedAccessService
from shop.services.user import UserService

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

    ks = StubKeyService(tempfile.mkdtemp())
    ks.create_key('escrow')
    key_id = f'patient:{user_id}'
    ks.create_key(key_id); ks.grant(key_id, str(user_id))
    async with Sess() as s:
        link, pseudonym_id = await BridgeService(session=s, keys=ks).create_link(
            'person', person_id, 'medical', groups={key_id: person_id})
        link_id = link.id

    payload = TokenPayload(sub=user_id)
    async with Sess() as s:
        await _svc(s, ks, payload).open_session()

    # --- открыть эпизод + список (проекция прячет objectid) ---
    async with Sess() as s:
        ep = await _svc(s, ks, payload).open_episode(
            EpisodeIn(category=ids['illness'], code='ep-1', name='ОРВИ'))
        eid = ep.id
    assert ep.objectid == pseudonym_id, 'эпизод обязан висеть на псевдониме сессии'
    async with Sess() as s:
        eps = await _svc(s, ks, payload).episodes()
    assert len(eps) == 1 and eps[0].id == eid
    assert not hasattr(EpisodeOut.model_validate(eps[0]), 'objectid')
    print('[ok] эпизод открыт на псевдониме, список отдаёт без objectid')

    # --- симптомы на эпизоде (боль в груди + одышка present) ---
    async with Sess() as s:
        svc = _svc(s, ks, payload)
        await svc.add_episode_property(eid, MedPropertyIn(
            category=ids['symptom'], code='chest_pain',
            value={'status': 'present', 'source': 'self'}))
        await svc.add_episode_property(eid, MedPropertyIn(
            category=ids['symptom'], code='dyspnea',
            value={'status': 'present', 'source': 'self'}))
    async with Sess() as s:
        syms = await _svc(s, ks, payload).episode_properties(eid, category=ids['symptom'])
    assert {p.code for p in syms} == {'chest_pain', 'dyspnea'}, syms
    print('[ok] симптомы записаны и читаются в скоупе эпизода')

    # --- FSM-переход ---
    async with Sess() as s:
        st = await _svc(s, ks, payload).transition(eid, 'diagnose')
    assert st['state'] == 'diagnosis', st
    print('[ok] FSM-переход anamnesis->diagnosis через /me')

    # --- assess (Фаза 3): красный флаг acs + пустые пациентские секции ---
    async with Sess() as s:
        r = await _svc(s, ks, payload).assess(eid)
    assert r['alerts'] == ['acs'], r
    assert set(r['gaps']) == {'medication', 'allergy', 'heredity'}, r
    print('[ok] assess через /me: флаг acs + пробелы секций')

    # --- ВОРОТА: чужой эпизод -> 404 ---
    async with Sess() as s:
        foreign = t.Pseudonym(); s.add(foreign); await s.commit()
        fep = t.Entity(category=ids['illness'], code='ep-x', name='Чужой',
                       table='pseudonym', objectid=foreign.id)
        s.add(fep); await s.commit()
        foreign_eid = fep.id
    async with Sess() as s:
        with pytest.raises(HTTPException) as ei:
            await _svc(s, ks, payload).episode_properties(foreign_eid)
        assert ei.value.status_code == 404
    print('[ok] ВОРОТА: чужой episode_id -> 404 (граница псевдонима держит)')

    # --- эпизод только из эпизодного концепта (у symptom нет value.fsm) -> 400 ---
    async with Sess() as s:
        with pytest.raises(HTTPException) as ei:
            await _svc(s, ks, payload).open_episode(
                EpisodeIn(category=ids['symptom'], code='bad', name='не эпизод'))
        assert ei.value.status_code == 400
    print('[ok] open_episode с неэпизодной категорией -> 400')

    # --- код state зарезервирован FSM: подделка состояния отбита моделью ---
    with pytest.raises(ValidationError):
        MedPropertyIn(code='state', value={'state': 'recovered'})
    print('[ok] MedPropertyIn(code=state) -> ValidationError (в обход FSM нельзя)')

    await eng.dispose()
    print('\nТЕСТ ЭПИЗОД-СКОУПА ПРОЙДЕН')
