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
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..cache import get_cache
from ..database import db_helper
from ..logger import logger
from ..settings import settings
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
        Псевдоним берётся из пула (см. PseudonymPool), а не создаётся на месте.
        Копия DEK для escrow создаётся всегда; для групп — по словарю
        {key_id в KeyService: id группы в реестре}; копия владельца —
        если передан owner_wrapped (шифртекст DEK, изготовленный клиентом).
        Возвращает (Link, pseudonym_id) — псевдоним наружу не отдавать,
        он нужен вызывающему только для создания операционных данных.
        """
        dek = self.keys.new_dek()
        pseudonym_id = await self._claim_pseudonym()

        link = tables.Link(table=subject_table, objectid=subject_id, scope=scope,
                           payload=_fernet(dek).encrypt(pseudonym_id.bytes))
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
        return link, pseudonym_id

    async def replenish_pool(self, count: int | None = None) -> int:
        """Пополняет пул псевдонимов пакетом (регламентная операция).

        Вся партия получает одинаковый begins — момент пополнения, никак
        не связанный с моментами создания мостов.
        """
        count = count or settings.pseudonym_pool_batch
        pseudonyms = [tables.Pseudonym() for _ in range(count)]
        self.session.add_all(pseudonyms)
        await self.session.flush()
        self.session.add_all(tables.PseudonymPool(id=p.id) for p in pseudonyms)
        await self.session.commit()
        return count

    async def _claim_pseudonym(self) -> uuid.UUID:
        """Выдаёт случайный свободный псевдоним из пула и удаляет его из пула.

        SKIP LOCKED — конкурентные выдачи не блокируют друг друга. Случайный
        выбор, а не FIFO: порядок выдачи не должен повторять порядок создания.
        """
        for _ in range(2):
            pid = (await self.session.execute(
                select(tables.PseudonymPool.id)
                .order_by(func.random())
                .limit(1)
                .with_for_update(skip_locked=True)
            )).scalar_one_or_none()
            if pid is not None:
                await self.session.execute(
                    delete(tables.PseudonymPool).where(tables.PseudonymPool.id == pid))
                return pid
            logger.warning('пул псевдонимов пуст — аварийное пополнение; '
                           'анти-корреляция по begins для этой партии ослаблена')
            await self.replenish_pool()
        raise RuntimeError('не удалось получить псевдоним из пула')

    async def resolve(self, link_id: uuid.UUID, key_id: str, actor: str) -> uuid.UUID:
        """Псевдоним по мосту для субъекта с грантом (повседневный доступ группы).

        KeyService сам решает, пускать ли actor (ACL ключа), и пишет аудит.
        Разрешённый мост живёт в сессионном Redis-кэше (TTL settings.cache_ttl_bridge_s),
        ключ включает actor — кэш не даёт доступ тому, кто не проходил ACL.
        Следствие: повторные обращения в пределах TTL не попадают в аудит,
        а отзыв гранта действует после истечения TTL.
        """
        cache = get_cache()
        ckey = f'bridge:{link_id}:{key_id}:{actor}'
        cached = await cache.get(ckey)
        if cached is not None:
            return uuid.UUID(cached)
        link, access = await self._link_and_access(link_id, key_id)
        dek = self.keys.unwrap(key_id, access.wrapped_dek, actor)
        pseudonym = uuid.UUID(bytes=_fernet(dek).decrypt(link.payload))
        await cache.set(ckey, str(pseudonym), settings.cache_ttl_bridge_s)
        return pseudonym

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
