"""Согласия: consent-first доступ к identity-данным, управляющий компании,
уведомления через outbox."""
import datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import text, select
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

import shop.tables as t
from shop.models.auth import TokenPayload
from shop.models.company import CompanyCreate
from shop.models.consent import ConsentDecision, ConsentRequest
from shop.models.user import Contact, UserCreate
from shop.services.company import CompanyService
from shop.services.consent import ConsentService
from shop.services.person import PersonService
from shop.services.user import UserService
from shop.settings import settings
from conftest import drain

URI = 'postgresql+asyncpg://shop:secret@localhost:5432/shop'


async def test_main():
    eng = create_async_engine(URI, poolclass=NullPool)
    async with eng.begin() as conn:
        await conn.execute(text('DROP SCHEMA public CASCADE'))
        await conn.execute(text('CREATE SCHEMA public'))
        await conn.run_sync(t.Root.metadata.create_all)
    Sess = async_sessionmaker(eng, expire_on_commit=False)

    # владелец (персона + учётка), запросивший, страна/место
    async with Sess() as s:
        country = t.Country(iso2='ru', iso3='rus', name='Russia')
        s.add(country); await s.flush()
        place = t.Place(code='msk', name='Москва', country=country.id)
        s.add(place); await s.flush()
        owner_person = t.Person(name={'last': 'Иванов'}, sex=True,
                                birthdate=datetime.date(1980, 5, 1), birth_place=place.id)
        friend_person = t.Person(name={'last': 'Сидоров'}, sex=True,
                                 birthdate=datetime.date(1985, 3, 2), birth_place=place.id)
        s.add(owner_person); s.add(friend_person); await s.flush()
        usvc = UserService(session=s)
        owner = await usvc.create(UserCreate(person=owner_person.id,
                                             contact=Contact(email='owner@x.com'),
                                             password='correct-horse'))
        friend = await usvc.create(UserCreate(person=friend_person.id,
                                              contact=Contact(email='friend@x.com'),
                                              password='correct-horse'))
        country_id, place_id = country.id, country.id
        owner_person_id, friend_id = owner_person.id, friend.id
    owner_p = TokenPayload(sub=owner.id)
    friend_p = TokenPayload(sub=friend.id)
    admin_p = TokenPayload(sub=friend.id, roles=[settings.admin_role])

    # --- чужак без согласия не читает чужую персону ---
    async with Sess() as s:
        csvc = ConsentService(session=s)
        with pytest.raises(HTTPException) as e:
            await csvc.ensure_access('person', owner_person_id, friend_p)
        assert e.value.status_code == 403
        # владелец читает свою
        await csvc.ensure_access('person', owner_person_id, owner_p)
    print('[ok] identity consent-first: чужак 403, владелец проходит')

    # --- запрос -> уведомление владельцу -> одобрение -> доступ ---
    async with Sess() as s:
        cid = (await ConsentService(session=s).request(
            ConsentRequest(subject_table='person', subject_id=owner_person_id,
                           scope='identity', reason='нужен доступ'), friend_p)).id
    await drain(Sess)
    async with Sess() as s:
        msg = (await s.execute(select(t.Message).where(
            t.Message.receiver == owner.id, t.Message.code == 'consent'))).scalars().one()
        assert 'identity' in msg.content
    # повторный запрос при живом — 409
    async with Sess() as s:
        with pytest.raises(HTTPException) as e:
            await ConsentService(session=s).request(
                ConsentRequest(subject_table='person', subject_id=owner_person_id,
                               scope='identity'), friend_p)
        assert e.value.status_code == 409
    # чужак не может одобрить свой же запрос
    async with Sess() as s:
        with pytest.raises(HTTPException) as e:
            await ConsentService(session=s).decide(cid, True, ConsentDecision(), friend_p)
        assert e.value.status_code == 403
    # владелец одобряет
    async with Sess() as s:
        await ConsentService(session=s).decide(cid, True, ConsentDecision(), owner_p)
    print('[ok] запрос -> уведомление -> дубль 409 -> чужое одобрение 403 -> владелец одобрил')

    # теперь friend читает персону
    async with Sess() as s:
        await ConsentService(session=s).ensure_access('person', owner_person_id, friend_p)
        # но писать не может — только чтение по согласию
        with pytest.raises(HTTPException) as e:
            await ConsentService(session=s).ensure_access(
                'person', owner_person_id, friend_p, write=True)
        assert e.value.status_code == 403
    await drain(Sess)
    async with Sess() as s:
        approved = (await s.execute(select(t.Message).where(
            t.Message.receiver == friend.id, t.Message.code == 'consent'))).scalars().all()
        assert any('одобрен' in m.content for m in approved)
    print('[ok] по согласию: чтение да, запись нет; запросивший уведомлён об одобрении')

    # --- отзыв -> доступа больше нет ---
    async with Sess() as s:
        row = (await s.execute(select(t.Consent).where(
            t.Consent.id == cid))).scalar_one()
        await ConsentService(session=s).revoke(row.id, owner_p)
    async with Sess() as s:
        with pytest.raises(HTTPException) as e:
            await ConsentService(session=s).ensure_access('person', owner_person_id, friend_p)
        assert e.value.status_code == 403
    print('[ok] после отзыва: 403')

    # --- создатель компании автоматически становится её управляющим ---
    async with Sess() as s:
        company = await CompanyService(session=s).create(
            CompanyCreate(code='acme', country=country_id,
                          registered=datetime.date(2020, 1, 1)), creator=owner.id)
        company_id = company.id
    async with Sess() as s:
        # owner (создатель) — управляющий: manage-consent появился сам
        assert await ConsentService(session=s).check(
            'company', company_id, owner.id, 'manage')
    print('[ok] создатель компании авто-получил manage')

    # чужак компанией не управляет; owner (управляющий) назначает friend
    async with Sess() as s:
        with pytest.raises(HTTPException) as e:
            await ConsentService(session=s).grant_manage(
                'company', company_id, friend_id, friend_p)
        assert e.value.status_code == 403
        await ConsentService(session=s).grant_manage(
            'company', company_id, friend_id, owner_p)
    print('[ok] управляющий назначил второго управляющего; чужак — 403')

    # запрос к данным компании; friend (соуправляющий) видит его и одобряет
    async with Sess() as s:
        mgr_cid = (await ConsentService(session=s).request(
            ConsentRequest(subject_table='company', subject_id=company_id,
                           scope='financial', reason='аудит'), owner_p)).id
    async with Sess() as s:
        incoming = await ConsentService(session=s).incoming(friend_p)
        assert any(c.id == mgr_cid for c in incoming)
        await ConsentService(session=s).decide(mgr_cid, True, ConsentDecision(), friend_p)
    async with Sess() as s:
        assert await ConsentService(session=s).check(
            'company', company_id, owner.id, 'financial')
    print('[ok] соуправляющий одобряет запрос к данным компании')

    # --- автопротухание until: sweep закрывает истёкшие согласия ---
    async with Sess() as s:
        exp_cid = (await ConsentService(session=s).request(
            ConsentRequest(subject_table='company', subject_id=company_id,
                           scope='contact', reason='временный'), friend_p)).id
    past = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=1)
    async with Sess() as s:
        await ConsentService(session=s).decide(
            exp_cid, True, ConsentDecision(until=past), owner_p)
    # доступ уже не действует (проверка until при чтении), но строка ещё approved
    async with Sess() as s:
        csvc = ConsentService(session=s)
        assert not await csvc.check('company', company_id, friend.id, 'contact')
        closed = await csvc.sweep_expired()
        assert closed >= 1
    async with Sess() as s:
        row = (await s.execute(select(t.Consent).where(t.Consent.id == exp_cid)
               .execution_options(include_expired=True)
               .order_by(t.Consent.begins.desc()))).scalars().first()
        assert row.status == 'expired' and row.ends is not None
    print('[ok] sweep: истёкшее согласие -> expired + закрыто')

    await drain(Sess)
    async with Sess() as s:
        msgs = (await s.execute(select(t.Message).where(
            t.Message.receiver == friend.id, t.Message.code == 'consent'))).scalars().all()
        assert any('истёк' in m.content for m in msgs)
    print('[ok] получатель уведомлён об истечении')

    await eng.dispose()
    print('\nТЕСТ CONSENT ПРОЙДЕН')
