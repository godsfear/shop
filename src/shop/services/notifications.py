"""Уведомления через outbox (вариант В: события после записи).

Первый консумер — обязательное уведомление владельца о break-glass доступе
(см. память проекта: дизайн псевдонимизации требует уведомлять всегда).
Событие эмитится в BridgeService.breakglass_resolve той же транзакцией,
здесь оно превращается в строку Message для пользователя субъекта.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..logger import logger
from ..outbox import outbox_handler
from .. import tables

TOPIC_BREAKGLASS = 'notify.breakglass'


@outbox_handler(TOPIC_BREAKGLASS)
async def _notify_breakglass(session: AsyncSession, payload: dict) -> None:
    subject_id = uuid.UUID(payload['subject_id'])
    receiver = (await session.execute(
        select(tables.User.id).where(tables.User.person == subject_id)
    )).scalars().first()
    if receiver is None:
        # субъект без учётки (компания или незарегистрированная персона):
        # доставить некому, но факт остаётся в аудите KeyService
        logger.warning('break-glass: у субъекта %s (%s) нет учётки — уведомление не доставлено',
                       subject_id, payload.get('subject_table'))
        return
    session.add(tables.Message(
        code='breakglass',
        receiver=receiver,
        title='Экстренный доступ к вашим данным',
        content=(f"По заявке {payload['request_id']} выполнен break-glass доступ "
                 f"к контуру '{payload['scope']}'. Если это не согласовано с вами — "
                 f"обратитесь к администратору."),
    ))
