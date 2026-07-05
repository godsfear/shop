"""Мост псевдонимизации: связывание персоны с псевдонимом через конвертное шифрование.

Каркас для прогонов сценариев. Криптографию получателей выполняет KeyService
(заглушка HSM); шифрование payload — Fernet на DEK. В продакшене копия
владельца шифруется на клиенте его ключом и приходит сюда готовым шифртекстом
(owner_wrapped), сервер DEK владельца не видит.
"""
import base64
import uuid

from cryptography.fernet import Fernet
from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import db_helper
from .. import tables
from ..keyservice import KeyService, get_key_service

ESCROW_KEY = 'escrow'

OWNER = 'owner'
GROUP = 'group'
ESCROW = 'escrow'


def _fernet(dek: bytes) -> Fernet:
    return Fernet(base64.urlsafe_b64encode(dek))


class BridgeService:
    def __init__(self,
                 session: AsyncSession = Depends(db_helper.scoped_session_dependency),
                 keys: KeyService | None = None):
        self.session = session
        self.keys = keys if keys is not None else get_key_service()

    async def create_link(self, subject_table: str, subject_id: uuid.UUID, scope: str,
                          groups: dict[str, uuid.UUID] | None = None,
                          owner_wrapped: bytes | None = None) -> tuple[tables.Link, uuid.UUID]:
        """Создаёт псевдоним и мост к нему.

        Субъект — любой identity-объект: ('person', id) или ('company', id).
        Копия DEK для escrow создаётся всегда; для групп — по словарю
        {key_id в KeyService: id группы в реестре}; копия владельца —
        если передан owner_wrapped (шифртекст DEK, изготовленный клиентом).
        Возвращает (Link, pseudonym_id) — псевдоним наружу не отдавать,
        он нужен вызывающему только для создания операционных данных.
        """
        dek = self.keys.new_dek()
        pseudonym = tables.Pseudonym()
        self.session.add(pseudonym)
        await self.session.flush()  # нужен pseudonym.id для payload

        link = tables.Link(table=subject_table, objectid=subject_id, scope=scope,
                           payload=_fernet(dek).encrypt(pseudonym.id.bytes))
        self.session.add(link)
        await self.session.flush()  # нужен link.id для копий DEK

        self.session.add(tables.Access(
            link=link.id, recipient_type=ESCROW, recipient=None,
            key_id=ESCROW_KEY, wrapped_dek=self.keys.wrap(ESCROW_KEY, dek)))
        for key_id, group_object in (groups or {}).items():
            self.session.add(tables.Access(
                link=link.id, recipient_type=GROUP, recipient=group_object,
                key_id=key_id, wrapped_dek=self.keys.wrap(key_id, dek)))
        if owner_wrapped is not None:
            self.session.add(tables.Access(
                link=link.id, recipient_type=OWNER, recipient=None,
                key_id=None, wrapped_dek=owner_wrapped))
        await self.session.commit()
        return link, pseudonym.id

    async def resolve(self, link_id: uuid.UUID, key_id: str, actor: str) -> uuid.UUID:
        """Псевдоним по мосту для субъекта с грантом (повседневный доступ группы).

        KeyService сам решает, пускать ли actor (ACL ключа), и пишет аудит.
        """
        link, access = await self._link_and_access(link_id, key_id)
        dek = self.keys.unwrap(key_id, access.wrapped_dek, actor)
        return uuid.UUID(bytes=_fernet(dek).decrypt(link.payload))

    async def breakglass_resolve(self, link_id: uuid.UUID, request_id: str) -> uuid.UUID:
        """Псевдоним через одобренную break-glass заявку (escrow-копия DEK)."""
        link, access = await self._link_and_access(link_id, ESCROW_KEY)
        dek = self.keys.execute(request_id, access.wrapped_dek)
        return uuid.UUID(bytes=_fernet(dek).decrypt(link.payload))

    async def add_recipient(self, link_id: uuid.UUID, key_id: str,
                            recipient: uuid.UUID | None, dek: bytes) -> tables.Access:
        """Грант нового получателя. DEK предоставляет владелец
        (в проде — расшифровав свою копию на клиенте)."""
        access = tables.Access(
            link=link_id, recipient_type=GROUP, recipient=recipient,
            key_id=key_id, wrapped_dek=self.keys.wrap(key_id, dek))
        self.session.add(access)
        await self.session.commit()
        return access

    async def _link_and_access(self, link_id: uuid.UUID,
                               key_id: str) -> tuple[tables.Link, tables.Access]:
        link = (await self.session.execute(
            select(tables.Link).where(tables.Link.id == link_id))).scalar_one()
        access = (await self.session.execute(
            select(tables.Access).where(
                tables.Access.link == link_id,
                tables.Access.key_id == key_id,
            ))).scalar_one()
        return link, access
