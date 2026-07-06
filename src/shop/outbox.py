"""Transactional outbox: события той же транзакцией, что и данные.

Использование:
- издатель: outbox.emit(session, topic, payload) ВНУТРИ транзакции доменной
  записи — событие не потеряется и не задвоится при падении между
  «записал в БД» и «отправил в очередь»;
- потребитель: @outbox_handler(topic) — async handler(session, payload);
  обработка события и пометка processed выполняются одной транзакцией,
  поэтому в пределах БД семантика exactly-once, дедупликация не нужна;
- воркер: outbox_worker() — фоновый цикл (стартует в lifespan приложения);
  для тестов и разовых прогонов — process_one(session).

Ошибки обработчика откатывают доменные изменения события, attempts растёт;
после settings.outbox_max_attempts событие помечается processed + error
(мёртвое) и не блокирует очередь. Конкурентные воркеры не мешают друг
другу: FOR UPDATE SKIP LOCKED. Релей во внешний брокер (Redis Streams) —
отдельный потребитель, когда появятся внешние подписчики.
"""
import asyncio
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .database import db_helper
from .logger import logger
from .settings import settings
from . import tables

_handlers: dict[str, Callable] = {}


def outbox_handler(topic: str):
    """Регистрирует обработчик темы: async handler(session, payload)."""
    def deco(fn: Callable) -> Callable:
        _handlers[topic] = fn
        return fn
    return deco


def emit(session: AsyncSession, topic: str, payload: dict[str, Any]) -> None:
    """Кладёт событие в outbox; вызывать внутри транзакции доменной записи."""
    session.add(tables.Outbox(topic=topic, payload=payload))


async def process_one(session: AsyncSession) -> bool:
    """Обрабатывает одно ожидающее событие; False — очередь пуста."""
    row = (await session.execute(
        select(tables.Outbox)
        .where(tables.Outbox.processed.is_(None))
        .order_by(tables.Outbox.created)
        .limit(1)
        .with_for_update(skip_locked=True)
    )).scalar_one_or_none()
    if row is None:
        await session.rollback()
        return False

    row_id, attempts_before = row.id, row.attempts
    now = datetime.now(timezone.utc)
    handler = _handlers.get(row.topic)
    if handler is None:
        await _register_failure(session, row_id, attempts_before,
                                f"нет обработчика темы '{row.topic}'", now)
        return True
    try:
        await handler(session, row.payload)
    except Exception as e:  # noqa: BLE001 — любой сбой обработчика не должен ронять воркер
        await session.rollback()  # откат доменных изменений события
        await _register_failure(session, row_id, attempts_before, repr(e)[:500], now)
        return True
    row.processed = now
    await session.commit()
    return True


async def _register_failure(session: AsyncSession, row_id, attempts_before: int,
                            error: str, now: datetime) -> None:
    attempts = attempts_before + 1
    dead = attempts >= settings.outbox_max_attempts
    logger.warning('outbox: событие %s, попытка %s/%s%s: %s',
                   row_id, attempts, settings.outbox_max_attempts,
                   ' — помечено мёртвым' if dead else '', error)
    await session.execute(
        update(tables.Outbox)
        .where(tables.Outbox.id == row_id,
               # после rollback блокировка снята: конкурентный воркер мог уже
               # успешно обработать событие — не воскрешать его
               tables.Outbox.processed.is_(None))
        .values(attempts=attempts, error=error,
                processed=now if dead else None))
    await session.commit()


async def outbox_worker() -> None:
    """Фоновый воркер: разбирает очередь, спит только когда она пуста."""
    while True:
        try:
            async with db_helper.session_factory() as session:
                worked = await process_one(session)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 — БД мигнула: подождать и продолжить
            logger.warning('outbox: воркер: %r', e)
            worked = False
        if not worked:
            await asyncio.sleep(settings.outbox_poll_s)
