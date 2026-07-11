"""Ключевой сервис на Postgres: ключи под KEK, break-glass и аудит в БД.

Контракт (его же обязан выполнять будущий Vault/HSM-бэкенд):

- ключи получателей (группы, escrow) НЕ покидают сервис — наружу только
  wrap/unwrap; у владельца-пациента свой ключ на клиенте, сервис его не видит;
- прямой unwrap разрешён только субъектам из ACL ключа (повседневная работа
  группы по гранту владельца); членство = ACL, ротация ключа не нужна;
- unwrap escrow-ключом — только через заявку break-glass по политике:
    emergency — N различных подтверждений (settings.breakglass_approvals,
                «правило двух»), подтверждающие несут одну выделенную роль
                (settings.breakglass_role — проверяется на слое API),
                инициатор подтверждать не может, исполнение немедленно;
    legal     — те же подтверждения + обязательные реквизиты основания;
    recovery  — без подтверждений, но исполнение только после окна вето
                (settings.veto_window_s), владелец может отменить заявку;
- каждое действие, включая отказы, пишется в append-only аудит
  с хеш-цепочкой ДО выполнения самого действия;
- уведомление владельца о каждой заявке — обязанность вызывающей стороны
  (очередь/Message), сервис его не эмулирует.

Хранение: таблицы Key / Breakglass / KeyAudit (tables.py) — состояние видно
всем воркерам и переживает рестарт (в отличие от прежней файловой заглушки).
Материал ключей зашифрован KEK — мастер-ключом из settings.kek: компрометация
дампа БД без KEK ключи не раскрывает. Ceiling: KEK в .env; следующий уровень —
KEK в Vault/KMS, реализация Protocol поверх их API (точка — get_key_service).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Literal, Protocol

from cryptography.fernet import Fernet
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .settings import settings
from . import tables

Kind = Literal['emergency', 'legal', 'recovery']

EMERGENCY: Kind = 'emergency'
LEGAL: Kind = 'legal'
RECOVERY: Kind = 'recovery'

_GENESIS = '0' * 64


class KeyServiceError(Exception):
    """Ошибка ключевого сервиса."""


class PolicyError(KeyServiceError):
    """Операция отклонена политикой."""


class AuditError(KeyServiceError):
    """Хеш-цепочка аудита нарушена."""


class KeyService(Protocol):
    """Интерфейс ключевого сервиса — точка замены на Vault Transit / KMS / HSM."""

    def new_dek(self) -> bytes: ...
    async def create_key(self, key_id: str) -> None: ...
    async def grant(self, key_id: str, actor: str) -> None: ...
    async def revoke(self, key_id: str, actor: str) -> None: ...
    async def wrap(self, key_id: str, plaintext: bytes) -> bytes: ...
    async def unwrap(self, key_id: str, token: bytes, actor: str) -> bytes: ...
    async def request_breakglass(self, kind: Kind, key_id: str, requester: str,
                                 reason: str, reference: str | None = None) -> str: ...
    async def approve(self, request_id: str, approver: str) -> None: ...
    async def veto(self, request_id: str, by: str) -> None: ...
    async def execute(self, request_id: str, token: bytes) -> bytes: ...
    async def verify_audit(self) -> int: ...


class DbKeyService:
    """KeyService поверх Postgres. Каждый метод — одна короткая транзакция
    в собственной сессии (session_factory), вызывающие сессий не передают."""

    def __init__(self, session_factory: async_sessionmaker,
                 approvals_required: int = 2,
                 veto_window_s: int = 7 * 24 * 3600,
                 kek: str | None = None):
        self._sessions = session_factory
        self.approvals_required = approvals_required
        self.veto_window = timedelta(seconds=veto_window_s)
        raw = (kek if kek is not None else settings.kek).encode()
        # KEK-строка любой длины -> ключ Fernet (sha256 -> urlsafe base64)
        self._kek = Fernet(base64.urlsafe_b64encode(hashlib.sha256(raw).digest()))

    @staticmethod
    def new_dek() -> bytes:
        """Свежий ключ данных (DEK) для персоны/контура."""
        return os.urandom(32)

    # ------------------------------------------------------------------ #
    #  Ключи и повседневный доступ по ACL
    # ------------------------------------------------------------------ #
    async def create_key(self, key_id: str) -> None:
        async with self._sessions() as s:
            if await s.get(tables.Key, key_id) is not None:
                raise KeyServiceError(f"ключ '{key_id}' уже существует")
            await self._audit(s, 'key.create', key_id=key_id)
            s.add(tables.Key(id=key_id,
                             material=self._kek.encrypt(Fernet.generate_key())))
            try:
                await s.commit()
            except IntegrityError:  # гонка конкурентного create_key
                await s.rollback()
                raise KeyServiceError(f"ключ '{key_id}' уже существует") from None

    async def grant(self, key_id: str, actor: str) -> None:
        async with self._sessions() as s:
            key = await self._key(s, key_id, lock=True)
            await self._audit(s, 'key.grant', key_id=key_id, actor=actor)
            if actor not in key.acl:
                key.acl = key.acl + [actor]
            await s.commit()

    async def revoke(self, key_id: str, actor: str) -> None:
        async with self._sessions() as s:
            key = await self._key(s, key_id, lock=True)
            await self._audit(s, 'key.revoke', key_id=key_id, actor=actor)
            if actor in key.acl:
                key.acl = [a for a in key.acl if a != actor]
            await s.commit()

    async def wrap(self, key_id: str, plaintext: bytes) -> bytes:
        async with self._sessions() as s:
            key = await self._key(s, key_id)
            await self._audit(s, 'key.wrap', key_id=key_id)
            await s.commit()
            return Fernet(self._kek.decrypt(key.material)).encrypt(plaintext)

    async def unwrap(self, key_id: str, token: bytes, actor: str) -> bytes:
        async with self._sessions() as s:
            key = await self._key(s, key_id)
            if actor not in key.acl:
                await self._audit(s, 'key.unwrap.denied', key_id=key_id, actor=actor)
                await s.commit()  # отказ фиксируется в аудите ДО исключения
                raise PolicyError(f"'{actor}' не имеет прямого доступа к ключу '{key_id}'")
            await self._audit(s, 'key.unwrap', key_id=key_id, actor=actor)
            await s.commit()
            return Fernet(self._kek.decrypt(key.material)).decrypt(token)

    # ------------------------------------------------------------------ #
    #  Break-glass
    # ------------------------------------------------------------------ #
    async def request_breakglass(self, kind: Kind, key_id: str, requester: str,
                                 reason: str, reference: str | None = None) -> str:
        async with self._sessions() as s:
            await self._key(s, key_id)
            if kind not in (EMERGENCY, LEGAL, RECOVERY):
                raise KeyServiceError(f"неизвестный вид заявки '{kind}'")
            if kind == LEGAL and not reference:
                await self._audit(s, 'breakglass.request.denied', kind=kind, key_id=key_id,
                                  requester=requester, why='нет реквизитов основания')
                await s.commit()
                raise PolicyError('для legal-заявки обязательны реквизиты основания (reference)')
            req = tables.Breakglass(kind=kind, key_id=key_id, requester=requester,
                                    reason=reason, reference=reference)
            s.add(req)
            await s.flush()
            await self._audit(s, 'breakglass.request', request_id=str(req.id), kind=kind,
                              key_id=key_id, requester=requester, reason=reason,
                              reference=reference)
            await s.commit()
            return str(req.id)

    async def approve(self, request_id: str, approver: str) -> None:
        async with self._sessions() as s:
            req = await self._request(s, request_id, lock=True)
            if req.kind == RECOVERY:
                await self._audit(s, 'breakglass.approve.denied', request_id=request_id,
                                  approver=approver, why='recovery исполняется после окна вето')
                await s.commit()
                raise PolicyError('recovery-заявка не подтверждается — она исполняется после окна вето')
            if approver == req.requester:
                await self._audit(s, 'breakglass.approve.denied', request_id=request_id,
                                  approver=approver, why='инициатор не может подтверждать')
                await s.commit()
                raise PolicyError('инициатор заявки не может её подтверждать')
            if approver not in req.approvals:
                req.approvals = req.approvals + [approver]
            await self._audit(s, 'breakglass.approve', request_id=request_id,
                              approver=approver, total=len(req.approvals))
            await s.commit()

    async def veto(self, request_id: str, by: str) -> None:
        async with self._sessions() as s:
            req = await self._request(s, request_id, lock=True)
            if req.status != 'pending':
                raise PolicyError(f"заявка в статусе '{req.status}', вето невозможно")
            await self._audit(s, 'breakglass.veto', request_id=request_id, by=by)
            req.status = 'vetoed'
            await s.commit()

    async def execute(self, request_id: str, token: bytes) -> bytes:
        async with self._sessions() as s:
            req = await self._request(s, request_id, lock=True)
            if req.status != 'pending':
                await self._audit(s, 'breakglass.execute.denied', request_id=request_id,
                                  why=f'статус {req.status}')
                await s.commit()
                raise PolicyError(f"заявка в статусе '{req.status}'")
            if req.kind in (EMERGENCY, LEGAL):
                if len(req.approvals) < self.approvals_required:
                    await self._audit(s, 'breakglass.execute.denied', request_id=request_id,
                                      why=f'подтверждений {len(req.approvals)}/{self.approvals_required}')
                    await s.commit()
                    raise PolicyError(
                        f'нужно {self.approvals_required} подтверждений, есть {len(req.approvals)}')
            else:  # RECOVERY
                deadline = req.created + self.veto_window
                if datetime.now(timezone.utc) < deadline:
                    await self._audit(s, 'breakglass.execute.denied', request_id=request_id,
                                      why='окно вето не истекло')
                    await s.commit()
                    raise PolicyError(f'окно вето открыто до {deadline.isoformat()}')
            key = await self._key(s, req.key_id)
            await self._audit(s, 'breakglass.execute', request_id=request_id,
                              kind=req.kind, key_id=req.key_id)
            req.status = 'executed'  # одноразовость: одна заявка — один unwrap
            await s.commit()
            return Fernet(self._kek.decrypt(key.material)).decrypt(token)

    # ------------------------------------------------------------------ #
    #  Аудит: append-only с хеш-цепочкой
    # ------------------------------------------------------------------ #
    async def verify_audit(self) -> int:
        """Проверяет цепочку, возвращает число записей; AuditError при разрыве."""
        async with self._sessions() as s:
            rows = (await s.execute(
                select(tables.KeyAudit).order_by(tables.KeyAudit.seq))).scalars().all()
        prev = _GENESIS
        for count, row in enumerate(rows):
            entry = {'ts': row.ts, 'event': row.event, 'data': row.data, 'prev': row.prev}
            if row.prev != prev or row.hash != self._entry_hash(entry):
                raise AuditError(f'цепочка аудита нарушена на записи {count}')
            prev = row.hash
        return len(rows)

    async def _audit(self, s: AsyncSession, event: str, **data) -> None:
        """Запись в цепочку в транзакции вызывающего (фиксируется его commit'ом).

        Advisory-лок до конца транзакции сериализует конкурентные append'ы —
        иначе два воркера прочитали бы один tip и раздвоили цепочку."""
        await s.execute(text("SELECT pg_advisory_xact_lock(hashtext('key_audit'))"))
        tip = (await s.execute(select(tables.KeyAudit.hash)
                               .order_by(tables.KeyAudit.seq.desc())
                               .limit(1))).scalar_one_or_none() or _GENESIS
        entry = {'ts': datetime.now(timezone.utc).isoformat(),
                 'event': event, 'data': data, 'prev': tip}
        s.add(tables.KeyAudit(ts=entry['ts'], event=event, data=data,
                              prev=tip, hash=self._entry_hash(entry)))

    @staticmethod
    def _entry_hash(entry: dict) -> str:
        payload = json.dumps(
            {k: entry[k] for k in ('ts', 'event', 'data', 'prev')},
            sort_keys=True, ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    # ------------------------------------------------------------------ #
    #  Внутреннее
    # ------------------------------------------------------------------ #
    @staticmethod
    async def _key(s: AsyncSession, key_id: str, lock: bool = False) -> tables.Key:
        q = select(tables.Key).where(tables.Key.id == key_id)
        if lock:
            q = q.with_for_update()
        key = (await s.execute(q)).scalar_one_or_none()
        if key is None:
            raise KeyServiceError(f"ключ '{key_id}' не существует")
        return key

    @staticmethod
    async def _request(s: AsyncSession, request_id: str,
                       lock: bool = False) -> tables.Breakglass:
        try:
            rid = uuid.UUID(request_id)
        except ValueError:
            raise KeyServiceError(f"заявка '{request_id}' не найдена") from None
        q = select(tables.Breakglass).where(tables.Breakglass.id == rid)
        if lock:
            q = q.with_for_update()
        req = (await s.execute(q)).scalar_one_or_none()
        if req is None:
            raise KeyServiceError(f"заявка '{request_id}' не найдена")
        return req


@lru_cache
def get_key_service() -> DbKeyService:
    """Точка получения сервиса; при замене на Vault/KMS меняется только она."""
    from .database import db_helper  # локально: разрыв цикла keyservice <- database
    return DbKeyService(
        db_helper.session_factory,
        approvals_required=settings.breakglass_approvals,
        veto_window_s=settings.veto_window_s,
    )
