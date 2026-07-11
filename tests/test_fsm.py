import asyncio, datetime

from fastapi import HTTPException
from sqlalchemy import text, select
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

import shop.tables as t
from shop.services.fsm import FSMService, fsm_handler

URI = 'postgresql+asyncpg://shop:secret@localhost:5432/shop'

archived_log = []


@fsm_handler('is_editor')
def is_editor(machine, actor_role='user', **_):
    return actor_role == 'editor'


@fsm_handler('log_archive')
def log_archive(machine, **_):
    archived_log.append((machine.table, machine.objectid))


FSM_CONFIG = {
    'states': ['draft', 'review', 'published', 'archived'],
    'initial': 'draft',
    'transitions': [
        {'event': 'submit',  'source': 'draft',                'dest': 'review'},
        {'event': 'approve', 'source': 'review',               'dest': 'published', 'guard': 'is_editor'},
        {'event': 'reject',  'source': 'review',               'dest': 'draft'},
        {'event': 'archive', 'source': ['published', 'draft'], 'dest': 'archived',  'action': 'log_archive'},
    ],
}


async def test_main():
    eng = create_async_engine(URI, poolclass=NullPool)
    async with eng.begin() as conn:
        await conn.execute(text('DROP SCHEMA public CASCADE'))
        await conn.execute(text('CREATE SCHEMA public'))
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS postgis'))
        await conn.run_sync(t.Root.metadata.create_all)
    Sess = async_sessionmaker(eng, expire_on_commit=False)

    # категория с машиной состояний + сущность в этой категории
    async with Sess() as s:
        country = t.Country(iso2='ru', iso3='rus', name='Russia')
        s.add(country); await s.flush()
        place = t.Place(code='msk', name='Москва', country=country.id)
        s.add(place); await s.flush()
        person = t.Person(name={'last': 'Иванов'}, sex=True,
                          birthdate=datetime.date(1980, 5, 1), birth_place=place.id)
        s.add(person); await s.flush()
        cat = t.Category(code='order', name='Заказ', value={'fsm': FSM_CONFIG})
        cat_plain = t.Category(code='note', name='Без FSM')
        s.add(cat); s.add(cat_plain); await s.flush()
        entity = t.Entity(category=cat.id, code='order-1',
                          table='person', objectid=person.id)
        entity2 = t.Entity(category=cat_plain.id, code='note-1',
                           table='person', objectid=person.id)
        s.add(entity); s.add(entity2); await s.commit()
        eid, eid2 = entity.id, entity2.id

    # --- ленивое начальное состояние ---
    async with Sess() as s:
        fsm = FSMService(session=s)
        st = await fsm.state('entity', eid)
    assert st == {'state': 'draft', 'available': ['archive', 'submit']}, st
    print('[ok] начальное состояние без строки в БД:', st)

    # --- переход submit ---
    async with Sess() as s:
        fsm = FSMService(session=s)
        st = await fsm.trigger('entity', eid, 'submit')
    assert st['state'] == 'review'
    print('[ok] submit -> review, доступно:', st['available'])

    # --- guard: без роли редактора нельзя ---
    async with Sess() as s:
        fsm = FSMService(session=s)
        try:
            await fsm.trigger('entity', eid, 'approve', context={'actor_role': 'user'})
            raise AssertionError('guard пропустил!')
        except HTTPException as e:
            assert e.status_code == 409
            print(f'[ok] guard заблокировал approve: 409 ({e.detail})')
        st = await fsm.trigger('entity', eid, 'approve', context={'actor_role': 'editor'})
        assert st['state'] == 'published'
        print('[ok] approve с ролью editor -> published')

    # --- action на archive ---
    async with Sess() as s:
        fsm = FSMService(session=s)
        st = await fsm.trigger('entity', eid, 'archive')
    assert st['state'] == 'archived' and archived_log == [('entity', eid)]
    print('[ok] archive: action log_archive вызван')

    # --- недопустимое событие из archived ---
    async with Sess() as s:
        fsm = FSMService(session=s)
        try:
            await fsm.trigger('entity', eid, 'submit')
            raise AssertionError('переход из archived прошёл!')
        except HTTPException as e:
            assert e.status_code == 409
            print('[ok] submit из archived: 409')

    # --- история и единственность активного состояния ---
    async with Sess() as s:
        fsm = FSMService(session=s)
        hist = await fsm.history('entity', eid)
        states = [r.value['state'] for r in hist]
        active = [r for r in hist if r.ends is None]
    assert states == ['review', 'published', 'archived'], states
    assert len(active) == 1 and active[0].value['state'] == 'archived'
    assert active[0].value['event'] == 'archive'
    print('[ok] история переходов из закрытых строк:', states, '| активная одна')

    # --- категория без FSM и битый конфиг ---
    async with Sess() as s:
        fsm = FSMService(session=s)
        try:
            await fsm.state('entity', eid2)
            raise AssertionError('объект без FSM прошёл!')
        except HTTPException as e:
            assert e.status_code == 400
            print(f'[ok] категория без value.fsm: 400')
        bad = t.Category(code='bad', value={'fsm': {'states': ['a'], 'initial': 'zzz'}})
        s.add(bad); await s.flush()
        broken = t.Entity(category=bad.id, code='x', table='person',
                          objectid=(await s.execute(select(t.Person.id))).scalar_one())
        s.add(broken); await s.commit()
        try:
            await fsm.state('entity', broken.id)
            raise AssertionError('битый конфиг прошёл!')
        except HTTPException as e:
            assert e.status_code == 422
            print(f'[ok] битый конфиг: 422 ({e.detail[:60]}...)')

    await eng.dispose()
    print('\nТЕСТ FSM ПРОЙДЕН')

