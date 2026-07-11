"""Фаза 2: эпизод болезни + анамнез на псевдониме через ядро (Entity/Property/FSM)."""
from sqlalchemy import text, select
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

import shop.tables as t
from shop.medical_seed import seed_medical
from shop.models.entity import EntityCreate
from shop.models.property import PropertyCreate, PropertyFilter
from shop.services.entity import EntityService
from shop.services.property import PropertyService
from shop.services.fsm import FSMService

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
    # псевдоним = операционный якорь медкарты (мост person<->pseudonym — отдельно)
    async with Sess() as s:
        pseud = t.Pseudonym()
        s.add(pseud); await s.commit()
        pid = pseud.id
    aspirin = None
    async with Sess() as s:
        aspirin = (await s.execute(select(t.Entity.id).where(
            t.Entity.code == 'aspirin'))).scalar_one()

    # --- открыть эпизод болезни (Entity[illness] на псевдониме) ---
    async with Sess() as s:
        ep = await EntityService(session=s).create(EntityCreate(
            category=ids['illness'], code='ep-1', name='ОРВИ',
            table='pseudonym', objectid=pid))
        eid = ep.id
    # начальное состояние FSM — anamnesis
    async with Sess() as s:
        st = await FSMService(session=s).state('entity', eid)
    assert st['state'] == 'anamnesis', st
    print('[ok] эпизод открыт, FSM = anamnesis')

    # --- анамнез: симптомы (present со слотами + pertinent negative) ---
    async with Sess() as s:
        psvc = PropertyService(session=s)
        await psvc.create(PropertyCreate(
            category=ids['symptom'], code='headache', table='entity', objectid=eid,
            value={'status': 'present', 'source': 'self', 'confidence': 1.0,
                   'slots': {'onset': 'вчера вечером', 'severity': 6,
                             'character': 'давящая'}}))
        await psvc.create(PropertyCreate(   # важный отрицательный симптом
            category=ids['symptom'], code='chest_pain', table='entity', objectid=eid,
            value={'status': 'absent', 'source': 'self'}))
        # лекарство пациента (уровень пациента, на псевдониме) со ссылкой на справочник
        await psvc.create(PropertyCreate(
            category=ids['medication'], code='aspirin', table='pseudonym', objectid=pid,
            value={'ref': str(aspirin), 'dose': '100 мг', 'period': 'по требованию'}))
    print('[ok] записаны: 2 симптома (present+absent), лекарство')

    # --- Relation пациент->справочник (operational->reference), теперь разрешён ---
    async with Sess() as s:
        s.add(t.Relation(category=ids['medication'], code='takes',
                         table='pseudonym', objectid=pid,
                         related_table='entity', related_id=aspirin))
        await s.commit()  # ORM-слушатель пропускает operational<->reference
    async with Sess() as s:
        rel = (await s.execute(select(t.Relation).where(
            t.Relation.objectid == pid))).scalar_one()
        assert rel.related_id == aspirin and rel.code == 'takes'
    print('[ok] Relation пациент->лекарство (operational->reference) создан')

    # домен медданных — operational (унаследован от псевдонима/эпизода)
    async with Sess() as s:
        dom = (await s.execute(select(t.ObjectRegistry.domain).join(
            t.Property, t.Property.id == t.ObjectRegistry.id).where(
            t.Property.code == 'headache'))).scalar_one()
    assert dom == 'operational', dom
    print('[ok] домен симптома operational')

    # --- FSM: диагноз ---
    async with Sess() as s:
        st = await FSMService(session=s).trigger('entity', eid, 'diagnose',
                                                 creator=None)
    assert st['state'] == 'diagnosis', st
    async with Sess() as s:
        await PropertyService(session=s).create(PropertyCreate(
            category=ids['illness'], code='diagnosis', table='entity', objectid=eid,
            value={'icd10': 'J06.9', 'text': 'ОРВИ', 'source': 'self'}))
    print('[ok] FSM anamnesis->diagnosis, диагноз записан')

    # --- сборка анамнеза: симптомы эпизода, лекарства пациента ---
    async with Sess() as s:
        psvc = PropertyService(session=s)
        symptoms = await psvc.find(PropertyFilter(
            table='entity', objectid=eid, category=ids['symptom']))
        meds = await psvc.find(PropertyFilter(
            table='pseudonym', objectid=pid, category=ids['medication']))
        dx = await psvc.find(PropertyFilter(
            table='entity', objectid=eid, code='diagnosis'))
    by_code = {p.code: p for p in symptoms}
    assert set(by_code) == {'headache', 'chest_pain'}
    assert by_code['headache'].value['status'] == 'present'
    assert by_code['headache'].value['slots']['severity'] == 6
    assert by_code['chest_pain'].value['status'] == 'absent'
    assert len(meds) == 1 and meds[0].value['ref'] == str(aspirin)
    assert len(dx) == 1 and dx[0].value['icd10'] == 'J06.9'
    print('[ok] сборка анамнеза: симптомы+негатив, лекарство, диагноз')

    # --- история состояний эпизода ---
    # начальное 'anamnesis' — ленивое (в БД не пишется до первого перехода),
    # поэтому в истории только записанные переходы
    async with Sess() as s:
        hist = await FSMService(session=s).history('entity', eid)
    states = [h.value['state'] for h in hist]
    assert states == ['diagnosis'], states
    print('[ok] история эпизода (записанные переходы):', states)

    await eng.dispose()
    print('\nТЕСТ МЕДКАРТЫ ПРОЙДЕН')
