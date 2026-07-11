import asyncio, datetime

from sqlalchemy import text
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

import shop.tables as t
from shop.cache import Cache, get_cache
from shop.keyservice import DbKeyService, PolicyError
from shop.models import CountryCreate, CountryFilter
from shop.models.user import UserCreate, UserUpdate, Contact
from shop.models.auth import TokenPayload
from shop.services.bridge import BridgeService
from shop.services.country import CountryService
from shop.services.user import UserService
from shop.services.auth import get_current_user

URI = 'postgresql+asyncpg://shop:secret@localhost:5432/shop'


async def test_main():
    await get_cache()._redis.flushdb()
    eng = create_async_engine(URI, poolclass=NullPool)
    async with eng.begin() as conn:
        await conn.execute(text('DROP SCHEMA public CASCADE'))
        await conn.execute(text('CREATE SCHEMA public'))
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS postgis'))
        await conn.run_sync(t.Root.metadata.create_all)
    Sess = async_sessionmaker(eng, expire_on_commit=False)

    # --- справочник: версионируемое пространство ---
    async with Sess() as s:
        svc = CountryService(session=s)
        await svc.create(CountryCreate(iso2='ru', iso3='rus', name='Russia'))
        assert len(await svc.get_all()) == 1          # промах -> закэшировано
    async with eng.begin() as conn:                    # вставка МИМО сервиса (без bump)
        await conn.execute(text(
            "INSERT INTO country (id, iso2, iso3, name) VALUES (gen_random_uuid(), 'de', 'deu', 'Germany')"))
    async with Sess() as s:
        svc = CountryService(session=s)
        assert len(await svc.get_all()) == 1, 'кэш не сработал'
        print('[ok] справочник отдан из кэша (вставка мимо сервиса невидима)')
        c = await svc.create(CountryCreate(iso2='fr', iso3='fra', name='France'))  # bump
        assert len(await svc.get_all()) == 3
        print('[ok] запись через сервис подняла версию — кэш обновился (видны все 3)')
        found = await svc.find(CountryFilter(iso2='FR'))
        found2 = await svc.find(CountryFilter(iso2='FR'))  # из кэша
        assert found2.id == c.id
        print('[ok] find закэширован по фильтру')

    # --- профиль пользователя ---
    async with Sess() as s:
        country_id = c.id
        place = t.Place(code='msk', name='Москва', country=country_id)
        s.add(place); await s.flush()
        person = t.Person(name={'last': 'Иванов'}, sex=True,
                          birthdate=datetime.date(1980, 5, 1), birth_place=place.id)
        s.add(person); await s.commit()
        user = await UserService(session=s).create(UserCreate(
            person=person.id, contact=Contact(email='a@x.com'), password='correct-horse'))
    payload = TokenPayload(sub=user.id)
    async with Sess() as s:
        me = await get_current_user(payload=payload, session=s)   # промах -> кэш
        assert me.contact.email == 'a@x.com'
    async with eng.begin() as conn:                    # правка МИМО сервиса
        await conn.execute(text('UPDATE "user" SET contact = \'{"email": "raw@x.com"}\''))
    async with Sess() as s:
        me = await get_current_user(payload=payload, session=s)
        assert me.contact.email == 'a@x.com', 'профиль не из кэша'
        print('[ok] профиль отдан из кэша (правка мимо сервиса невидима)')
        await UserService(session=s).update(user.id, UserUpdate(contact=Contact(email='new@x.com')))
    async with Sess() as s:
        me = await get_current_user(payload=payload, session=s)
        assert me.contact.email == 'new@x.com', me.contact
        print('[ok] update через сервис инвалидировал профиль — свежие данные')

    # --- мост: сессионный кэш, ACL не обходится ---
    ks = DbKeyService(Sess)
    await ks.create_key('escrow'); await ks.create_key('group:doctors')
    await ks.grant('group:doctors', 'dr-ivanov')
    async with Sess() as s:
        bridge = BridgeService(session=s, keys=ks)
        link, pseudonym_id = await bridge.create_link(
            'person', person.id, 'medical', groups={'group:doctors': None})
        n_audit = await ks.verify_audit()
        r1 = await bridge.resolve(link.id, 'group:doctors', 'dr-ivanov')  # unwrap + кэш
        r2 = await bridge.resolve(link.id, 'group:doctors', 'dr-ivanov')  # из кэша
        assert r1 == r2 == pseudonym_id
        assert await ks.verify_audit() == n_audit + 1, 'второй resolve пошёл в KeyService'
        print('[ok] мост: повторный resolve из кэша, KeyService не тронут')
        try:
            await bridge.resolve(link.id, 'group:doctors', 'dr-chuzhoy')
            raise AssertionError('кэш обошёл ACL!')
        except PolicyError:
            print('[ok] кэш не обходит ACL: чужой actor по-прежнему отвергнут')

    # --- деградация: Redis недоступен -> работаем напрямую ---
    dead = Cache('redis://localhost:9/0')
    assert await dead.get('x') is None
    await dead.set('x', 'y', 5)
    assert await dead.version('country') == -1
    async with Sess() as s:
        rows = await CountryService(session=s).get_all()   # ver>=0 у живого кэша
        assert len(rows) == 3
    print('[ok] деградация: мёртвый Redis не роняет вызовы (get=None, version=-1)')

    await eng.dispose()
    print('\nТЕСТ КЭША ПРОЙДЕН')

