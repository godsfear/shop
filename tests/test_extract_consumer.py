"""ИИ-консумер (заглушка): документ через outbox 'data.extract' -> Property(source='ai')."""
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

import shop.tables as t
from shop.medical_seed import seed_medical
from shop.models.entity import EntityCreate
from shop.services.entity import EntityService
from shop.services.files import FileStore
from shop.services.extract import request_extract
from shop.settings import settings
from conftest import drain

URI = 'postgresql+asyncpg://shop:secret@localhost:5432/shop'


async def test_main():
    # держим детерминированную заглушку: тест не должен ходить в Gemini (сеть/квота),
    # даже если GOOGLE_API_KEY задан в .env
    settings.google_api_key = None
    eng = create_async_engine(URI)
    async with eng.begin() as conn:
        await conn.execute(text('DROP SCHEMA public CASCADE'))
        await conn.execute(text('CREATE SCHEMA public'))
        await conn.run_sync(t.Root.metadata.create_all)
    Sess = async_sessionmaker(eng, expire_on_commit=False)

    async with Sess() as s:
        ids = await seed_medical(s)
    async with Sess() as s:
        pseud = t.Pseudonym(); s.add(pseud); await s.commit()
        pid = pseud.id
    async with Sess() as s:
        ep = await EntityService(session=s).create(EntityCreate(
            category=ids['illness'], code='ep-1', name='Эпизод',
            table='pseudonym', objectid=pid))
        eid = ep.id

    blob = b'%PDF fake lab report ' + b'z' * 300
    async with Sess() as s:
        ref = await FileStore(session=s).put(blob)

    # прикрепить документ (Data) + поставить в очередь на разбор — одна транзакция
    async with Sess() as s:
        s.add(t.Data(category=ids['analysis'], code='lab', name='Лаборатория',
                     table='entity', objectid=eid, hash=ref['hash'], algorithm=ref['algorithm']))
        request_extract(s, ref['hash'], 'entity', eid, 'application/pdf')
        await s.commit()

    await drain(Sess)  # консумер разбирает событие

    async with Sess() as s:
        props = (await s.execute(select(t.Property).where(
            t.Property.objectid == eid, t.Property.code == 'summary'))).scalars().all()
    assert len(props) == 1, props
    p = props[0]
    assert p.value['source'] == 'ai', p.value
    assert str(len(blob)) in p.value['text'], p.value        # заглушка видела реальные байты
    print('[ok] data.extract -> Property(summary, source=ai) на эпизоде')

    # событие помечено обработанным
    async with Sess() as s:
        pending = (await s.execute(select(t.Outbox).where(
            t.Outbox.processed.is_(None)))).scalars().all()
    assert pending == [], pending
    print('[ok] событие outbox обработано')

    await eng.dispose()
    print('\nТЕСТ ИИ-КОНСУМЕРА ПРОЙДЕН')
