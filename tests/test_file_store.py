"""Файлохранилище: контент-адресация (дедуп), roundtrip, привязка к эпизоду как Data."""
from sqlalchemy import text, select, func
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

import shop.tables as t
from shop.medical_seed import seed_medical
from shop.models.entity import EntityCreate
from shop.services.entity import EntityService
from shop.services.files import FileStore

URI = 'postgresql+asyncpg://shop:secret@localhost:5432/shop'


async def test_main():
    eng = create_async_engine(URI, poolclass=NullPool)
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

    blob = b'%PDF-1.4 fake blood test result\n' + b'x' * 500

    # --- put + roundtrip ---
    async with Sess() as s:
        ref = await FileStore(session=s).put(blob)
        await s.commit()
    assert ref['algorithm'] == 'sha256' and ref['size'] == len(blob)
    async with Sess() as s:
        got = await FileStore(session=s).get(ref['hash'])
    assert got == blob
    print('[ok] put/get roundtrip')

    # --- дедуп: те же байты -> один блоб ---
    async with Sess() as s:
        ref2 = await FileStore(session=s).put(blob)
        await s.commit()
    assert ref2['hash'] == ref['hash']
    async with Sess() as s:
        n = (await s.execute(select(func.count()).select_from(t.Blob))).scalar_one()
    assert n == 1, n
    print('[ok] дедуп: одинаковый контент = один блоб')

    # --- привязка анализа к эпизоду: Data(метаданные + hash) на эпизоде псевдонима ---
    async with Sess() as s:
        ep = await EntityService(session=s).create(EntityCreate(
            category=ids['illness'], code='ep-1', name='Эпизод',
            table='pseudonym', objectid=pid))
        eid = ep.id
    async with Sess() as s:
        s.add(t.Data(category=ids['analysis'], code='cbc', name='Общий анализ крови',
                     table='entity', objectid=eid,
                     hash=ref['hash'], algorithm=ref['algorithm']))
        await s.commit()
    async with Sess() as s:
        d = (await s.execute(select(t.Data).where(t.Data.objectid == eid))).scalar_one()
        content = await FileStore(session=s).get(d.hash)
    assert content == blob
    print('[ok] Data(метаданные) на эпизоде -> контент по hash из FileStore')

    # --- exists ---
    async with Sess() as s:
        fs = FileStore(session=s)
        assert await fs.exists(ref['hash'])
        assert not await fs.exists('0' * 64)
    print('[ok] exists')

    # --- домен Data — operational (унаследован от эпизода); блоб — вне реестра ---
    async with Sess() as s:
        dom = (await s.execute(select(t.ObjectRegistry.domain).join(
            t.Data, t.Data.id == t.ObjectRegistry.id).where(
            t.Data.objectid == eid))).scalar_one()
    assert dom == 'operational', dom
    async with Sess() as s:
        reg = (await s.execute(select(func.count()).select_from(t.ObjectRegistry).where(
            t.ObjectRegistry.table == 'blob'))).scalar_one()
    assert reg == 0, reg
    print('[ok] Data operational; блоб обезличен (вне реестра объектов)')

    await eng.dispose()
    print('\nТЕСТ ФАЙЛОХРАНИЛИЩА ПРОЙДЕН')
