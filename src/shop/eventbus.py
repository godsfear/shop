"""Шина событий поверх outbox: гибрид «outbox + relay + RabbitMQ».

Атомарность «данные + событие» остаётся за outbox (источник истины). Здесь:
- RELAY: читает неотправленные события outbox (FOR UPDATE SKIP LOCKED),
  публикует в topic-exchange с publisher-confirm, помечает processed. Падение
  между publish и пометкой -> повторная публикация -> дубль в шине;
- КОНСУМЕР: читает очередь, ДЕДУПлицирует по id события (ProcessedEvent,
  ON CONFLICT), гоняет @outbox_handler в той же транзакции, ack. Итог —
  эффект exactly-once на at-least-once транспорте;
- РЕТРАИ: сбой обработчика -> republish в retry-exchange с x-attempt+1;
  retry-очередь держит сообщение TTL и dead-letter'ит обратно в main-exchange
  (routing key сохраняется). Исчерпание попыток -> dead-очередь. Немаршрутизируемые
  события ловит alternate-exchange -> dead (ничего не теряется молча).

Топология очередей по нагрузке: shop.ai (ИИ-разбор/оценка — масштабируется
конкурирующими консумерами), shop.mail (почта), shop.notify (уведомления).
"""
import asyncio
import json
from datetime import datetime, timezone

import aio_pika
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .database import db_helper
from .logger import logger
from .outbox import _handlers
from .settings import settings
from . import tables

EXCHANGE = 'shop.events'
RETRY_EX = 'shop.events.retry'
DEAD_EX = 'shop.events.dead'

# очередь -> топики, которые она обслуживает (привязки к main-exchange)
QUEUE_TOPICS = {
    'shop.ai':     ['data.extract', 'episode.evaluate', 'episode.workup', 'episode.plan'],
    'shop.mail':   ['notify.email'],
    'shop.notify': ['notify.breakglass', 'notify.access', 'notify.consent'],
}


async def _topology(channel: aio_pika.abc.AbstractChannel):
    """Идемпотентно объявляет exchanges/очереди/привязки."""
    dead_ex = await channel.declare_exchange(DEAD_EX, aio_pika.ExchangeType.FANOUT, durable=True)
    # alternate-exchange: неотрефанные (без привязки) события -> dead, не теряются
    main_ex = await channel.declare_exchange(
        EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True,
        arguments={'alternate-exchange': DEAD_EX})
    retry_ex = await channel.declare_exchange(RETRY_EX, aio_pika.ExchangeType.TOPIC, durable=True)

    dead_q = await channel.declare_queue('shop.dead', durable=True)
    await dead_q.bind(dead_ex)

    # retry-очередь: подержать TTL и вернуть в main-exchange (routing key сохранится)
    retry_q = await channel.declare_queue(
        'shop.retry', durable=True,
        arguments={'x-message-ttl': settings.bus_retry_delay_ms,
                   'x-dead-letter-exchange': EXCHANGE})
    await retry_q.bind(retry_ex, routing_key='#')

    for qname, topics in QUEUE_TOPICS.items():
        # reject(requeue=False) на исчерпании попыток -> DLX -> dead-очередь
        q = await channel.declare_queue(qname, durable=True,
                                        arguments={'x-dead-letter-exchange': DEAD_EX})
        for topic in topics:
            await q.bind(main_ex, routing_key=topic)
    return main_ex, retry_ex


# --------------------------------------------------------------------- relay
async def relay_loop() -> None:
    """outbox -> RabbitMQ. Одно соединение с publisher-confirm."""
    conn = await aio_pika.connect_robust(settings.rabbitmq_uri)
    async with conn:
        channel = await conn.channel(publisher_confirms=True)
        main_ex, _ = await _topology(channel)
        logger.info('eventbus: relay запущен')
        while True:
            try:
                published = await _relay_batch(main_ex)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 — брокер/БД мигнули: подождать
                logger.warning('eventbus: relay: %r', e)
                published = 0
            if not published:
                await asyncio.sleep(settings.outbox_poll_s)


async def _relay_batch(main_ex: aio_pika.abc.AbstractExchange, limit: int = 100) -> int:
    async with db_helper.session_factory() as s:
        rows = (await s.execute(
            select(tables.Outbox)
            .where(tables.Outbox.processed.is_(None))
            .order_by(tables.Outbox.created)
            .limit(limit)
            .with_for_update(skip_locked=True))).scalars().all()
        now = datetime.now(timezone.utc)
        for row in rows:
            body = json.dumps({'id': str(row.id), 'topic': row.topic,
                               'payload': row.payload}).encode()
            # publish возвращается после confirm брокера (publisher_confirms)
            await main_ex.publish(
                aio_pika.Message(body, delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                                 content_type='application/json'),
                routing_key=row.topic)
            row.processed = now
        await s.commit()
        return len(rows)


# ------------------------------------------------------------------ consumer
async def _dedup(s: AsyncSession, event_id: str) -> bool:
    """True — событие впервые (вставили маркер); False — уже обработано."""
    res = await s.execute(pg_insert(tables.ProcessedEvent)
                          .values(id=event_id).on_conflict_do_nothing(index_elements=['id']))
    return res.rowcount == 1


async def _handle(msg: aio_pika.abc.AbstractIncomingMessage,
                  retry_ex: aio_pika.abc.AbstractExchange) -> None:
    data = json.loads(msg.body)
    event_id, topic, payload = data['id'], data['topic'], data['payload']
    handler = _handlers.get(topic)
    if handler is None:
        logger.warning('eventbus: нет обработчика темы %s -> dead', topic)
        await msg.reject(requeue=False)     # DLX очереди -> dead
        return
    try:
        async with db_helper.session_factory() as s:
            if not await _dedup(s, event_id):
                await s.rollback()
                await msg.ack()             # дубль доставки — уже обработано
                return
            await handler(s, payload)
            await s.commit()                # эффект обработчика + маркер дедупа атомарно
        await msg.ack()
    except Exception as e:  # noqa: BLE001 — сбой обработчика: ретрай или dead
        attempt = int(msg.headers.get('x-attempt', 0)) + 1 if msg.headers else 1
        if attempt >= settings.bus_max_attempts:
            logger.warning('eventbus: событие %s мёртво после %s попыток: %r',
                           event_id, attempt, e)
            await msg.reject(requeue=False)  # DLX очереди -> dead-очередь
        else:
            logger.warning('eventbus: событие %s, попытка %s: %r — ретрай', event_id, attempt, e)
            await retry_ex.publish(
                aio_pika.Message(msg.body, delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                                 headers={'x-attempt': attempt}),
                routing_key=topic)
            await msg.ack()                  # оригинал снят, копия в retry-очереди


async def consume_loop() -> None:
    """Консумеры всех очередей в одном процессе (масштаб — репликами процесса)."""
    conn = await aio_pika.connect_robust(settings.rabbitmq_uri)
    async with conn:
        channel = await conn.channel()
        await channel.set_qos(prefetch_count=settings.bus_prefetch)
        _, retry_ex = await _topology(channel)
        for qname in QUEUE_TOPICS:
            queue = await channel.get_queue(qname)
            await queue.consume(lambda m, rex=retry_ex: _handle(m, rex))
        logger.info('eventbus: консумеры запущены (%s)', ', '.join(QUEUE_TOPICS))
        await asyncio.Future()               # держим соединение живым
