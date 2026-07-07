"""Согласия: consent-first доступ к приватным данным (см. tables.Consent).

Запросить может любой аутентифицированный; решает владелец субъекта,
его управляющий (approved consent scope='manage') или админ. Все смены
статуса версионны, каждая сторона уведомляется через outbox.
denied/revoked строки закрываются (ends) — уникальный индекс держит
только живые requested/approved, повторный запрос после отказа возможен.
"""
import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import Depends, HTTPException, status
from sqlalchemy import select, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import db_helper
from ..models.auth import TokenPayload
from ..models.consent import ConsentDecision, ConsentRequest
from ..outbox import emit
from ..settings import settings
from ..versioning import versioned_update
from .. import tables
from .notifications import TOPIC_CONSENT

REQUESTED, APPROVED, DENIED, REVOKED = 'requested', 'approved', 'denied', 'revoked'
MANAGE = 'manage'


def _until_alive():
    return or_(tables.Consent.until.is_(None),
               tables.Consent.until > datetime.now(timezone.utc))


async def is_subject_manager(session: AsyncSession, subject_table: str,
                             subject_id: uuid.UUID, payload: TokenPayload) -> bool:
    """Владелец субъекта, его управляющий (manage-consent) или админ."""
    if settings.admin_role in payload.roles:
        return True
    if subject_table == 'person':
        owner = (await session.execute(select(tables.User.id).where(
            tables.User.person == subject_id))).scalars().first()
        if owner == payload.sub:
            return True
    manage = (await session.execute(select(tables.Consent.id).where(
        tables.Consent.table == subject_table,
        tables.Consent.objectid == subject_id,
        tables.Consent.grantee == payload.sub,
        tables.Consent.scope == MANAGE,
        tables.Consent.status == APPROVED,
        _until_alive()))).scalars().first()
    return manage is not None


