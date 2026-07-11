import asyncio, datetime

from fastapi import HTTPException
from sqlalchemy import select, text, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

import shop.tables as t
from shop.cache import get_cache
from shop.tables import DomainBoundaryError
from shop.keyservice import DbKeyService, EMERGENCY
from shop.models.auth import TokenPayload
from shop.models.user import Contact, UserCreate
from conftest import drain
from shop.services.bridge import BridgeService
from shop.services.user import UserService
from shop.settings import settings

URI = 'postgresql+asyncpg://shop:secret@localhost:5432/shop'


async def test_main():
    eng = create_async_engine(URI, poolclass=NullPool)
    async with eng.begin() as conn:
        # полное пересоздание: drop_all не переживает дрейф схемы между запусками
        await conn.execute(text('DROP SCHEMA public CASCADE'))
        await conn.execute(text('CREATE SCHEMA public'))
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS postgis'))
        await conn.run_sync(t.Root.metadata.create_all)
    print('[ok] схема создана (пересоздание public + create_all)')

    Sess = async_sessionmaker(eng, expire_on_commit=False)
    ks = DbKeyService(Sess, approvals_required=2, veto_window_s=1)
    await ks.create_key('escrow')
    await ks.create_key('group:doctors')
    await ks.grant('group:doctors', 'dr-ivanov')

    # --- бутстрап домена личности: страна -> место -> персона ---
    async with Sess() as s:
        country = t.Country(iso2='ru', iso3='rus', name='Russia')
        s.add(country); await s.flush()
        place = t.Place(code='msk', name='Москва', country=country.id)
        s.add(place); await s.flush()
        person = t.Person(name={'last': 'Иванов', 'first': 'Пётр'}, sex=True,
                          birthdate=datetime.date(1980, 5, 1), birth_place=place.id)
        s.add(person); await s.commit()
        person_id = person.id
        place_id = place.id
    print('[ok] бутстрап: страна -> место -> персона (циклы FK развязаны)')

    # --- пул псевдонимов ---
    async with Sess() as s:
        bridge = BridgeService(session=s, keys=ks)
        await bridge.replenish_pool(5)
        n0 = (await s.execute(select(func.count()).select_from(t.PseudonymPool))).scalar_one()
    assert n0 == 5
    print('[ok] пул пополнен пакетом: 5 свободных псевдонимов')

    # --- мост: персона -> псевдоним (из пула) ---
    async with Sess() as s:
        bridge = BridgeService(session=s, keys=ks)
        link, pseudonym_id = await bridge.create_link(
            'person', person_id, 'medical', groups={'group:doctors': None})
        link_id = link.id
        n1 = (await s.execute(select(func.count()).select_from(t.PseudonymPool))).scalar_one()
        p_begins = (await s.execute(select(t.Pseudonym.begins).where(
            t.Pseudonym.id == pseudonym_id))).scalar_one()
    assert pseudonym_id.version == 4, 'псевдоним должен быть uuid4'
    assert n1 == 4, 'псевдоним не списан из пула'
    assert p_begins < link.begins, 'begins псевдонима совпадает с мостом — корреляция!'
    print('[ok] мост создан: псевдоним из пула, begins псевдонима раньше begins моста')

    # --- мост для компании (субъект — любой identity-объект) ---
    async with Sess() as s:
        company = t.Company(code='acme', country=(await s.execute(
            select(t.Country.id))).scalar_one(), registered=datetime.date(2020, 1, 1))
        s.add(company); await s.commit()
        company_id = company.id
    async with Sess() as s:
        bridge = BridgeService(session=s, keys=ks)
        c_link, c_pseudonym = await bridge.create_link('company', company_id, 'financial')
        assert c_pseudonym.version == 4
    print('[ok] мост для компании: субъект полиморфный')

    # --- мост нельзя прикрепить к справочнику ---
    async with Sess() as s:
        bridge = BridgeService(session=s, keys=ks)
        try:
            await bridge.create_link('country', (await s.execute(
                select(t.Country.id))).scalar_one(), 'medical')
            raise AssertionError('мост на справочник прошёл!')
        except DomainBoundaryError as e:
            print(f'[ok] мост только к identity: {e}')

    # --- реестр: таблицы и домены ---
    async with Sess() as s:
        rows = (await s.execute(select(t.ObjectRegistry.table, t.ObjectRegistry.domain))).all()
    reg = {(r[0], r[1]) for r in rows}
    assert ('person', 'identity') in reg and ('pseudonym', 'operational') in reg
    assert ('link', 'identity') in reg and ('access', 'identity') in reg
    print(f'[ok] реестр заполнен автоматически: {sorted(reg)}')

    # --- операционные данные на псевдониме; домен наследуется ---
    async with Sess() as s:
        s.add(t.Property(code='diagnosis', table='pseudonym', objectid=pseudonym_id,
                         value={'icd10': 'J06.9'}))
        await s.commit()
    async with Sess() as s:
        d = (await s.execute(select(t.ObjectRegistry.domain).join(
            t.Property, t.Property.id == t.ObjectRegistry.id))).scalar_one()
    assert d == 'operational', d
    print('[ok] Property на псевдониме унаследовала домен operational')

    # --- граница доменов: прямая связь персона<->псевдоним запрещена ---
    async with Sess() as s:
        s.add(t.Relation(code='is', table='person', objectid=person_id,
                         related_table='pseudonym', related_id=pseudonym_id))
        try:
            await s.commit()
            raise AssertionError('связь через границу доменов не была отвергнута!')
        except DomainBoundaryError as e:
            print(f'[ok] граница доменов: {e}')

    # --- битая полиморфная ссылка: отвергается реестром ---
    import uuid as _uuid
    async with Sess() as s:
        s.add(t.Property(code='x', table='pseudonym', objectid=_uuid.uuid4(), value={}))
        try:
            await s.commit()
            raise AssertionError('ссылка на несуществующий объект прошла!')
        except DomainBoundaryError as e:
            print(f'[ok] реестр: {e}')

    # --- составной FK: тип полиморфной ссылки проверяется базой ---
    async with Sess() as s:
        cid = (await s.execute(select(t.Country.id))).scalar_one()
        # id страны есть в реестре, но под типом 'country', а не 'pseudonym'
        s.add(t.Property(code='x', table='pseudonym', objectid=cid, value={}))
        try:
            await s.commit()
            raise AssertionError('ссылка с неверным типом цели прошла!')
        except IntegrityError:
            print('[ok] составной FK: неверный тип цели отвергнут базой')

    # --- повседневный доступ группы ---
    async with Sess() as s:
        bridge = BridgeService(session=s, keys=ks)
        resolved = await bridge.resolve(link_id, 'group:doctors', 'dr-ivanov')
        assert resolved == pseudonym_id
        print('[ok] врач из группы разрешил мост -> псевдоним совпал')
        try:
            await bridge.resolve(link_id, 'group:doctors', 'dr-chuzhoy')
            raise AssertionError('чужак разрешил мост!')
        except Exception as e:
            print(f'[ok] чужаку отказано: {e}')

    # --- break-glass: правило двух ---
    async with Sess() as s:
        bridge = BridgeService(session=s, keys=ks)
        rid = await ks.request_breakglass(EMERGENCY, 'escrow', 'nurse-1', 'пациент без сознания')
        await ks.approve(rid, 'keyholder-1'); await ks.approve(rid, 'keyholder-2')
        resolved = await bridge.breakglass_resolve(link_id, rid)
        assert resolved == pseudonym_id
        print('[ok] break-glass: escrow-копия DEK раскрыла мост, аудит:', await ks.verify_audit(), 'записей')

    # --- автофильтр ends вживую ---
    async with Sess() as s:
        prop = (await s.execute(select(t.Property))).scalars().first()
        prop.ends = datetime.datetime.now(datetime.timezone.utc)
        await s.commit()
    async with Sess() as s:
        active = (await s.execute(select(t.Property))).scalars().all()
        all_rows = (await s.execute(
            select(t.Property).execution_options(include_expired=True))).scalars().all()
    assert len(active) == 0 and len(all_rows) == 1
    print('[ok] автофильтр ends: активных 0, с include_expired — 1')

    # === владелец делится доступом: grant / list / revoke / уведомления ===
    async with Sess() as s:
        usvc = UserService(session=s)
        owner = await usvc.create(UserCreate(person=person_id,
                                             contact=Contact(email='owner@x.com'),
                                             password='correct-horse'))
        friend_person = t.Person(name={'last': 'Сидоров'}, sex=True,
                                 birthdate=datetime.date(1985, 3, 2), birth_place=place_id)
        s.add(friend_person); await s.flush()
        friend = await usvc.create(UserCreate(person=friend_person.id,
                                              contact=Contact(email='friend@x.com'),
                                              password='correct-horse'))
    owner_p = TokenPayload(sub=owner.id)
    friend_p = TokenPayload(sub=friend.id)
    admin_p = TokenPayload(sub=friend.id, roles=[settings.admin_role])

    # DEK владелец «расшифровывает у себя» — в тесте достаём через группу врачей
    async with Sess() as s:
        wrapped = (await s.execute(select(t.Access.wrapped_dek).where(
            t.Access.link == link_id,
            t.Access.key_id == 'group:doctors'))).scalar_one()
    dek = await ks.unwrap('group:doctors', wrapped, 'dr-ivanov')
    friend_key = f'user:{friend.id}'
    await ks.create_key(friend_key)
    await ks.grant(friend_key, str(friend.id))

    async with Sess() as s:
        bridge = BridgeService(session=s, keys=ks)
        # чужак выдать грант не может
        try:
            await bridge.add_recipient(link_id, friend_key, friend.id, dek,
                                       recipient_type='user', payload=friend_p)
            raise AssertionError('чужак выдал грант!')
        except HTTPException as e:
            assert e.status_code == 403
            print(f'[ok] грант чужаком: 403 ({e.detail})')
        # владелец может
        access = await bridge.add_recipient(link_id, friend_key, friend.id, dek,
                                            recipient_type='user', payload=owner_p)
        # список: escrow + группа + персональный, честные типы
        infos = await bridge.list_access(link_id, owner_p)
        assert {a.recipient_type for a in infos} == {'escrow', 'group', 'user'}
        print('[ok] владелец выдал персональный грант; список доступов честный')
        # получатель разрешает мост (actor = его sub)
        resolved = await bridge.resolve(link_id, friend_key, str(friend.id))
        assert resolved == pseudonym_id
        print('[ok] получатель гранта разрешил мост')
        # escrow отозвать нельзя
        escrow_row = next(a for a in infos if a.recipient_type == 'escrow')
        try:
            await bridge.revoke_access(link_id, escrow_row.id, admin_p)
            raise AssertionError('escrow отозван!')
        except HTTPException as e:
            assert e.status_code == 400
            print('[ok] escrow-копию отозвать нельзя: 400')
        # отзыв персонального гранта (админом — тоже можно)
        await bridge.revoke_access(link_id, access.id, admin_p)
        infos = await bridge.list_access(link_id, owner_p)
        assert 'user' not in {a.recipient_type for a in infos}
    # после отзыва (и очистки сессионного кэша) мост недоступен
    await get_cache().delete(f'bridge:{link_id}:{friend_key}:{friend.id}')
    async with Sess() as s:
        bridge = BridgeService(session=s, keys=ks)
        try:
            await bridge.resolve(link_id, friend_key, str(friend.id))
            raise AssertionError('отозванный грант работает!')
        except HTTPException as e:
            assert e.status_code == 404
            print('[ok] после отзыва: 404 (копии DEK больше нет)')

    # уведомления владельцу о гранте и отзыве
    await drain(Sess)
    async with Sess() as s:
        msgs = (await s.execute(select(t.Message).where(
            t.Message.receiver == owner.id,
            t.Message.code == 'access').order_by(t.Message.begins))).scalars().all()
        assert len(msgs) == 2
        assert 'выдан' in msgs[0].content and 'отозван' in msgs[1].content
    print('[ok] владелец уведомлён о гранте и отзыве через outbox')

    await eng.dispose()
    print('\nСКВОЗНОЙ ТЕСТ ПРОЙДЕН')

