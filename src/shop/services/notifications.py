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
TOPIC_ACCESS = 'notify.access'
TOPIC_CONSENT = 'notify.consent'


async def _subject_user(session: AsyncSession, payload: dict) -> uuid.UUID | None:
    """Пользователь субъекта моста; None — учётки нет (компания и т.п.)."""
    subject_id = uuid.UUID(payload['subject_id'])
    receiver = (await session.execute(
        select(tables.User.id).where(tables.User.person == subject_id)
    )).scalars().first()
    if receiver is None:
        logger.warning('%s: у субъекта %s (%s) нет учётки — уведомление не доставлено',
                       payload.get('action', 'break-glass'),
                       subject_id, payload.get('subject_table'))
    return receiver


@outbox_handler(TOPIC_BREAKGLASS)
async def _notify_breakglass(session: AsyncSession, payload: dict) -> None:
    receiver = await _subject_user(session, payload)
    if receiver is None:
        return  # факт остаётся в аудите KeyService
    session.add(tables.Message(
        code='breakglass',
        receiver=receiver,
        title='Экстренный доступ к вашим данным',
        content=(f"По заявке {payload['request_id']} выполнен break-glass доступ "
                 f"к контуру '{payload['scope']}'. Если это не согласовано с вами — "
                 f"обратитесь к администратору."),
    ))


@outbox_handler(TOPIC_CONSENT)
async def _notify_consent(session: AsyncSession, payload: dict) -> None:
    """requested — владельцу и управляющим; решения — запросившему."""
    action = payload['action']
    if action == 'requested':
        receivers = set()
        owner = await _subject_user(session, payload)
        if owner is not None:
            receivers.add(owner)
        managers = (await session.execute(
            select(tables.Consent.grantee).where(
                tables.Consent.table == payload['subject_table'],
                tables.Consent.objectid == uuid.UUID(payload['subject_id']),
                tables.Consent.scope == 'manage',
                tables.Consent.status == 'approved'))).scalars().all()
        receivers.update(managers)
        for receiver in receivers:
            session.add(tables.Message(
                code='consent', receiver=receiver,
                title='Запрос доступа к вашим данным',
                content=(f"Запрошен доступ: контур '{payload['scope']}'."
                         + (f" Причина: {payload['reason']}" if payload.get('reason') else ''))))
        return
    verdict = {'approved': 'одобрен', 'denied': 'отклонён',
               'revoked': 'отозван', 'expired': 'истёк по сроку'}[action]
    session.add(tables.Message(
        code='consent', receiver=uuid.UUID(payload['grantee']),
        title='Решение по вашему запросу доступа',
        content=f"Доступ (контур '{payload['scope']}') {verdict}."))


@outbox_handler(TOPIC_ACCESS)
async def _notify_access(session: AsyncSession, payload: dict) -> None:
    """Владелец уведомляется о любом изменении круга доступа к его данным."""
    receiver = await _subject_user(session, payload)
    if receiver is None:
        return
    action = 'выдан' if payload['action'] == 'grant' else 'отозван'
    session.add(tables.Message(
        code='access',
        receiver=receiver,
        title='Изменение круга доступа к вашим данным',
        content=(f"Доступ {action}: контур '{payload['scope']}', "
                 f"ключ получателя '{payload['key_id']}'."),
    ))