class ConsentService:
    def __init__(self, session: AsyncSession = Depends(db_helper.scoped_session_dependency)):
        self.session = session

    async def request(self, data: ConsentRequest, payload: TokenPayload) -> tables.Consent:
        """Запрос доступа: grantee = запрашивающий; владельцу уходит уведомление."""
        domain = (await self.session.execute(select(tables.ObjectRegistry.domain).where(
            tables.ObjectRegistry.id == data.subject_id))).scalar_one_or_none()
        if domain is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='субъект не найден')
        if domain != tables.Domain.IDENTITY:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail='согласия применимы только к identity-субъектам')
        row = tables.Consent(table=data.subject_table, objectid=data.subject_id,
                             grantee=payload.sub, scope=data.scope,
                             status=REQUESTED, reason=data.reason)
        self.session.add(row)
        try:
            await self.session.flush()
        except IntegrityError:
            await self.session.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail='живой запрос или согласие уже существует') from None
        self._emit(row, REQUESTED)
        await self.session.commit()
        return row

    async def decide(self, consent_id: uuid.UUID, approve: bool,
                     decision: ConsentDecision, payload: TokenPayload) -> tables.Consent:
        row = await self._get_pending(consent_id, payload, expected=REQUESTED)
        if approve:
            values = {'status': APPROVED, 'until': decision.until}
        else:  # отказ закрывает строку — можно запросить снова
            values = {'status': DENIED, 'ends': datetime.now(timezone.utc)}
        row = await versioned_update(self.session, tables.Consent, row.id, values)
        self._emit(row, APPROVED if approve else DENIED)
        await self.session.commit()
        return row

    async def revoke(self, consent_id: uuid.UUID, payload: TokenPayload) -> tables.Consent:
        row = await self._get_pending(consent_id, payload, expected=APPROVED)
        row = await versioned_update(self.session, tables.Consent, row.id,
                                     {'status': REVOKED, 'ends': datetime.now(timezone.utc)})
        self._emit(row, REVOKED)
        await self.session.commit()
        return row

    async def incoming(self, payload: TokenPayload) -> List[tables.Consent]:
        """Ожидающие решения запросы к субъектам, которыми управляет вызывающий."""
        q = select(tables.Consent).where(tables.Consent.status == REQUESTED)
        if settings.admin_role not in payload.roles:
            person = (await self.session.execute(select(tables.User.person).where(
                tables.User.id == payload.sub))).scalar_one_or_none()
            managed = select(tables.Consent.objectid).where(
                tables.Consent.grantee == payload.sub,
                tables.Consent.scope == MANAGE,
                tables.Consent.status == APPROVED,
                _until_alive())
            q = q.where(or_(tables.Consent.objectid == person,
                            tables.Consent.objectid.in_(managed)))
        return list((await self.session.execute(q)).scalars().all())

    async def mine(self, payload: TokenPayload) -> List[tables.Consent]:
        """Мои запросы и действующие согласия."""
        return list((await self.session.execute(select(tables.Consent).where(
            tables.Consent.grantee == payload.sub))).scalars().all())

    async def check(self, subject_table: str, subject_id: uuid.UUID,
                    grantee: uuid.UUID, scope: str) -> bool:
        """Есть ли действующее согласие (горячий путь identity-эндпоинтов)."""
        row = (await self.session.execute(select(tables.Consent.id).where(
            tables.Consent.table == subject_table,
            tables.Consent.objectid == subject_id,
            tables.Consent.grantee == grantee,
            tables.Consent.scope == scope,
            tables.Consent.status == APPROVED,
            _until_alive()))).scalars().first()
        return row is not None

    async def grant_manage(self, subject_table: str, subject_id: uuid.UUID,
                           grantee: uuid.UUID, payload: TokenPayload) -> tables.Consent:
        """Прямое назначение управляющего (без запроса-одобрения).

        Может действующий управляющий субъекта, владелец персоны или админ.
        Сюда же должен встать будущий Company-API: creator компании получает
        первый manage автоматически при её создании.
        """
        if not await is_subject_manager(self.session, subject_table, subject_id, payload):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail='назначать управляющего может владелец, '
                                       'действующий управляющий или администратор')
        row = tables.Consent(table=subject_table, objectid=subject_id,
                             grantee=grantee, scope=MANAGE, status=APPROVED,
                             reason='назначение управляющего')
        self.session.add(row)
        try:
            await self.session.flush()
        except IntegrityError:
            await self.session.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail='у получателя уже есть живой manage-доступ') from None
        self._emit(row, APPROVED)
        await self.session.commit()
        return row

    async def ensure_access(self, subject_table: str, subject_id: uuid.UUID,
                            payload: TokenPayload, scope: str = 'identity',
                            write: bool = False) -> None:
        """Пропуск к identity-данным субъекта.

        Владелец/управляющий/админ — всегда; для чтения достаточно
        действующего согласия нужного scope. Запись — только управляющим.
        """
        if await is_subject_manager(self.session, subject_table, subject_id, payload):
            return
        if not write and await self.check(subject_table, subject_id, payload.sub, scope):
            return
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail='нет доступа: требуется согласие владельца')

    async def _get_pending(self, consent_id: uuid.UUID, payload: TokenPayload,
                           expected: str) -> tables.Consent:
        row = (await self.session.execute(select(tables.Consent).where(
            tables.Consent.id == consent_id))).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        if not await is_subject_manager(self.session, row.table, row.objectid, payload):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail='решает владелец данных, управляющий или администратор')
        if row.status != expected:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail=f"ожидался статус '{expected}', сейчас '{row.status}'")
        return row

    def _emit(self, row: tables.Consent, action: str) -> None:
        emit(self.session, TOPIC_CONSENT, {
            'action': action, 'subject_table': row.table,
            'subject_id': str(row.objectid), 'scope': row.scope,
            'grantee': str(row.grantee), 'reason': row.reason,
        })
