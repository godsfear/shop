import asyncio, tempfile, datetime

from sqlalchemy import select, text, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

import shop.tables as t
from shop.tables import DomainBoundaryError
from shop.keyservice import StubKeyService, EMERGENCY
from shop.services.bridge import BridgeService

URI = 'postgresql+asyncpg://shop:secret@localhost:5432/shop'


async def test_main():
    eng = create_async_engine(URI)
    async with eng.begin() as conn:
        # полное пересоздание: drop_all не переживает дрейф схемы между запусками
        await conn.execute(text('DROP SCHEMA public CASCADE'))
        await conn.execute(text('CREATE SCHEMA public'))
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS postgis'))
        await conn.run_sync(t.Root.metadata.create_all)
    print('[ok] схема создана (пересоздание public + create_all)')

    Sess = async_sessionmaker(eng, expire_on_commit=False)
    ks = StubKeyService(tempfile.mkdtemp(), approvals_required=2, veto_window_s=1)
    ks.create_key('escrow')
    ks.create_key('group:doctors')
    ks.grant('group:doctors', 'dr-ivanov')

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
        rid = ks.request_breakglass(EMERGENCY, 'escrow', 'nurse-1', 'пациент без сознания')
        ks.approve(rid, 'keyholder-1'); ks.approve(rid, 'keyholder-2')
        resolved = await bridge.breakglass_resolve(link_id, rid)
        assert resolved == pseudonym_id
        print('[ok] break-glass: escrow-копия DEK раскрыла мост, аудит:', ks.verify_audit(), 'записей')

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

    await eng.dispose()
    print('\nСКВОЗНОЙ ТЕСТ ПРОЙДЕН')

