"""Мост псевдонимизации: связывание персоны с псевдонимом через конвертное шифрование.

Каркас для прогонов сценариев. Криптографию получателей выполняет KeyService
(заглушка HSM); шифрование payload — Fernet на DEK. В продакшене копия
владельца шифруется на клиенте его ключом и приходит сюда готовым шифртекстом
(owner_wrapped), сервер DEK владельца не видит.
"""
import asyncio
import base64
import uuid

from cryptography.fernet import Fernet
from fastapi import Depends, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..cache import get_cache
from ..database import db_helper
from ..logger import logger
from ..models.auth import TokenPayload
from ..outbox import emit
from ..settings import settings
from ..versioning import versioned_expire
from .. import tables
from ..keyservice import KeyService, get_key_service
from .consent import is_subject_manager
from .notifications import TOPIC_ACCESS, TOPIC_BREAKGLASS

ESCROW_KEY = 'escrow'

OWNER = 'owner'
GROUP = 'group'
USER = 'user'
ESCROW = 'escrow'


def _fernet(dek: bytes) -> Fernet:
    return Fernet(base64.urlsafe_b64encode(dek))


class BridgeService:
    def __init__(self,
                 session: AsyncSession = Depends(db_helper.scoped_session_dependency),
                 keys: KeyService = Depends(get_key_service)):
        self.session = session
        self.keys = keys

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
            key_id=ESCROW_KEY, wrapped_dek=await self.keys.wrap(ESCROW_KEY, dek)))
        for key_id, group_object in (groups or {}).items():
            self.session.add(tables.Access(
                link=link.id, recipient_type=GROUP, recipient=group_object,
                key_id=key_id, wrapped_dek=await self.keys.wrap(key_id, dek)))
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

    async def top_up_pool(self, target: int | None = None) -> int:
        """Добирает пул до целевого размера (фоново, по расписанию — НЕ на выдачу).

        Расписание, а не синхрон на выдачу: псевдоним должен полежать в пуле
        (лаг), иначе при случайной выдаче свежесозданный уйдёт сразу и его
        begins совпадёт с моментом выдачи. Возвращает сколько создано."""
        target = target or settings.pseudonym_pool_target
        have = (await self.session.execute(
            select(func.count()).select_from(tables.PseudonymPool))).scalar_one()
        deficit = target - have
        if deficit <= 0:
            return 0
        return await self.replenish_pool(deficit)

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
        dek = await self.keys.unwrap(key_id, access.wrapped_dek, actor)
        pseudonym = uuid.UUID(bytes=_fernet(dek).decrypt(link.payload))
        await cache.set(ckey, str(pseudonym), settings.cache_ttl_bridge_s)
        return pseudonym

    async def breakglass_resolve(self, link_id: uuid.UUID, request_id: str) -> uuid.UUID:
        """Псевдоним через одобренную break-glass заявку (escrow-копия DEK).

        Владелец уведомляется всегда: событие в outbox той же транзакцией
        (консумер — services/notifications.py)."""
        link, access = await self._link_and_access(link_id, ESCROW_KEY)
        dek = await self.keys.execute(request_id, access.wrapped_dek)
        pseudonym = uuid.UUID(bytes=_fernet(dek).decrypt(link.payload))
        emit(self.session, TOPIC_BREAKGLASS, {
            'request_id': request_id,
            'subject_table': link.table,
            'subject_id': str(link.objectid),
            'scope': link.scope,
        })
        await self.session.commit()
        return pseudonym

    async def add_recipient(self, link_id: uuid.UUID, key_id: str,
                            recipient: uuid.UUID | None, dek: bytes,
                            recipient_type: str = GROUP,
                            payload: TokenPayload | None = None) -> tables.Access:
        """Грант нового получателя (тип: group | user).

        DEK предоставляет владелец (в проде — расшифровав свою копию на
        клиенте). Управлять кругом доступа может владелец субъекта моста
        или администратор (payload обязателен на API-пути); владелец
        уведомляется событием notify.access той же транзакцией.
        """
        if recipient_type not in (GROUP, USER, OWNER):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"недопустимый тип получателя '{recipient_type}'")
        link = await self._get_link(link_id)
        await self._ensure_manager(link, payload)
        access = tables.Access(
            link=link_id, recipient_type=recipient_type, recipient=recipient,
            key_id=key_id, wrapped_dek=await self.keys.wrap(key_id, dek))
        self.session.add(access)
        emit(self.session, TOPIC_ACCESS, {
            'action': 'grant', 'subject_table': link.table,
            'subject_id': str(link.objectid), 'scope': link.scope, 'key_id': key_id,
        })
        await self.session.commit()
        return access

    async def list_access(self, link_id: uuid.UUID,
                          payload: TokenPayload) -> list[tables.Access]:
        """Кому выдан доступ по мосту (активные копии DEK, без шифртекстов)."""
        link = await self._get_link(link_id)
        await self._ensure_manager(link, payload)
        rows = (await self.session.execute(
            select(tables.Access).where(tables.Access.link == link_id))).scalars().all()
        return list(rows)

    async def revoke_access(self, link_id: uuid.UUID, access_id: uuid.UUID,
                            payload: TokenPayload) -> tables.Access:
        """Отзыв гранта: закрывает копию DEK.

        Escrow-копию отозвать нельзя — break-glass должен работать всегда.
        Для группового получателя членство дополнительно правится ACL ключа
        в KeyService. Уже разрешённый мост может жить в сессионном кэше
        до cache_ttl_bridge_s — известная цена (см. resolve).
        """
        link = await self._get_link(link_id)
        await self._ensure_manager(link, payload)
        access = (await self.session.execute(
            select(tables.Access).where(tables.Access.id == access_id,
                                        tables.Access.link == link_id)
        )).scalar_one_or_none()
        if access is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        if access.recipient_type == ESCROW:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail='escrow-копию отозвать нельзя — '
                                       'break-glass должен работать всегда')
        await versioned_expire(self.session, tables.Access, access_id)
        emit(self.session, TOPIC_ACCESS, {
            'action': 'revoke', 'subject_table': link.table,
            'subject_id': str(link.objectid), 'scope': link.scope,
            'key_id': access.key_id,
        })
        await self.session.commit()
        return access

    async def _get_link(self, link_id: uuid.UUID) -> tables.Link:
        link = (await self.session.execute(
            select(tables.Link).where(tables.Link.id == link_id))).scalar_one_or_none()
        if link is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='мост не найден')
        return link

    async def _ensure_manager(self, link: tables.Link,
                              payload: TokenPayload | None) -> None:
        """Кругом доступа управляет владелец субъекта, его управляющий
        (approved consent scope='manage' — «управляющий» компании или
        доверенное лицо персоны) или администратор."""
        if payload is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail='нужна аутентификация')
        if not await is_subject_manager(self.session, link.table,
                                        link.objectid, payload):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail='управлять доступами может владелец данных, '
                                       'управляющий или администратор')

    async def _link_and_access(self, link_id: uuid.UUID,
                               key_id: str) -> tuple[tables.Link, tables.Access]:
        link = await self._get_link(link_id)
        access = (await self.session.execute(
            select(tables.Access).where(
                tables.Access.link == link_id,
                tables.Access.key_id == key_id,
            ))).scalar_one_or_none()
        if access is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail='доступ не найден (нет копии DEK или отозван)')
        return link, access


async def pseudonym_pool_topper() -> None:
    """Фоновый добор пула псевдонимов до целевого размера (стартует в lifespan).

    По расписанию, независимо от темпа выдачи — так псевдоним всегда полежит
    в пуле (лаг), и штатная выдача не уходит в аварийное пополнение."""
    while True:
        try:
            async with db_helper.session_factory() as session:
                created = await BridgeService(session).top_up_pool()
            if created:
                logger.info('пул псевдонимов: добрано %s', created)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 — БД мигнула: подождать и продолжить
            logger.warning('пул псевдонимов: добор: %r', e)
        await asyncio.sleep(settings.pseudonym_pool_check_s)
