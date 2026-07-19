"""Питание: приём пищи -> оценка консумером (заглушка без Gemini), транзитное
фото удаляется после оценки; суточная норма ставится лениво и не дублируется
при поллинге. Требует Redis (owner-сессия)."""
import datetime

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
from shop.services.user import UserService
from shop.settings import settings
from conftest import drain

URI = 'postgresql+asyncpg://shop:secret@localhost:5432/shop'
DAY = datetime.date.today().isoformat()


def _svc(s, ks, payload):
    return MedAccessService(session=s, bridge=BridgeService(session=s, keys=ks), payload=payload)


async def test_main():
    settings.google_api_key = None                # заглушки: без сети/Gemini
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
        person = t.Person(name={'last': 'Едоков'}, sex=True,
                          birthdate=datetime.date(1988, 4, 4))
        s.add(person); await s.commit()
        user = await UserService(session=s).create(UserCreate(
            person=person.id, contact=Contact(email='eat@x.com'), password='correct-horse'))
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

    # --- приём пищи с «фото»: запись estimating + транзитный блоб ---
    async with Sess() as s:
        meal = await _svc(s, ks, payload).add_meal(
            DAY, 'яблоко', b'\x89PNG fake photo bytes', 'image/png')
    assert meal.value['status'] == 'estimating'
    async with Sess() as s:
        blobs = (await s.execute(select(func.count()).select_from(t.Blob))).scalar_one()
    assert blobs == 1, blobs
    print('[ok] приём создан (estimating), фото легло транзитным блобом')

    # --- консумер: оценка (заглушка) + удаление транзитного фото ---
    await drain(Sess)
    async with Sess() as s:
        row = await s.get(t.Property, meal.id)
        blobs = (await s.execute(select(func.count()).select_from(t.Blob))).scalar_one()
    assert row.value['status'] == 'done' and 'totals' in row.value, row.value
    assert blobs == 0, 'транзитное фото должно быть удалено после оценки'
    print('[ok] оценка консумером; фото НЕ хранится (блоб удалён)')

    # --- норма: лениво ставится, pending не дублирует задач при поллинге ---
    async with Sess() as s:
        n1 = await _svc(s, ks, payload).nutrition(DAY)
    assert n1['norm']['status'] == 'pending'
    async with Sess() as s:
        pend = (await s.execute(select(func.count()).select_from(t.Outbox)
                .where(t.Outbox.processed.is_(None)))).scalar_one()
    async with Sess() as s:
        await _svc(s, ks, payload).nutrition(DAY)      # поллинг
    async with Sess() as s:
        pend2 = (await s.execute(select(func.count()).select_from(t.Outbox)
                 .where(t.Outbox.processed.is_(None)))).scalar_one()
    assert pend == pend2 == 1, (pend, pend2)
    print('[ok] норма поставлена лениво; повторный запрос не плодит задач')

    await drain(Sess)
    async with Sess() as s:
        n2 = await _svc(s, ks, payload).nutrition(DAY)
    assert n2['norm']['status'] == 'done' and n2['norm']['kcal'] > 0, n2['norm']
    assert n2['totals']['kcal'] == 0                   # заглушка еды без позиций
    print('[ok] норма пересчитана (заглушка), суммы дня считаются')

    await eng.dispose()
    print('\nТЕСТ ПИТАНИЯ ПРОЙДЕН')
