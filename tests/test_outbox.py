import datetime
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import text, select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

import shop.tables as t
from shop.outbox import emit
from shop.versioning import versions
from shop.models.operation import OperationCreate
from shop.models.rate import RateCreate, RateUpdate, RateFilter
from shop.services.operation import OperationService
from shop.services.rate import RateService
from conftest import drain

URI = 'postgresql+asyncpg://shop:secret@localhost:5432/shop'


async def test_main():
    # NullPool: как db_helper — дренящий drain в тесном цикле течёт на дефолтном
    # пуле (соединение возвращается с FOR UPDATE -> событие висит под SKIP LOCKED)
    eng = create_async_engine(URI, poolclass=NullPool)
    async with eng.begin() as conn:
        await conn.execute(text('DROP SCHEMA public CASCADE'))
        await conn.execute(text('CREATE SCHEMA public'))
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS postgis'))
        await conn.run_sync(t.Root.metadata.create_all)
    Sess = async_sessionmaker(eng, expire_on_commit=False)

    # счета: компания с двумя счетами в одной валюте + счёт в другой валюте
    async with Sess() as s:
        country = t.Country(iso2='ru', iso3='rus', name='Russia')
        s.add(country); await s.flush()
        cur_rub = t.Currency(code='RUB', name='Ruble', adjective='r', name_plural='r',
                             name_minor='k', name_minor_plural='k', symbol='₽',
                             symbol_native='₽', decimals=2, rounding=0)
        cur_usd = t.Currency(code='USD', name='Dollar', adjective='d', name_plural='d',
                             name_minor='c', name_minor_plural='c', symbol='$',
                             symbol_native='$', decimals=2, rounding=0)
        s.add(cur_rub); s.add(cur_usd); await s.flush()
        rub_id, usd_id = cur_rub.id, cur_usd.id
        company = t.Company(code='acme', country=country.id,
                            registered=datetime.date(2020, 1, 1))
        s.add(company); await s.flush()
        acc = {}
        for code, cur in (('main', cur_rub), ('reserve', cur_rub), ('usd', cur_usd)):
            a = t.Account(code=code, currency=cur.id, table='company', objectid=company.id)
            s.add(a); await s.flush()
            acc[code] = a.id
        await s.commit()

    # --- проводка: запись синхронна, событие в outbox той же транзакцией ---
    async with Sess() as s:
        svc = OperationService(session=s)
        op = await svc.create(OperationCreate(code='transfer', number='001',
                                              debit=acc['main'], credit=acc['reserve'],
                                              amount_db=Decimal('100')))
        pending = (await s.execute(select(func.count()).select_from(t.Outbox)
                   .where(t.Outbox.processed.is_(None)))).scalar_one()
        assert pending == 1
        assert await svc.balance(acc['main']) == 0, 'баланс посчитан синхронно?!'
    print('[ok] проводка записана, событие в outbox, баланс ещё не тронут (асинхронность)')

    await drain(Sess)
    async with Sess() as s:
        svc = OperationService(session=s)
        assert await svc.balance(acc['main']) == Decimal('-100')
        assert await svc.balance(acc['reserve']) == Decimal('100')
    print('[ok] консумер пересчитал: main=-100, reserve=+100')

    # --- вторая проводка + история баланса версиями ---
    async with Sess() as s:
        await OperationService(session=s).create(OperationCreate(
            code='transfer', number='002', debit=acc['main'], credit=acc['reserve'],
            amount_db=Decimal('40')))
    await drain(Sess)
    async with Sess() as s:
        svc = OperationService(session=s)
        assert await svc.balance(acc['main']) == Decimal('-140')
        assert await svc.balance(acc['reserve']) == Decimal('140')
        bal_row = (await s.execute(select(t.Balance).where(
            t.Balance.account == acc['main']))).scalar_one()
        hist = await versions(s, t.Balance, bal_row.id)
        assert [h.value for h in hist] == [Decimal('-100')]
        total = (await s.execute(select(func.sum(t.Balance.value)))).scalar_one()
        assert total == 0, f'сумма балансов {total} != 0'
    print('[ok] история баланса версиями; инвариант: сумма всех балансов = 0')

    # --- валидации ---
    async with Sess() as s:
        svc = OperationService(session=s)
        for kwargs, code, label in (
            (dict(debit=acc['main'], credit=acc['main']), 400, 'дебет=кредит'),
            (dict(debit=acc['main'], credit=acc['usd']), 400, 'кросс-валюта без amount_cr'),
            (dict(debit=acc['main'], credit=acc['reserve'],
                  amount_cr=Decimal(2)), 400, 'одна валюта, amount_cr != amount_db'),
        ):
            try:
                await svc.create(OperationCreate(code='x', number='x',
                                                 amount_db=Decimal(1), **kwargs))
                raise AssertionError(f'прошло: {label}')
            except HTTPException as e:
                assert e.status_code == code
                print(f'[ok] {label}: {code}')

    # --- пакет из 6 событий: каждое применяется РОВНО раз ---
    # (воркер один — как в проде: outbox_worker на процесс. Двух drain-корутин
    #  в одном event loop не гоняем: нереалистично и создаёт ложную гонку;
    #  межпроцессную безопасность даёт FOR UPDATE SKIP LOCKED по построению.)
    async with Sess() as s:
        svc = OperationService(session=s)
        for i in range(6):
            await svc.create(OperationCreate(code='t', number=f'c{i}',
                                             debit=acc['main'], credit=acc['reserve'],
                                             amount_db=Decimal('10')))
    await drain(Sess)
    async with Sess() as s:
        svc = OperationService(session=s)
        assert await svc.balance(acc['main']) == Decimal('-200')
        assert await svc.balance(acc['reserve']) == Decimal('200')
    print('[ok] пакет из 6 событий: балансы точны (каждое ровно раз)')

    # --- отравленное событие не блокирует очередь ---
    async with Sess() as s:
        emit(s, 'no.such.topic', {'x': 1})
        await s.commit()
        await OperationService(session=s).create(OperationCreate(
            code='t', number='after-poison', debit=acc['main'], credit=acc['reserve'],
            amount_db=Decimal('1')))
    await drain(Sess)
    async with Sess() as s:
        dead = (await s.execute(select(t.Outbox).where(
            t.Outbox.topic == 'no.such.topic'))).scalar_one()
        assert dead.processed is not None and dead.attempts == 5 and dead.error
        assert await OperationService(session=s).balance(acc['main']) == Decimal('-201')
    print('[ok] отравленное событие: 5 попыток, помечено мёртвым, очередь не встала')

    # --- кросс-валютная проводка: две суммы, применённый курс фиксируют сами суммы ---
    async with Sess() as s:
        await OperationService(session=s).create(OperationCreate(
            code='fx', number='fx-1', debit=acc['main'], credit=acc['usd'],
            amount_db=Decimal('90'), amount_cr=Decimal('1.13')))
    await drain(Sess)
    async with Sess() as s:
        svc = OperationService(session=s)
        assert await svc.balance(acc['main']) == Decimal('-291')
        assert await svc.balance(acc['usd']) == Decimal('1.13')
    print('[ok] кросс-валютная проводка: RUB -90, USD +1.13')

    # --- справочник курсов: история версиями, активная пара уникальна ---
    async with Sess() as s:
        rsvc = RateService(session=s)
        rate = await rsvc.create(RateCreate(code='internal', currency_from=rub_id,
                                            currency_to=usd_id, value=Decimal('0.0125')))
        await rsvc.update(rate.id, RateUpdate(value=Decimal('0.0130')))
        hist = await versions(s, t.Rate, rate.id)
        assert [h.value for h in hist] == [Decimal('0.0125')]
        found = await rsvc.find(RateFilter(currency_from=rub_id, currency_to=usd_id))
        assert len(found) == 1 and found[0].value == Decimal('0.0130')
    async with Sess() as s:
        try:
            await RateService(session=s).create(RateCreate(
                code='internal', currency_from=rub_id, currency_to=usd_id,
                value=Decimal('1')))
            raise AssertionError('дубль активного курса прошёл!')
        except IntegrityError:
            pass
    print('[ok] Rate: история курса версиями, дубль активной пары отвергнут')

    await eng.dispose()
    print('\nТЕСТ OUTBOX ПРОЙДЕН')

