"""Интернационализация: переводы контента, upsert версионно, trigram-поиск по локали."""
import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

import shop.tables as t
from shop.models.translation import TranslationSearch, TranslationSet
from shop.services.translation import TranslationService
from shop.versioning import versions

URI = 'postgresql+asyncpg://shop:secret@localhost:5432/shop'


async def test_main():
    eng = create_async_engine(URI)
    async with eng.begin() as conn:
        await conn.execute(text('DROP SCHEMA public CASCADE'))
        await conn.execute(text('CREATE SCHEMA public'))
        await conn.run_sync(t.Root.metadata.create_all)  # расширения — before_create
    Sess = async_sessionmaker(eng, expire_on_commit=False)

    # локали + каталог + товар (entity на категории-каталоге, домен reference)
    async with Sess() as s:
        ru = t.Language(code='ru', iso='ru', name='Русский')
        de = t.Language(code='de', iso='de', name='Deutsch')
        catalog = t.Category(code='catalog', name='Каталог')
        s.add(ru); s.add(de); s.add(catalog)
        await s.flush()
        goods = t.Category(code='goods', name='Товары', category=catalog.id)
        s.add(goods); await s.flush()
        product = t.Entity(category=goods.id, code='shampoo-01', name='Шампунь',
                           table='category', objectid=catalog.id)
        s.add(product); await s.commit()
        pid = product.id

    # --- upsert переводов + выдача по локали ---
    async with Sess() as s:
        svc = TranslationService(session=s)
        await svc.set_translations('entity', pid, [
            TranslationSet(language='ru', field='name', content='Шампунь восстанавливающий'),
            TranslationSet(language='de', field='name', content='Aufbau-Shampoo'),
            TranslationSet(language='de', field='description', content='Für strapaziertes Haar'),
        ])
        got = await svc.get_translations('entity', pid, 'de')
        assert got == {'name': 'Aufbau-Shampoo', 'description': 'Für strapaziertes Haar'}
    print('[ok] upsert переводов и выдача по локали de')

    # --- повторный upsert = версионная правка, активный один ---
    async with Sess() as s:
        svc = TranslationService(session=s)
        rows = await svc.set_translations('entity', pid, [
            TranslationSet(language='de', field='name', content='Reparatur-Shampoo')])
        hist = await versions(s, t.Translation, rows[0].id)
        assert [h.content for h in hist] == ['Aufbau-Shampoo']
        got = await svc.get_translations('entity', pid, 'de')
        assert got['name'] == 'Reparatur-Shampoo'
    print('[ok] повторный upsert: правка версионно, история хранит прежний перевод')

    # --- поиск по локали (trigram, регистронезависимо, подстрока) ---
    async with Sess() as s:
        svc = TranslationService(session=s)
        hits = await svc.search(TranslationSearch(q='shampoo', locale='de'))
        assert len(hits) == 1 and hits[0].objectid == pid
        hits = await svc.search(TranslationSearch(q='ШАМПУНЬ', locale='ru'))
        assert len(hits) == 1 and hits[0].objectid == pid
        assert await svc.search(TranslationSearch(q='shampoo', locale='ru')) == []
        assert await svc.search(TranslationSearch(q='Haar', locale='de',
                                                  field='description')) != []
    print('[ok] поиск: de/ru находят своё, чужая локаль — пусто, description ищется')

    # --- незаведённая локаль и дубль активного перевода ---
    async with Sess() as s:
        svc = TranslationService(session=s)
        with pytest.raises(HTTPException) as e:
            await svc.get_translations('entity', pid, 'fr')
        assert e.value.status_code == 400
    async with eng.begin() as conn:
        lang_de = (await conn.execute(text(
            "SELECT id FROM language WHERE iso = 'de'"))).scalar_one()
        with pytest.raises(IntegrityError):
            await conn.execute(text(
                "INSERT INTO translation (id, \"table\", objectid, language, field, content) "
                "VALUES (gen_random_uuid(), 'entity', :o, :l, 'name', 'dup')"),
                {'o': pid, 'l': lang_de})
    print('[ok] незаведённая локаль: 400; дубль активного перевода отвергнут БД')

    await eng.dispose()
    print('\nТЕСТ I18N ПРОЙДЕН')
