"""Общие помощники тестов."""
import asyncio

from sqlalchemy import select, func

from shop import tables
from shop.outbox import process_one
from shop.settings import settings

settings.outbox_backoff_s = 0  # тестам не ждать backoff ретраев (drain — тесный цикл)


async def drain(Sess) -> None:
    """Дренит outbox до реальной пустоты (pending == 0).

    Останов по одному False ненадёжен: только что закоммиченное событие бывает
    транзиентно невидимо новому соединению (async-видимость) — прод-воркер
    переживает это поллингом со sleep, здесь перепроверяем pending и ждём
    (щедрый бонус до ~5с; дольше = реальная блокировка, не транзиент).
    """
    idle = 0
    while True:
        async with Sess() as s:
            if await process_one(s):
                idle = 0
                continue
        async with Sess() as s:
            pend = (await s.execute(select(func.count()).select_from(tables.Outbox)
                    .where(tables.Outbox.processed.is_(None)))).scalar_one()
        if pend == 0:
            return
        assert idle < 100, 'событие застряло дольше 5с — реальная блокировка'
        idle += 1
        await asyncio.sleep(0.05)
