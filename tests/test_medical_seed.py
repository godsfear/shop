"""Фаза 1: медицинский сид — идемпотентность, схемы, справочники."""
from sqlalchemy import text, select, func
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

import shop.tables as t
from shop.medical_seed import DICTIONARY, seed_medical, SYMPTOM_SCHEMA

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
        cats1 = (await s.execute(select(func.count()).select_from(t.Category))).scalar_one()
        ents1 = (await s.execute(select(func.count()).select_from(t.Entity))).scalar_one()
    assert 'symptom' in ids and 'illness' in ids
    print(f'[ok] сид создан: категорий={cats1}, справочных сущностей={ents1}')

    # идемпотентность: повтор ничего не добавляет
    async with Sess() as s:
        await seed_medical(s)
    async with Sess() as s:
        cats2 = (await s.execute(select(func.count()).select_from(t.Category))).scalar_one()
        ents2 = (await s.execute(select(func.count()).select_from(t.Entity))).scalar_one()
    assert (cats1, ents1) == (cats2, ents2), (cats1, ents1, cats2, ents2)
    print('[ok] повторный сид идемпотентен')

    # симптом несёт 11-слотовую схему
    async with Sess() as s:
        sym = (await s.execute(select(t.Category).where(
            t.Category.code == 'symptom'))).scalar_one()
        assert sym.value['schema'] == SYMPTOM_SCHEMA
        assert len(sym.value['schema']) == 11
    print('[ok] symptom.value.schema — 11 слотов')

    # болезнь несёт FSM + required + red_flags; домены reference
    async with Sess() as s:
        illness = (await s.execute(select(t.Category).where(
            t.Category.code == 'illness'))).scalar_one()
        assert illness.value['fsm']['initial'] == 'anamnesis'
        # required — секции {category, scope}; полнота проверяется по данным
        req_cats = {r['category'] for r in illness.value['required']}
        assert {'symptom', 'medication', 'allergy'} <= req_cats, req_cats
        assert illness.value['red_flags'] == ['acs']
        # справочная Entity зарегистрирована в reference-домене
        dom = (await s.execute(select(t.ObjectRegistry.domain).join(
            t.Entity, t.Entity.id == t.ObjectRegistry.id).where(
            t.Entity.category == illness.id))).first()
    print('[ok] illness несёт fsm/required/red_flags')

    # справочник читается; размеры — из самого DICTIONARY (единый источник:
    # пополнение сида не должно ломать тест)
    async with Sess() as s:
        n_sym = (await s.execute(select(func.count()).select_from(t.Entity).where(
            t.Entity.category == ids['symptom']))).scalar_one()
        n_med = (await s.execute(select(func.count()).select_from(t.Entity).where(
            t.Entity.category == ids['medication']))).scalar_one()
        dom = (await s.execute(select(t.ObjectRegistry.domain).where(
            t.ObjectRegistry.table == 'entity').limit(1))).scalar_one()
    assert n_sym == len(DICTIONARY['symptom']), (n_sym, len(DICTIONARY['symptom']))
    assert n_med == len(DICTIONARY['medication']), (n_med, len(DICTIONARY['medication']))
    assert dom == 'reference', dom
    print(f'[ok] справочник: симптомов={n_sym}, лекарств={n_med}, домен={dom}')

    await eng.dispose()
    print('\nТЕСТ МЕДСИДА ПРОЙДЕН')
