"""Сон: запись ночи -> запись в журнал + оценка сна за период консумером
(заглушка без Gemini). Оценка ставится один раз при записи (pending),
консумер дозаполняет (done). Требует Redis (owner-сессия)."""
import datetime
import os

from sqlalchemy import select, func, text
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

import shop.tables as t
from shop.keyservice import DbKeyService
from shop.medical_seed import seed_medical
from shop.models.auth import TokenPayload
from shop.models.user import Contact, UserCreate
from shop.services.bridge import BridgeService
from shop.services.medaccess import MedAccessService
from shop.services.sleep import ASSESS_CODE
from shop.services.user import UserService
from shop.settings import settings
from conftest import drain

URI = os.getenv(
    'TEST_DATABASE_URI', 'postgresql+asyncpg://shop:secret@localhost:5432/shop')
DAY = datetime.date.today().isoformat()


def _svc(s, ks, payload):
    return MedAccessService(session=s, bridge=BridgeService(session=s, keys=ks), payload=payload)


async def test_main():
    settings.google_api_key = None                # заглушка: без сети/Gemini
    eng = create_async_engine(URI, poolclass=NullPool)
    async with eng.begin() as conn:
        await conn.execute(text('DROP SCHEMA public CASCADE'))
        await conn.execute(text('CREATE SCHEMA public'))
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS postgis'))
        await conn.run_sync(t.Root.metadata.create_all)
    Sess = async_sessionmaker(eng, expire_on_commit=False)

    async with Sess() as s:
        await seed_medical(s)
    async with Sess() as s:
        person = t.Person(name={'last': 'Сонин'}, sex=True,
                          birthdate=datetime.date(1985, 2, 2))
        s.add(person); await s.commit()
        user = await UserService(session=s).create(UserCreate(
            person=person.id, contact=Contact(email='sleep@x.com'), password='correct-horse'))
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

    # --- запись ночи: попадает в журнал + ставит оценку (pending) + событие ---
    async with Sess() as s:
        await _svc(s, ks, payload).add_sleep(DAY, {
            'bedtime': '23:30', 'getup': '07:00', 'total': '07:00',
            'efficiency': 91, 'wellbeing': 7})
    async with Sess() as s:
        j = await _svc(s, ks, payload).sleep_journal()
    assert len(j['entries']) == 1, j['entries']
    assert j['assessment']['status'] == 'pending', j['assessment']
    async with Sess() as s:
        pend = (await s.execute(select(func.count()).select_from(t.Outbox)
                .where(t.Outbox.processed.is_(None),
                       t.Outbox.topic == 'sleep.assess'))).scalar_one()
    assert pend == 1, pend
    print('[ok] ночь в журнале; оценка pending; задача поставлена (1 событие)')

    # --- консумер: оценка за период дозаполняется (заглушка без Gemini) ---
    await drain(Sess)
    async with Sess() as s:
        j2 = await _svc(s, ks, payload).sleep_journal()
    assert j2['assessment']['status'] == 'done', j2['assessment']
    assert j2['assessment'].get('summary'), j2['assessment']
    assert j2['assessment'].get('current_summary'), j2['assessment']
    assert j2['assessment'].get('assessed_day') == DAY, j2['assessment']
    assert j2['assessment'].get('nights') == 1, j2['assessment']
    print('[ok] оценка сна дозаполнена консумером (заглушка)')

    # Старая оценка без current-проекции пересчитывается один раз при запросе
    # дашборда за текущий день; повторный GET не плодит второе событие.
    async with Sess() as s:
        row = (await s.execute(select(t.Property).where(
            t.Property.code == ASSESS_CODE,
            t.Property.version_of.is_(None)))).scalars().one()
        legacy = dict(row.value)
        legacy.pop('assessed_day', None)
        legacy.pop('current_quality', None)
        legacy.pop('current_summary', None)
        row.value = legacy
        await s.commit()
    async with Sess() as s:
        legacy_journal = await _svc(s, ks, payload).sleep_journal(current_day=DAY)
    assert legacy_journal['assessment']['status'] == 'pending'
    assert legacy_journal['assessment']['assessed_day'] == DAY
    assert 'current_summary' not in legacy_journal['assessment']
    async with Sess() as s:
        await _svc(s, ks, payload).sleep_journal(current_day=DAY)
        pending_current = (await s.execute(select(func.count()).select_from(t.Outbox)
                           .where(t.Outbox.processed.is_(None),
                                  t.Outbox.topic == 'sleep.assess'))).scalar_one()
    assert pending_current == 1
    await drain(Sess)
    async with Sess() as s:
        current = await _svc(s, ks, payload).sleep_journal(current_day=DAY)
    assert current['assessment'].get('current_summary')
    print('[ok] старая оценка лениво дополнена current-проекцией без дублей')

    # --- запись второй ночи не плодит вторую строку оценки (versioned_update) ---
    async with Sess() as s:
        await _svc(s, ks, payload).add_sleep(DAY, {'total': '06:30', 'wellbeing': 6})
    await drain(Sess)
    async with Sess() as s:
        assess_rows = (await s.execute(select(func.count()).select_from(t.Property)
                       .where(t.Property.table == 'pseudonym',
                              t.Property.code == ASSESS_CODE,
                              t.Property.version_of.is_(None)))).scalar_one()
    assert assess_rows == 1, assess_rows
    print('[ok] оценка одна на псевдоним (обновляется, не дублируется)')

    await eng.dispose()
    print('\nТЕСТ СНА ПРОЙДЕН')
